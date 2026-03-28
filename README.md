# OSE — Omni-Simulation Engine

**Status:** Active
**Started:** 2026-03-26
**Build status:** v0.3 — capability system, pressure model, open-ended event generation complete · ready for first run
**Repo:** `~/Documents/OSE/`

---

## Purpose

OSE is a modular geopolitical conflict simulation framework where LLM agents play real-world state actors and make decisions that update a shared world state over multiple turns.

**Research thesis:** Can LLMs faithfully follow qualitative IR decision doctrines, and does doctrine assignment change behavioural outcomes in measurable ways?

This is an **interventional** experiment, not descriptive. The doctrine IS the independent variable. Every other LLM conflict simulation just observes what LLMs do. OSE prescribes how they must reason and measures compliance.

OSE is not a game. It is a **research instrument**.

---

## System Architecture

### Full Data Flow

```mermaid
flowchart TD
    WS([World State]) --> CAP[Capability Builder\nderive 13-field capability vector per actor]
    WS --> PRES[Pressure Model\ncompute 8-dimension pressure state]
    CAP --> PF[Perception Filter\nnoise scaled to actor intel quality]
    PRES --> PF
    PF --> PP[Persona Prompt\ndoctrine · identity · war aversion · history]
    PP --> DP[Decision Prompt\ncapabilities + pressures + available actions]
    DP --> LLM{Claude Sonnet\nwrites reasoning then calls action tool}
    LLM --> AP[Action Parser\nconverts output to typed action]
    AP --> V{Rule Validator\ncapability-gated · pure logic}
    V -->|valid| TR[Turn Resolver\nall actors resolved simultaneously]
    V -->|invalid| RT[Retry\nerror feedback injected]
    RT -->|up to 2x| LLM
    RT -->|still invalid| FB[Hold Position\nfallback action]
    TR --> MUT[State Mutation\nresource deltas + action costs applied]
    MUT --> CD[Cascade Detector\n9 rules · 6 escalatory + 3 de-escalatory]
    CD --> LOG[Logger\nfull reasoning trace saved to SQLite]
    LOG --> NEXT([Next Turn])
    EG([Event Generator\npressure-gated + capability-gated\nweighted sampling each turn]) --> TR

    style V fill:#c0392b,color:#fff
    style LLM fill:#2980b9,color:#fff
    style CD fill:#8e44ad,color:#fff
    style EG fill:#16a085,color:#fff
    style CAP fill:#d35400,color:#fff
    style PRES fill:#d35400,color:#fff
```

### Module Dependency Graph

