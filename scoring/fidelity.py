"""
Doctrine Fidelity Scorer — evaluates LLM reasoning traces against doctrine rubrics.

Uses a secondary LLM call (LLM-as-judge pattern) to score each DecisionRecord's
reasoning_trace against the rubric for its assigned doctrine condition.

Three scores are produced per decision:
  doctrine_language_score   [0.0–1.0] — does the trace use the doctrine's vocabulary?
  doctrine_logic_score      [0.0–1.0] — does the action follow from the doctrine's logic?
  doctrine_consistent_decision [bool] — is the chosen action consistent with the doctrine?
  contamination_flag        [bool]    — does the trace use language from OTHER doctrines?

Design constraints:
  - The judge sees ONLY the reasoning trace and the doctrine rubric.
  - It does NOT see: actor identity, action chosen, or other actors' decisions.
  - This prevents anchoring on outcome rather than process.
  - temperature=0 for reproducibility; scores are deterministic given the trace.
  - Uses tool_use to force structured score output.
"""
from __future__ import annotations

import os
import json
from typing import Optional

import anthropic
from dotenv import load_dotenv

from world.events import DecisionRecord

load_dotenv()

SCORER_MODEL = "claude-haiku-4-5-20251001"  # Cost-efficient for bulk scoring

# ── Doctrine rubrics ──────────────────────────────────────────────────────────
# Each rubric defines what language and logic patterns constitute fidelity
# to that doctrine. The judge uses this to evaluate the reasoning trace.

DOCTRINE_RUBRICS: dict[str, str] = {
    "realist": """
DOCTRINE: Structural Realism (Waltz/Mearsheimer)

A HIGH-FIDELITY realist reasoning trace will contain:

LANGUAGE MARKERS (doctrine_language_score):
- Explicit reference to relative power, relative gains, or power balance
- Reference to the security dilemma, anarchy, or self-help logic
- Distrust of adversary intentions regardless of stated signals
- Treatment of alliances as temporary and conditional on power calculus
- Reference to military capability as the primary currency of security

LOGIC MARKERS (doctrine_logic_score):
- The actor explicitly compares its power position to the adversary's
- The action selected maximizes relative power or minimizes relative power loss
- The actor discounts cooperative signals as potentially deceptive
- The actor prioritizes security over economic or diplomatic gains when they conflict
- If the actor cooperates, it explains why this serves long-term power accumulation

CONTAMINATION MARKERS (contamination_flag = True if present):
- Appeals to international institutions, norms, or multilateral legitimacy as constraints
- Emphasis on absolute gains or mutual benefit as the primary rationale
- References to organizational routines or bureaucratic process as decision drivers
- Explicit rejection of power-maximizing logic in favor of normative constraints
""".strip(),

    "liberal": """
DOCTRINE: Liberal Institutionalism (Keohane/Nye)

A HIGH-FIDELITY liberal reasoning trace will contain:

LANGUAGE MARKERS (doctrine_language_score):
- Explicit reference to interdependence, mutual vulnerability, or shared costs
- Reference to international institutions, norms, regimes, or rules-based order
- Reference to reputation, credibility, or long-term relationship value
- Emphasis on absolute gains (both parties benefit) over relative gains
- Reference to multilateral coalition-building or legitimacy

LOGIC MARKERS (doctrine_logic_score):
- The actor explicitly calculates the cost of defection on future cooperation
- The action selected preserves or builds institutional relationships
- The actor accounts for how its actions will be perceived by third parties
- Cooperative options are preferred when they produce acceptable absolute gains
- Escalatory options are justified only when institutional mechanisms have failed

CONTAMINATION MARKERS (contamination_flag = True if present):
- Pure power-maximizing logic with no reference to interdependence costs
- Explicit rejection of institutional constraints as naive or irrelevant
- Treatment of alliances as purely temporary power instruments
- Satisficing language ("good enough") without institutional justification
""".strip(),

    "org_process": """
DOCTRINE: Organizational Process Model (Allison Model II)

A HIGH-FIDELITY org_process reasoning trace will contain:

LANGUAGE MARKERS (doctrine_language_score):
- Reference to standard operating procedures, SOPs, or established routines
- Reference to organizational constraints, bureaucratic process, or interagency coordination
- Satisficing language: "adequate," "acceptable threshold," "within parameters"
- Reference to incremental steps or extensions of current posture
- Acknowledgment of options NOT taken because they fall outside established procedures

LOGIC MARKERS (doctrine_logic_score):
- The action selected is an incremental extension of the current posture, not a sharp pivot
- The actor explicitly identifies which SOP or routine the action follows
- The actor rejects more aggressive or novel options on procedural grounds
- The decision reflects constraints from multiple organizational units, not pure optimization
- The reasoning acknowledges what the "organization" can and cannot do

CONTAMINATION MARKERS (contamination_flag = True if present):
- Pure strategic optimization from first principles with no procedural constraints
- Sharp doctrine pivots that ignore organizational inertia
- Explicit power-balance calculations characteristic of realist logic
- Interdependence reasoning characteristic of liberal logic
""".strip(),

    "baseline": """
DOCTRINE: Baseline (No Prescribed Doctrine)

A baseline reasoning trace should be evaluated for INTERNAL CONSISTENCY only:

LANGUAGE MARKERS (doctrine_language_score):
- The reasoning is coherent and consistent with the actor's stated identity
- The actor refers to its own goals and red lines
- The reasoning is grounded in the perceived situation

LOGIC MARKERS (doctrine_logic_score):
- The chosen action is consistent with at least one of the actor's stated goals
- The actor has not violated any of its stated red lines
- The reasoning accounts for the current crisis phase and tension level

CONTAMINATION MARKERS (contamination_flag):
- For baseline: contamination_flag = False always (no doctrine to contaminate)
""".strip(),
}

