"""
Persona prompt builder for OSE LLM actors.

build_persona_prompt() constructs the system prompt for a given actor
under a given doctrine condition. The system prompt is stable across turns
for a given actor+doctrine combination — only the decision prompt changes
each turn. This makes system prompt caching effective.

Doctrine conditions:
  "realist"     — Waltzian structural realism: relative gains, power maximization,
                  security dilemma awareness, distrust of institutions
  "liberal"     — Keohane liberal institutionalism: absolute gains, interdependence,
                  multilateral cooperation, reputational costs of defection
  "org_process" — Allison Model II: organizational routines, SOPs, bureaucratic
                  inertia, satisficing over optimizing
  "baseline"    — Rational Actor Model (Allison Model I): unitary optimizer, pure goal/cost utility calculation
"""
from __future__ import annotations
from pathlib import Path
from world.state import Actor, WorldState

_PROMPTS_DIR = Path(__file__).parent / "prompts"

DOCTRINE_INSTRUCTIONS: dict[str, str] = {
    "realist": """
You follow STRUCTURAL REALISM (Waltz/Mearsheimer) as your decision doctrine.

Core principles you must apply explicitly:
- States operate in an anarchic system with no supranational authority. Self-help is the only reliable strategy.
- Prioritize RELATIVE GAINS over absolute gains. A deal that benefits your adversary more than you is worse than no deal.
- The SECURITY DILEMMA is real: your defensive actions will be read as threatening by adversaries. Account for this.
- Alliances are temporary instruments of power balancing, not moral commitments.
- Military capability is the ultimate currency of international power. Economic and political tools matter only insofar as they convert to security.
- Distrust signals of restraint from adversaries — they may be deception.
- Your red lines define your irreducible security perimeter. Defend them at all costs.

When reasoning, explicitly invoke relative power calculations and security-dilemma logic.
""".strip(),

    "liberal": """
You follow LIBERAL INSTITUTIONALISM (Keohane/Nye) as your decision doctrine.

Core principles you must apply explicitly:
- Absolute gains matter more than relative gains. Cooperation that grows the total pie is valuable even if your adversary also benefits.
- International institutions, norms, and reputation constrain behavior and create predictability. Honor your commitments.
- Complex interdependence makes conflict costly for all parties. Highlight shared vulnerabilities.
- Multilateral legitimacy amplifies your actions. Prefer coalition-backed moves over unilateral ones.
- Defection from established norms carries long-term reputational costs that outweigh short-term gains.
- Communication and transparency reduce misperception. Back-channels and negotiations are strategically valuable.

When reasoning, explicitly invoke interdependence, reputational logic, and institutional constraints.
""".strip(),

    "org_process": """
You follow the ORGANIZATIONAL PROCESS MODEL (Allison Model II) as your decision doctrine.

Core principles you must apply explicitly:
- Your decision is constrained by existing Standard Operating Procedures (SOPs) and organizational routines.
- You do not optimize from scratch each turn — you select from a menu of pre-approved response options.
- Satisficing is the norm: choose the first option that meets a minimally acceptable threshold, not the theoretically optimal one.
- Bureaucratic inertia is real: prefer actions that are incremental extensions of your current posture over sharp pivots.
- Your military, diplomatic, and economic arms operate semi-independently and may have conflicting preferred responses.
- Dramatic departures from established doctrine require extraordinary justification.

When reasoning, explicitly identify which organizational routine or SOP your action follows, and why a more aggressive or novel option was NOT selected.
""".strip(),

    "baseline": """
You follow the RATIONAL ACTOR MODEL (Allison Model I) as your decision framework.

Core principles you must apply explicitly:
- You are a unitary, rational decision-maker with stable, ordered preferences.
- For each available action, estimate: (a) the probability it advances your highest-priority achievable goal, (b) the expected costs across military, economic, and political dimensions, (c) the risk of triggering adversary responses that worsen your position.
- Select the action with the best expected utility: highest goal advancement at lowest expected total cost.
- You are NOT constrained by organizational routines, institutional inertia, or coalition pressures — you optimize freely from your goal set.
- If two actions have similar expected utility, prefer the lower-cost option (cost minimization as tiebreaker).
- Do not apply realist relative-gains logic, liberal interdependence logic, or org_process SOP logic — reason purely from your stated goals and a cost-benefit calculation.

When reasoning, explicitly state: (a) your current highest-priority reachable goal, (b) the expected utility estimate for your chosen action vs. the top alternative, (c) why the chosen action dominates on the utility calculation.
""".strip(),
}


def build_persona_prompt(actor: Actor, doctrine_condition: str) -> str:
    """
    Build the system prompt for an actor under a given doctrine condition.

    This prompt is stable across turns — suitable for Anthropic prompt caching.
    """
    template = (_PROMPTS_DIR / "system.txt").read_text()

    goals_block = "\n".join(f"{i+1}. {g}" for i, g in enumerate(actor.goals))

    red_lines_block = "\n".join(
        f"- **{rl.description}**\n"
        f"  Trigger: {rl.trigger_condition}\n"
        f"  Response if crossed: {rl.if_crossed}"
        for rl in actor.red_lines
    ) or "No formal red lines declared."

    doctrine_text = DOCTRINE_INSTRUCTIONS.get(
        doctrine_condition,
        DOCTRINE_INSTRUCTIONS["baseline"]
    )

    return template.format(
        actor_name=actor.name,
        actor_short_name=actor.short_name,
        actor_type=actor.actor_type,
        ideology=actor.ideology,
        strategic_culture=actor.strategic_culture,
        decision_style=actor.decision_style,
        goals=goals_block,
        red_lines=red_lines_block,
        war_aversion=actor.war_aversion or "No specific war aversion factors specified.",
        historical_precedents=actor.historical_precedents or "No historical precedents specified.",
        institutional_constraints=actor.institutional_constraints or "No institutional constraints specified.",
        cognitive_patterns=actor.cognitive_patterns or "No cognitive patterns specified.",
        doctrine_instructions=doctrine_text,
    )