```mermaid
graph LR
    subgraph World["World Layer"]
        State[State Models\nall Pydantic resources]
        Events[Event Models\ndecisions · logs · records]
        RelGraph[Relationship Graph\nbilateral query wrapper]
        WCap[Capability Vector\n13-field normalized actor vector]
        WPres[Pressure State\n8-dimension pressure model]
    end

    subgraph Actors["Actor Layer"]
        Prompts[Prompt Templates\nsystem + decision text]
        Persona[Persona Builder\ndoctrine instructions injected here]
        LLMActor[LLM Decision Actor\nperception → CoT → action → retry]
    end

    subgraph Engine["Engine Layer"]
        Actions[Action Space\n25 typed action classes]
        Validator[Validator\ncapability-gated firewall]
        Resolver[Turn Resolver\nsimultaneous conflict adjudication]
        Cascade[Cascade Detector\n9 rules · escalatory + de-escalatory]
        Loop[Simulation Loop\nfull turn lifecycle]
        ECap[Capability Builder\nbuild_actor_capabilities per turn]
        EPres[Pressure Tracker\nScenarioPressureModel · smoothed]
        Perception[Perception Filter\ndeterministic SHA-256 noise]
        Costs[Action Costs\nper-action resource depletion]
        EventGen[Event Generator\npressure + capability gated]
        ScenTemplate[Scenario Template\nOpenEndedScenarioTemplate ABC]
    end

    subgraph Scenarios["Scenario Layer"]
        ScenarioBase[Scenario Base\nABC interface]
        Taiwan[Taiwan Strait\n4 actors · pressure-gated event pool]
    end

    subgraph Scoring["Scoring Layer"]
        Fidelity[Doctrine Fidelity\nLLM-as-judge rubric]
        BCI[Behavioral Consistency\nnormalized entropy across runs]
    end

    Runner[Experiment Runner\nbatch orchestrator]

    subgraph Analysis["Analysis Layer"]
        AEngine[Analysis Engine\npure SQL+Python stats]
        Analyst[LLM Analyst\noptional Sonnet qualitative layer]
        Renderer[Renderer\nMarkdown + LaTeX dual output]
        Report[Report CLI\norchestrator + entry point]
    end

    State --> LLMActor
    State --> Actions
    State --> Resolver
    State --> Cascade
    State --> ECap
    State --> EPres
    Events --> LLMActor
    Events --> Loop
    Events --> BCI
    RelGraph --> LLMActor
    WCap --> LLMActor
    WCap --> Validator
    WPres --> LLMActor
    WPres --> EventGen
    ECap --> WCap
    EPres --> WPres
    Perception --> LLMActor
    Costs --> Resolver
    EventGen --> Loop
    ScenTemplate --> Taiwan
    Prompts --> Persona
    Persona --> LLMActor
    Actions --> LLMActor
    Actions --> Validator
    Actions --> Resolver
    Validator --> Loop
    Resolver --> Loop
    Cascade --> Loop
    LLMActor --> Loop
    ScenarioBase --> ScenTemplate
    Taiwan --> Loop
    Loop --> Fidelity
    Runner --> Loop
    Runner --> Fidelity
    Runner --> BCI
    BCI --> AEngine
    Fidelity --> AEngine
    AEngine --> Analyst
    AEngine --> Renderer
    Analyst --> Renderer
    Renderer --> Report
    Report --> AEngine
```

### Turn Lifecycle

```mermaid
sequenceDiagram
    participant Scenario as Event Pool
    participant Engine as Simulation Engine
    participant Agent as State Agent
    participant LLM as Claude Sonnet
    participant Validator as Rule Validator
    participant Resolver as Turn Resolver
    participant Cascade
    participant Logger

    Engine->>Scenario: generate events (tension + capability)
    Note over Scenario: Weighted sampling based on<br/>crisis_instability + actor uncertainty
    Scenario-->>Engine: 0–3 events (e.g., "Cyber Probe Detected")

    loop Each State Actor
        Engine->>Agent: Request Action(world state)
        Agent->>Agent: Apply Perception Filter (Jervis)
        Note right of Agent: Injects noise based on<br/>Intel Quality (0.0 - 1.0)
        
        Agent->>Agent: Load Strategy Profile (2026 NDS/ODC)
        Note right of Agent: Loads hard constraints:<br/>e.g., US "Integrated Deterrence"<br/>or Taiwan "Asymmetric Porcupine"
        
        Agent->>LLM: Persona + Doctrine + Strategy + Perceived State
        Note over LLM: 6-step rationale required:<br/>1. Situation, 2. Doctrine check,<br/>3. Capability check, 4. Risk...
        
        LLM-->>Agent: Reasoning trace + Action call
        
        Agent->>Validator: check action legality (Physical/Political)
        alt valid
            Validator-->>Agent: approved
        else invalid
            Validator-->>Agent: error (e.g., "Insufficient Lift Capability")
            Agent->>LLM: retry with constraints (max 2x)
        end
        Agent-->>Engine: Action + Final Rationale
    end

    Engine->>Resolver: Resolve all actions (Simultaneous)
    Resolver-->>Engine: New Base State + Outcome Events

    Engine->>Cascade: check structural rules (9 logic gates)
    Cascade-->>Engine: Secondary changes (e.g., market flight)

    Engine->>Logger: Log telemetry (BCI/DFS metadata)
    Engine->>Engine: Terminal check (De-escalation or War)
```

### Experiment Design