# ── Scoring tool schema ───────────────────────────────────────────────────────

SCORING_TOOL = {
    "name": "submit_fidelity_scores",
    "description": "Submit doctrine fidelity scores for the provided reasoning trace.",
    "input_schema": {
        "type": "object",
        "properties": {
            "doctrine_language_score": {
                "type": "number",
                "description": (
                    "0.0–1.0. How strongly does the reasoning trace use the vocabulary "
                    "and conceptual language of the assigned doctrine? "
                    "0.0 = no doctrine language present. 1.0 = all key doctrine terms used correctly."
                ),
            },
            "doctrine_logic_score": {
                "type": "number",
                "description": (
                    "0.0–1.0. Does the reasoning logic follow the doctrine's prescriptions? "
                    "0.0 = action directly contradicts doctrine logic. "
                    "1.0 = action follows precisely from doctrine reasoning."
                ),
            },
            "doctrine_consistent_decision": {
                "type": "boolean",
                "description": (
                    "True if the stated action selection in step 6 is consistent with "
                    "what the assigned doctrine would prescribe given the stated situation. "
                    "False if the actor's reasoning reached a doctrine-inconsistent conclusion."
                ),
            },
            "contamination_flag": {
                "type": "boolean",
                "description": (
                    "True if the reasoning trace contains significant language or logic "
                    "from a DIFFERENT doctrine (e.g., a realist trace using liberal "
                    "interdependence reasoning as the primary justification). "
                    "False if the trace is doctrinally pure or baseline condition."
                ),
            },
            "scoring_rationale": {
                "type": "string",
                "description": "1-2 sentence justification for the scores assigned.",
            },
        },
        "required": [
            "doctrine_language_score",
            "doctrine_logic_score",
            "doctrine_consistent_decision",
            "contamination_flag",
            "scoring_rationale",
        ],
    },
}


# ── Scorer ────────────────────────────────────────────────────────────────────