```mermaid
flowchart LR
    subgraph Conditions["4 Doctrine Conditions"]
        C1[Realist\npower · security dilemma]
        C2[Liberal\ninterdependence · institutions]
        C3[Org Process\nSOPs · bureaucratic inertia]
        C4[Baseline\nno doctrine · LLM default]
    end

    subgraph Runs["N runs per condition"]
        R1[Run 1]
        R2[Run 2]
        RN[Run N\npilot: 5 · full: 20]
    end

    subgraph Scoring["Measurement"]
        DFS[Doctrine Fidelity Score\ndoes reasoning match doctrine?]
        BCI[Behavioral Consistency Index\nare actions consistent across runs?]
        OUT[Outcome Classification\nsuccess · failure · frozen]
    end

    C1 & C2 & C3 & C4 --> R1 & R2 & RN
    R1 & R2 & RN --> DFS & BCI & OUT
    DFS & BCI & OUT --> Results([experiment_summary.json])
```

---

## File Inventory

| File | Role |
|---|---|
| `world/state.py` | WorldState, Actor (+ historical_precedents, institutional_constraints, cognitive_patterns, war_aversion fields), all resource models |
| `world/events.py` | DecisionRecord, TurnLog, GlobalEvent, RunRecord |
| `world/graph.py` | RelationshipGraph — named query wrapper over bilateral relationships |
| `world/capabilities.py` | CapabilityVector — 13-field normalized actor capability model · as_bands() for LLM · clamp() for engine |
| `world/pressures.py` | PressureState — 8-dimension pressure model · PressureDelta · apply_pressure_delta() |
| `actors/base.py` | ActorInterface ABC |
| `actors/persona.py` | build_persona_prompt() — 4 doctrine conditions + war_aversion injection |
| `actors/llm_actor.py` | Full LLM pipeline: perception filter → capability summary → tool_choice=auto → CoT → tool_use → validate → retry |
| `actors/prompts/system.txt` | System prompt template — identity + war_aversion + historical precedents + doctrine |
| `actors/prompts/decision.txt` | Per-turn prompt — situation + 6-step rationale schema |
| `engine/actions.py` | 25 typed action classes + ACTION_REGISTRY + parser + get_available_actions_for() |
| `engine/validator.py` | ActionValidator — capability-gated rule-based firewall |
| `engine/resolver.py` | Simultaneous resolution — all 25 actions, conflict adjudication, applies action costs |
| `engine/cascade.py` | 9 cascade rules — 6 escalatory + 3 de-escalatory structural downstream effects |
| `engine/loop.py` | SimulationEngine — ensure_derived_state() called 3×/turn, full lifecycle + Rich display |
| `engine/capabilities.py` | build_actor_capabilities() → CapabilityVector · ACTION_CONSTRAINTS per-action gates · get_available_actions_for() |
| `engine/pressures.py` | ScenarioPressureModel — ACTION_PRESSURE_MAP · smoothed pressure computation (α=0.40) |
| `engine/perception.py` | build_perception_packet() — SHA-256 deterministic Gaussian noise · ally intel bonus +0.04 |
| `engine/costs.py` | BASE_ACTION_COSTS — per-action resource depletion applied by resolver |
| `engine/event_generation.py` | OpenEndedEventGenerator — pressure-gated + capability-gated weighted sampling · dynamic event budget |
| `engine/scenario_template.py` | OpenEndedScenarioTemplate ABC — theater-adjusted capability profiles · full event pipeline |
| `scenarios/base.py` | ScenarioDefinition ABC |
| `scenarios/taiwan_strait.py` | 4-actor Taiwan Strait 2026 — full actor profiles, pressure/capability-gated event pool |
| `cli/run.py` | Entry point — `python3 -m cli.run` |
| `logs/logger.py` | SQLite logger — 4 tables, full prompt + reasoning stored |
| `scoring/fidelity.py` | DoctrinesFidelityScorer — LLM-as-judge, 4 rubrics |
| `scoring/bci.py` | BCICalculator — normalized entropy across N runs, 6 action categories |
| `experiments/runner.py` | Batch orchestrator — 4×N runs, auto-score, summary JSON |
| `analysis/engine.py` | AnalysisEngine — extracts data from SQLite run DBs, computes all statistics (tension, escalation, action distributions, DFS, BCI) |
| `analysis/analyst.py` | LLMAnalyst — optional Sonnet call producing qualitative narrative (executive summary, turning points, cross-doctrine findings) |
| `analysis/renderer.py` | MarkdownRenderer + LaTeXRenderer — dual-format output matching research document style |
| `analysis/report.py` | CLI orchestrator — `python3 -m analysis.report --runs --llm --latex --output` |

---

## Action Space (25 Actions)

| Category | Count | Actions |
|---|---|---|
| Military | 8 | mobilize, strike, advance, withdraw, blockade, defensive_posture, probe, signal_resolve |
| Diplomatic | 7 | negotiate, targeted_sanction, comprehensive_sanction, form_alliance, condemn, intel_sharing, back_channel |
| Economic | 4 | embargo, foreign_aid, cut_supply, technology_restriction |
| Information/Cyber | 3 | propaganda, partial_coercion, cyber_operation |
| Nuclear | 1 | nuclear_signal |
| Inaction | 2 | hold_position, monitor |

Each action has: `is_valid(state) → (bool, errors)`, `get_expected_effects()`, resource cost fields.

---

## Capability System (v0.3)

Every actor has a 13-field `CapabilityVector` rebuilt each turn from their raw resource state. Actors only see **qualitative bands** (HIGH/MEDIUM/LOW) — never raw floats.

| Field | Derived From |
|---|---|
| `local_naval_projection` | `naval_power × (1 + 0.3 × amphibious_capacity)` |
| `local_air_projection` | `air_superiority × readiness` |
| `missile_a2ad_capability` | `a2ad_effectiveness` |
| `cyber_capability` | `decision_unity × 0.4 + readiness × 0.6` |
| `intelligence_quality` | `actor.information_quality` |
| `economic_coercion_capacity` | `trade_openness × foreign_reserves` |
| `alliance_leverage` | max relationship alliance_strength across allies |
| `logistics_endurance` | `foreign_reserves × 0.5 + industrial_capacity × 0.5` |
| `domestic_stability` | `political.domestic_stability` |
| `war_aversion` | `1.0 − casualty_tolerance` |
| `escalation_tolerance` | `casualty_tolerance × 0.6 + readiness × 0.4` |
| `bureaucratic_flexibility` | `decision_unity × 0.7 + regime_legitimacy × 0.3` |
| `signaling_credibility` | `nuclear_capability × 0.5 + international_standing × 0.5` |

### Action Constraints (Capability Gates)

`get_available_actions_for(actor_id, state)` filters the action space before showing it to the LLM. Actors cannot choose actions they lack the capability for.

| Action | Minimum Requirements |
|---|---|
| `nuclear_signal` | signaling_credibility ≥ 0.60 AND escalation_tolerance ≥ 0.60 |
| `strike` | local_air_projection ≥ 0.40 OR local_naval_projection ≥ 0.40 |
| `blockade` | local_naval_projection ≥ 0.45 |
| `cyber_operation` | cyber_capability ≥ 0.35 |
| `form_alliance` | alliance_leverage ≥ 0.25 AND signaling_credibility ≥ 0.30 |
| `technology_restriction` | economic_coercion_capacity ≥ 0.40 |

---

## Pressure System (v0.3)

`ScenarioPressureModel` computes an 8-dimension `PressureState` each turn. Pressures gate event generation and appear in actor perception packets.

| Dimension | Meaning |
|---|---|
| `military_pressure` | Mobilization and strike activity across all actors |
| `diplomatic_pressure` | Sanction, embargo, condemnation accumulation |
| `alliance_pressure` | Alliance cohesion stress |
| `domestic_pressure` | Internal political instability |
| `economic_pressure` | GDP degradation and trade disruption |
| `informational_pressure` | Propaganda and disinformation activity |
| `crisis_instability` | Aggregate crisis volatility — gates dynamic event budget |
| `uncertainty` | Contradictory signals in recent events |

Pressures are **smoothed** each turn: `new = (1 − α) × previous + α × computed` (α = 0.40). `ACTION_PRESSURE_MAP` defines per-action pressure deltas — e.g., `negotiate → {diplomatic_pressure: −0.06, crisis_instability: −0.04}`, `strike → {military_pressure: +0.12, crisis_instability: +0.08}`.

---

## Taiwan Strait 2026 Scenario

**Actors:** USA · PRC · TWN · JPN
**Starting phase:** `tension` | **Global tension:** `0.55`
**Relationships:** 12 directed bilateral edges