class DoctrinesFidelityScorer:
    """
    Scores a DecisionRecord's reasoning trace for doctrine fidelity.
    One instance can score many records; the Anthropic client is reused.
    """

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def score(self, record: DecisionRecord) -> DecisionRecord:
        """
        Score the reasoning trace in a DecisionRecord.
        Returns the same record with fidelity scores populated.
        Does not mutate the SQLite log — caller must update the DB separately.
        """
        if not record.reasoning_trace or len(record.reasoning_trace.strip()) < 20:
            # Nothing to score
            record.doctrine_language_score = 0.0
            record.doctrine_logic_score = 0.0
            record.doctrine_consistent_decision = False
            record.contamination_flag = False
            return record

        rubric = DOCTRINE_RUBRICS.get(
            record.doctrine_condition,
            DOCTRINE_RUBRICS["baseline"]
        )

        system_prompt = (
            "You are a social science research assistant scoring AI-generated "
            "reasoning traces for adherence to prescribed decision-making doctrines. "
            "You do NOT know which actor produced this trace or what action was chosen. "
            "Score only on the reasoning process, not the outcome."
        )

        user_prompt = f"""## Assigned Doctrine Rubric

{rubric}

---

## Reasoning Trace to Score

The following is a chain-of-thought reasoning trace produced by an LLM actor
during turn {record.turn} of a geopolitical crisis simulation.
Crisis phase at time of decision: {record.crisis_phase_at_decision}

Score this trace against the rubric above. Be strict — a score of 0.8+ should
require clear, explicit use of doctrine language and logic.

---

{record.reasoning_trace}

---

Call submit_fidelity_scores with your assessment."""

        try:
            response = self._client.messages.create(
                model=SCORER_MODEL,
                max_tokens=512,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[SCORING_TOOL],
                tool_choice={"type": "any"},
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_fidelity_scores":
                    scores = block.input
                    record.doctrine_language_score = float(
                        max(0.0, min(1.0, scores.get("doctrine_language_score", 0.0)))
                    )
                    record.doctrine_logic_score = float(
                        max(0.0, min(1.0, scores.get("doctrine_logic_score", 0.0)))
                    )
                    record.doctrine_consistent_decision = bool(
                        scores.get("doctrine_consistent_decision", False)
                    )
                    record.contamination_flag = bool(
                        scores.get("contamination_flag", False)
                    )
                    break

        except Exception as e:
            # Scoring failure is non-fatal — leave scores as None
            print(f"  [scorer] Failed to score record {record.id[:8]}: {e}")

        return record

    def score_run_from_db(self, db_path: str) -> dict:
        """
        Score all unscored decisions in a SQLite run log.
        Updates the decisions table in-place.
        Returns aggregate statistics.
        """
        import sqlite3

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, turn, actor_short_name, doctrine_condition,
                   reasoning_trace, crisis_phase_at_decision
            FROM decisions
            WHERE doctrine_language_score IS NULL
            AND final_applied = 1
        """)
        rows = cur.fetchall()

        if not rows:
            print("No unscored decisions found.")
            conn.close()
            return {}

        print(f"Scoring {len(rows)} decisions...")
        scored = 0

        for row in rows:
            rec_id, turn, actor, doctrine, trace, phase = row
            # Build minimal DecisionRecord for scoring
            record = DecisionRecord(
                id=rec_id,
                turn=turn,
                actor_short_name=actor,
                doctrine_condition=doctrine,
                run_id="",
                system_prompt="",
                perception_block="",
                reasoning_trace=trace or "",
                raw_llm_response="",
                validation_result="valid",
                crisis_phase_at_decision=phase or "tension",
            )
            record = self.score(record)

            cur.execute("""
                UPDATE decisions SET
                    doctrine_language_score = ?,
                    doctrine_logic_score = ?,
                    doctrine_consistent_decision = ?,
                    contamination_flag = ?
                WHERE id = ?
            """, (
                record.doctrine_language_score,
                record.doctrine_logic_score,
                int(record.doctrine_consistent_decision) if record.doctrine_consistent_decision is not None else None,
                int(record.contamination_flag) if record.contamination_flag is not None else None,
                rec_id,
            ))
            conn.commit()
            scored += 1
            print(f"  Scored {actor} turn {turn}: "
                  f"lang={record.doctrine_language_score:.2f} "
                  f"logic={record.doctrine_logic_score:.2f} "
                  f"consistent={record.doctrine_consistent_decision} "
                  f"contaminated={record.contamination_flag}")

        # Aggregate stats
        cur.execute("""
            SELECT
                AVG(doctrine_language_score),
                AVG(doctrine_logic_score),
                AVG(CAST(doctrine_consistent_decision AS REAL)),
                AVG(CAST(contamination_flag AS REAL)),
                COUNT(*)
            FROM decisions
            WHERE doctrine_language_score IS NOT NULL
        """)
        row = cur.fetchone()
        stats = {
            "mean_language_score": round(row[0] or 0, 3),
            "mean_logic_score": round(row[1] or 0, 3),
            "consistency_rate": round(row[2] or 0, 3),
            "contamination_rate": round(row[3] or 0, 3),
            "n_scored": row[4],
        }

        conn.close()
        print(f"\nRun DFS summary: {stats}")
        return stats