### Actor Power Summary (illustrative values)

| Actor | Conv. Forces | Naval | Air | Amphibious | A2/AD | Nuclear | Info Quality |
|---|---|---|---|---|---|---|---|
| USA | 0.85 | 0.90 | 0.88 | 0.30 | 0.52 | 0.90 | 0.82 |
| PRC | 0.82 | 0.76 | 0.72 | 0.78 | 0.82 | 0.80 | 0.75 |
| TWN | 0.50 | 0.45 | 0.55 | 0.12 | 0.68 | 0.00 | 0.70 |
| JPN | 0.62 | 0.68 | 0.64 | 0.22 | 0.58 | 0.00 | 0.76 |

### Actor Behavioral Profile Depth

All four actors have full three-field behavioral grounding injected into the system prompt:

| Field | Content |
|---|---|
| `historical_precedents` | Real crisis case studies with decision patterns and lessons (e.g. Third Taiwan Strait Crisis, Pelosi visit, Scarborough Shoal) |
| `institutional_constraints` | Actual decision machinery (NSC process, CMC structure, Article 9, Taiwan NSC) — binding procedural limits |
| `cognitive_patterns` | Documented biases (US casualty sensitivity, PRC Century of Humiliation, Taiwan abandonment anxiety, Japan entrapment-abandonment dilemma) |
| `war_aversion` | Actor-specific concrete reasons why escalation to war is catastrophic — weighted heavily in every decision |

### Relationship Graph

```mermaid
graph TD
    USA -->|ally 0.92| JPN
    USA -->|partner 0.58| TWN
    USA -->|competitor| PRC
    JPN -->|ally 0.92| USA
    JPN -->|partner 0.30| TWN
    JPN -->|competitor| PRC
    TWN -->|partner 0.58| USA
    TWN -->|partner 0.32| JPN
    TWN -->|hostile| PRC
    PRC -->|adversary| USA
    PRC -->|competitor| JPN
    PRC -->|hostile| TWN

    style PRC fill:#c0392b,color:#fff
    style TWN fill:#27ae60,color:#fff
    style USA fill:#2980b9,color:#fff
    style JPN fill:#e67e22,color:#fff
```

### Event Generation System (v0.3)

Turn 0 has one scripted ignition event (PRC announces PLAN exercises, +0.06 tension). Every subsequent turn uses `OpenEndedEventGenerator` — pressure-gated and capability-gated weighted sampling with a seeded RNG for reproducibility.

**Event budget per turn:** 1 base + up to +2 for high `crisis_instability` / `uncertainty` / `economic_pressure`.

**Event templates have four gates:** `pressure_gates` (minimum pressure threshold), `capability_gates` (actor capability required), `phase_bias` (weight multiplier per crisis phase), `recent_action_bias` (weight boost if matching action occurred last turn).

```mermaid
flowchart LR
    LiveState([Pressure State\ncomputed each turn])

    subgraph Escalatory["Escalatory — 7 events"]
        E1[PLAN warship enters Taiwan waters · +0.05]
        E2[PLA ballistic missile test · +0.07]
        E3[PRC reunification ultimatum in state media · +0.04]
        E4[US carrier strikes through Taiwan Strait · +0.05]
        E5[PRC cyber attack on Taiwan power grid · +0.04]
        E6[US Taiwan arms enhancement legislation · +0.04]
        E7[PRC coast guard blockade of outlying islands · +0.03]
    end

    subgraph DeEscalatory["De-escalatory — 6 events"]
        D1[US–PRC back-channel diplomatic call · −0.04]
        D2[PRC announces exercises concluded · −0.05]
        D3[ASEAN joint restraint statement · −0.03]
        D4[Taiwan signals willingness for dialogue · −0.04]
        D5[G7 calls for de-escalation · −0.03]
        D6[US–PRC military hotline activated · −0.03]
    end

    subgraph Neutral["Neutral / Ambiguous — 3 events"]
        N1[Major Taiwan earthquake · −0.02]
        N2[Global oil price spike · +0.02]
        N3[International media frenzy · +0.02]
    end

    LiveState --> Escalatory & DeEscalatory & Neutral
```

### Terminal Conditions

- `deterrence_failure` — war phase + tension ≥ 0.90
- `deterrence_success` — tension ≤ 0.30
- `frozen_conflict` — all actors passive for 3+ consecutive turns
- `defense_success` — max turns reached, crisis/tension phase

---

## Cascade Rules

```mermaid
flowchart TD
    Action([Resolved Actions this Turn])

    subgraph Escalatory["Escalatory"]
        R1[Phase Transition\ntension crosses threshold → crisis phase changes]
        R2[Strike Cascade\nstruck actor's allies raise military readiness]
        R3[Mobilization Cascade\nadversaries raise threat perception in response]
        R4[Supply Chain Cascade\nblockades and embargoes degrade semiconductor supply]
        R5[Alliance Cohesion Cascade\nno ally response to a strike → credibility loss]
        R6[Economic Collapse\nGDP below critical threshold → domestic instability]
    end

    subgraph Deescalatory["De-escalatory"]
        R7[Diplomatic De-escalation\nnegotiate reduces threat perception and tension\nmutual negotiation triggers stronger bilateral effect]
        R8[Back-Channel Cascade\nquiet diplomacy reduces target's threat perception]
        R9[Aid and Alliance Cascade\nforeign aid stabilizes recipient · intel sharing builds trust\nalliance formation strengthens systemic cohesion]
    end

    Action --> Escalatory & Deescalatory
    Escalatory & Deescalatory --> NextState([Updated World State])
```

**Design note:** Cooperative cascades are intentionally weaker than escalatory ones — de-escalation is structurally harder than escalation. Mutual negotiation (both sides targeting each other in the same turn) triggers a larger effect than unilateral.

---

## Doctrine Conditions

| Condition | IR Theory | Core Prescription |
|---|---|---|
| `realist` | Waltz / Mearsheimer | Relative gains; security dilemma logic; alliances as temporary; nuclear signaling as primary deterrent |
| `liberal` | Keohane / Nye | Absolute gains; interdependence costs; multilateral legitimacy; reputation preservation |
| `org_process` | Allison Model II | SOP selection; satisficing; incremental over pivot; bureaucratic constraints binding |
| `baseline` | None | Actor identity only — empirically expected to resemble realist (LLM default prior) |

### Doctrine-Action Discrimination

| Doctrine | Distinctive action signals |
|---|---|
| `realist` | nuclear_signal, mobilize, strike, blockade — power currency logic |
| `liberal` | negotiate, back_channel, targeted_sanction, form_alliance — interdependence preservation |
| `org_process` | defensive_posture, monitor, targeted_sanction, intel_sharing — incremental SOPs |
| `baseline` | LLM default prior (empirically expected to resemble realist) |

---

## Measurement Framework

### Doctrine Fidelity Score (DFS)

Scored by `claude-haiku-4-5-20251001` as judge. Judge sees only the reasoning trace — not the actor identity or the action chosen.

- `doctrine_language_score` [0–1] — uses doctrine vocabulary in reasoning
- `doctrine_logic_score` [0–1] — action follows from doctrine logic
- `doctrine_consistent_decision` [bool] — final choice is doctrine-coherent
- `contamination_flag` [bool] — uses language from a different doctrine

### Behavioral Consistency Index (BCI)

- Normalized Shannon entropy of action distribution across N repeated runs
- `0.0` = always same action (perfectly consistent — doctrine reliably channels behavior)
- `1.0` = uniform distribution (fully stochastic — doctrine has no effect)
- Computed at action level and **6-category level** (military, diplomatic, economic, information, nuclear, inaction) per actor, per condition

---

## How to Run

```bash
cd ~/Documents/OSE

# Single run — test the loop (~$0.60–0.70, ~40 API calls + reasoning traces)
python3 -m cli.run --scenario taiwan_strait --doctrine realist --turns 10

# Pilot experiment — 4 conditions × 5 runs (~$12–14)
python3 -m experiments.runner --runs 5 --turns 10

# Full research experiment — 4 conditions × 20 runs (~$50–60)
python3 -m experiments.runner --runs 20 --turns 15

# Query reasoning traces from any run
sqlite3 logs/runs/<run_id>.db \
  "SELECT actor_short_name, turn, length(reasoning_trace), substr(reasoning_trace,1,300) FROM decisions ORDER BY turn, actor_short_name LIMIT 20;"

# Query action distribution
sqlite3 logs/runs/<run_id>.db \
  "SELECT actor_short_name, parsed_action, COUNT(*) FROM decisions GROUP BY actor_short_name, parsed_action ORDER BY actor_short_name, COUNT(*) DESC;"

# Generate analysis report (statistical only)
python3 -m analysis.report --runs logs/runs/ --output reports/

# With LLM qualitative analysis + LaTeX PDF
python3 -m analysis.report --runs logs/runs/ --llm --latex --output reports/
```

---

## Stack

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Pydantic v2, Anthropic SDK |
| Schema | Pydantic v2 | Strict typing, [0,1] float enforcement |
| LLM (decisions) | `claude-sonnet-4-6` | Best reasoning/cost at simulation scale |
| LLM (scoring) | `claude-haiku-4-5-20251001` | Cost-efficient bulk fidelity scoring |
| Structured output | Anthropic `tool_use` with `tool_choice=auto` | CoT reasoning first, then guaranteed JSON schema action |
| Logging | SQLite (stdlib) | No deps, full replay, queryable |
| CLI display | Rich | Turn-by-turn terminal output |
| LLM (analysis) | `claude-sonnet-4-6` | Qualitative narrative requires cross-doctrine comparative reasoning |
| Reports | Markdown + LaTeX (booktabs/fancyhdr/natbib) | Matches existing research document style |
| Dependency mgmt | `uv` + `pyproject.toml` | Fast, modern |

---

## Build Status

| Phase | Deliverable | Status |
|---|---|---|
| 1 | World state models + action space | ✅ Done |
| 2 | Actor + LLM loop | ✅ Done |
| 3 | Simulation engine + logger | ✅ Done |
| 4 | Taiwan Strait scenario + CLI | ✅ Done |
| 5 | Scoring layer (DFS + BCI) + experiment runner | ✅ Done |
| 5b | v0.2 improvements (action space, stochastic events, reasoning traces, actor profiles) | ✅ Done |
| 5c | v0.3 improvements (capability system · pressure model · perception filter · action costs · open-ended event generation · de-escalatory cascade rules) | ✅ Done |
| 6 | Run pilot experiment (4×5) | ⬜ Next |
| 7 | Analysis engine (engine + LLM analyst + Markdown/LaTeX renderer + CLI) | ✅ Done |
| 8 | Research write-up | ⬜ Pending |

---

## Known Limitations (for methods section)

- **No causal identification**: OSE measures behavioral correlates of doctrine assignment, not causal doctrine→action chains. Reasoning traces may be post-hoc rationalization.
- **DFS circularity**: Doctrine rubrics and doctrine instructions share vocabulary — measure may capture prompt compliance, not genuine reasoning change.
- **Cascade asymmetry (partially resolved)**: Three de-escalatory cascade rules added (Rules 7–9) for negotiate, back_channel, foreign_aid, intel_sharing, form_alliance. Escalatory effects are still structurally stronger — de-escalation requires sustained cooperation, not a single action.
- **Single scenario**: All findings are Taiwan Strait-specific. Generalizability requires a second scenario.
- **Baseline confound**: Baseline condition reflects LLM default prior (likely realist-adjacent), not a clean null.
- **Haiku judge**: Secondary LLM is weaker than the decision LLM; complex reasoning distinctions may be mis-scored.
- **IV-clarity trade-off (v0.3)**: Capability-gated action filtering improves behavioral realism but creates a confound — some doctrine-appropriate actions may be unavailable due to actor capability state, not doctrine resistance. Methods section must distinguish capability-blocked decisions from doctrine-non-compliant ones.

---

## Open Questions

- Add a second scenario (Ukraine, South China Sea) to test generalizability?
- Manual annotation sample: have IR scholar score 20–30 traces to validate Haiku judge (r ≥ 0.70 target)?
- Scoring: should the judge LLM also see the action chosen, or only the reasoning trace?
- Should actors be shown outcome classifications from prior runs to build trajectory awareness?
- Does capability-gated action filtering confound the doctrine IV? (e.g., realist doctrine may push toward nuclear_signal but TWN is capability-blocked — is that doctrine failing or realism working?)

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-03-26 | LLMs as behavior engine (hybrid CoT + structured output) | More realistic than utility-function agents; human irrationality is load-bearing |
| 2026-03-26 | Conflict as first domain | Highest decision value; most demanding test of emergence |
| 2026-03-26 | Taiwan Strait as first scenario | Well-documented motivations, clear asymmetries, rich cascade potential |
| 2026-03-26 | CLI-first, no UI | Core loop correctness before interface |
| 2026-03-26 | temperature=0 for structured outputs | Reproducibility via full prompt logging |
| 2026-03-26 | Doctrine vs. persona design | Doctrine is experimentally controllable; persona conflates identity with reasoning |
| 2026-03-26 | Qualitative bands (HIGH/MEDIUM/LOW) not raw floats | Prevents numerical hallucination; matches how real decision-makers reason |
| 2026-03-26 | Simultaneous turn resolution | Eliminates turn-order bias; forces genuine uncertainty into actor calculus |
| 2026-03-27 | 23 action classes (expanded from 17) | Added probe, signal_resolve, back_channel, partial_coercion, 4 inaction types |
| 2026-03-27 | Haiku for fidelity scoring | Cost-efficient for bulk secondary LLM calls; reasoning quality sufficient for rubric scoring |
| 2026-03-27 | tool_choice="any" → "auto" | "any" suppressed text reasoning; actors produced empty reasoning traces defeating DFS scoring |
| 2026-03-27 | Scripted events → stochastic pool | Deterministic turn-3 event (+0.08) guaranteed crisis threshold crossing regardless of actor behavior; pool creates genuine run-to-run variance for BCI |
| 2026-03-27 | Dynamic scenario event generation | Pre-computed events used initial state for all condition checks; now rolls against live tension each turn |
| 2026-03-27 | 25 action classes (restructured from 23) | Added cyber_operation, technology_restriction, nuclear_signal; split sanction into targeted/comprehensive; removed redundant delay_commitment and wait_and_observe |
| 2026-03-27 | war_aversion field in actor profiles | Actors had no awareness that war is catastrophically bad for them; locally-rational decisions produced deterministic escalation |
| 2026-03-27 | Full actor behavioral profiles | historical_precedents + institutional_constraints + cognitive_patterns grounds LLM behavior in real-world decision patterns |
| 2026-03-27 | Analysis engine: hybrid stats + optional LLM | Pure Python deterministic stats (engine.py) + optional Sonnet qualitative layer (analyst.py); inflection-point trace sampling keeps LLM context manageable; dual Markdown/LaTeX output |
| 2026-03-27 | Inflection-point sampling for LLM analysis | Feeding all traces would blow context; instead sample max 6/run: first active action per actor, phase transitions, contamination flags — high signal density |
| 2026-03-28 | Capability Vector system (13 fields) | Actors had no grounding for why certain actions were impossible; capability gates derived from actor resources prevent hallucinated escalation (e.g. TWN cannot nuclear_signal) |
| 2026-03-28 | Pressure State system (8 dimensions) | Events and cascades lacked environmental context; pressure model provides smoothed, lagged signal that gates event generation and appears in actor perception |
| 2026-03-28 | OpenEndedEventGenerator replacing simple probability rolls | Fixed probability pool was insensitive to world state; pressure + capability gates create realistic conditional event generation that responds to actor behavior |
| 2026-03-28 | De-escalatory cascade rules (Rules 7–9) | Cooperative actions had no structural reward; asymmetry was producing deterministic escalation |
| 2026-03-28 | Perception filter with deterministic SHA-256 noise | LLM actors were seeing exact world state floats; noise scaled by information_quality and relationship type creates realistic intelligence uncertainty |
| 2026-03-28 | Action costs wired into resolver | Actions had no resource depletion; military activity needed to deplete readiness, economic actions needed to deplete foreign reserves |
| 2026-03-28 | IV-clarity trade-off accepted | v0.3 capability/pressure grounding makes behavioral realism stronger but weakens clean experimental control — methods section must acknowledge |
