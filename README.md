# OSE — Omni-Simulation Engine

**Status:** Active | **Version:** v0.4

LLM-driven geopolitical conflict simulation. State actors powered by real IR decision doctrines. Outcomes emerge from LLM reasoning, not scripted rules.

**Research thesis:** Does doctrine assignment change measurable behavioural outcomes across LLMs? OSE prescribes how agents must reason and measures compliance — it is an interventional experiment, not a sandbox.

---

## Quick Start

```bash
# Install
uv pip install -e ".[dev]"
cp .env.example .env   # add keys

# Run with Anthropic (default)
python -m cli.run --scenario taiwan_strait --doctrine realist --turns 15

# Run with OpenRouter
python -m cli.run --scenario taiwan_strait --doctrine liberal --provider openrouter --model openai/gpt-4o --turns 15

# Run batch experiments
python -m experiments.runner --scenarios taiwan_strait --doctrines realist liberal constructivist --providers anthropic openrouter --turns 15

# Generate report
python -m analysis --run-dir logs/runs/ --output reports/
```

---

## Data Flow

```mermaid
flowchart TD
    WS([World State]) --> CAP[Capability Builder\n13-field normalized vector]
    WS --> PRES[Pressure Model\n8-dimension pressure state]
    CAP --> PF[Perception Filter\nnoise scaled to actor intel quality]
    PRES --> PF
    PF --> PP[Persona Prompt\ndoctrine · identity · war aversion · history]
    PP --> DP[Decision Prompt\ncapabilities + pressures + available actions]
    DP --> LLM{LLM Provider\nAnthropic · OpenRouter · any model}
    LLM --> AP[Action Parser]
    AP --> V{Rule Validator\ncapability-gated · pure logic}
    V -->|valid| TR[Turn Resolver\nsimultaneous resolution]
    V -->|invalid| RT[Retry\nerror injected · max 2x]
    RT -->|still invalid| FB[Hold Position\nfallback]
    TR --> MUT[State Mutation\nresource deltas applied]
    MUT --> CD[Cascade Detector\n9 rules]
    CD --> LOG[Logger\nSQLite · full reasoning trace]
    LOG --> NEXT([Next Turn])
    EG([Event Generator\npressure + capability gated]) --> TR
```

---

## Module Graph

```mermaid
graph LR
    subgraph World["World Layer"]
        State[State Models\nall Pydantic resources]
        Events[Event Models\ndecisions · logs · records]
        RelGraph[Relationship Graph\nbilateral query wrapper]
        WCap[Capability Vector\n13-field normalized actor vector]
        WPres[Pressure State\n8-dimension pressure model]
    end

    subgraph Providers["Provider Layer"]
        ProvBase[LLMProvider ABC\nProviderCallResult · usage tracking]
        ProvAnthropic[Anthropic Provider\ntool_use · cache_control]
        ProvOpenRouter[OpenRouter Provider\nOpenAI-compat · 100+ models]
        ProvFactory[Provider Factory\nbuild_provider · require_env]
    end

    subgraph Actors["Actor Layer"]
        Prompts[Prompt Templates\nsystem + decision text]
        Persona[Persona Builder\n6 doctrine conditions]
        LLMActor[LLM Decision Actor\nperception → CoT → call → retry]
    end

    subgraph Engine["Engine Layer"]
        Actions[Action Space\n32 typed action classes]
        Validator[Validator\ncapability-gated firewall]
        Resolver[Turn Resolver\nsimultaneous conflict adjudication]
        Cascade[Cascade Detector\n9 rules]
        Loop[Simulation Loop\nfull turn lifecycle]
        ECap[Capability Builder]
        EPres[Pressure Tracker\nSmoothed ScenarioPressureModel]
        Perception[Perception Filter\ndeterministic SHA-256 noise]
        EventGen[Event Generator\npressure + capability gated]
    end

    subgraph Scenarios["Scenario Layer"]
        ScenarioBase[Scenario Base ABC]
        Taiwan[Taiwan Strait\n4 actors · pressure-gated events]
    end

    subgraph Scoring["Scoring Layer"]
        Fidelity[Doctrine Fidelity\nLLM-as-judge rubric]
        BCI[Behavioral Consistency\nnormalized entropy across runs]
    end

    subgraph Analysis["Analysis Layer"]
        AEngine[Analysis Engine\npure SQL + Python stats]
        Analyst[LLM Analyst\noptional qualitative layer]
        Renderer[Renderer\nMarkdown + LaTeX dual output]
        Report[Report CLI]
    end

    Runner[Experiment Runner\nbatch orchestrator]

    State --> LLMActor
    State --> Actions
    State --> Resolver
    State --> Cascade
    State --> ECap
    State --> EPres
    Events --> LLMActor
    Events --> Loop
    RelGraph --> LLMActor
    WCap --> LLMActor
    WCap --> Validator
    WPres --> LLMActor
    WPres --> EventGen
    ECap --> WCap
    EPres --> WPres
    ProvBase --> ProvAnthropic
    ProvBase --> ProvOpenRouter
    ProvFactory --> LLMActor
    Perception --> LLMActor
    EventGen --> Loop
    ScenarioBase --> Taiwan
    Prompts --> Persona
    Persona --> LLMActor
    Actions --> Validator
    Actions --> Resolver
    Validator --> Loop
    Resolver --> Loop
    Cascade --> Loop
    LLMActor --> Loop
    Taiwan --> Loop
    Loop --> Fidelity
    Runner --> Loop
    Runner --> BCI
    BCI --> AEngine
    Fidelity --> AEngine
    AEngine --> Analyst
    AEngine --> Renderer
    Analyst --> Renderer
    Renderer --> Report
```

## Turn Lifecycle

```mermaid
sequenceDiagram
    participant Pool as Event Pool
    participant Engine as Simulation Engine
    participant Agent as State Agent
    participant LLM as LLM Provider
    participant Validator as Rule Validator
    participant Resolver as Turn Resolver
    participant Cascade
    participant Logger

    Engine->>Pool: generate events (tension + capability gated)
    Pool-->>Engine: 0–3 events

    loop Each State Actor
        Engine->>Agent: request action (world state snapshot)
        Agent->>Agent: apply perception filter (SHA-256 noise)
        Agent->>LLM: persona + doctrine + perceived state + actions
        LLM-->>Agent: reasoning trace + action call
        Agent->>Validator: validate action legality
        alt valid
            Validator-->>Agent: approved
        else invalid
            Validator-->>Agent: error feedback
            Agent->>LLM: retry with constraints (max 2x)
        end
        Agent-->>Engine: action + DecisionRecord
    end

    Engine->>Resolver: resolve all actions simultaneously
    Resolver-->>Engine: state deltas + turn events
    Engine->>Cascade: detect cascade triggers
    Cascade-->>Engine: cascade events
    Engine->>Logger: log turn (decisions · reasoning · state snapshot)
    Logger-->>Engine: done
    Engine->>Engine: check terminal conditions
```

---

## Doctrine Conditions

Six doctrine conditions control how actors reason. Assigned per run; the LLM must follow the framework explicitly.

| Condition | IR Theory | Core Logic |
|---|---|---|
| `baseline` | Rational Actor Model (Allison I) | Maximize expected utility. Explicit cost/benefit per action. |
| `realist` | Structural Realism (Waltz/Mearsheimer) | Relative power maximization. Survival first. Balance threats. |
| `liberal` | Liberal Institutionalism (Keohane) | Cooperation pays. Institutions and reputation constrain behaviour. |
| `constructivist` | Constructivism (Wendt) | Identity and norms drive action. Audience costs are real. |
| `prospect_theory` | Prospect Theory (Kahneman/Tversky) | Frame decisions as losses, not gains. Risk-acceptant when losing. |
| `organizational` | Organizational Process (Allison II) | Organizational routines constrain choices. SOPs dominate. |

---

## Action Space (32 actions)

| Category | Actions |
|---|---|
| Military | `mobilize` `strike` `advance` `withdraw` `blockade` `defensive_posture` `deploy_forward` |
| Diplomatic | `negotiate` `form_alliance` `condemn` `intel_sharing` `multilateral_appeal` `expel_diplomats` |
| Economic | `sanction` `embargo` `foreign_aid` `cut_supply` `asset_freeze` `supply_chain_diversion` |
| Information | `propaganda` `disinformation` `hack_and_leak` `intel_operation` |
| Coercive | `coercive_signaling` `nuclear_signaling` `hostage_taking` `proxy_support` |
| Legal | `lawfare_filing` |
| Standby | `hold_position` `monitor` `request_ceasefire` `war_termination` `alliance_burden_sharing` |

---

## Capability System

Each actor gets a 13-field capability vector derived from `WorldState` each turn. The LLM sees qualitative bands (HIGH / MEDIUM / LOW), never raw floats.

Fields: `conventional_strength` · `naval_power` · `air_superiority` · `nuclear_capability` · `logistics_capacity` · `readiness` · `amphibious_capacity` · `a2ad_effectiveness` · `economic_strength` · `energy_independence` · `industrial_capacity` · `domestic_stability` · `international_standing`

---

## Pressure System

Eight pressure dimensions track crisis dynamics independently of resource values.

Dimensions: `military_tension` · `economic_coercion` · `diplomatic_isolation` · `information_warfare` · `domestic_instability` · `alliance_fracture` · `nuclear_risk` · `crisis_instability`

---

## Taiwan Strait Scenario

Four actors. Starting phase: `tension`. Global tension: 0.55.

| Actor | Conv. Forces | Naval | Air | Econ | Stability |
|---|---|---|---|---|---|
| USA | 0.85 | 0.90 | 0.88 | 0.80 | 0.70 |
| PRC | 0.82 | 0.75 | 0.70 | 0.75 | 0.65 |
| TWN | 0.50 | 0.45 | 0.55 | 0.70 | 0.72 |
| JPN | 0.60 | 0.65 | 0.62 | 0.72 | 0.68 |

Values are illustrative research constructs, not real intelligence estimates.

---

## Cascade Rules

Automatic state mutations triggered after turn resolution.

| # | Trigger | Effect |
|---|---|---|
| 1 | Actor mobilizes | Adversary readiness +0.10 |
| 2 | Strike executed | Target conventional_forces −0.15, attacker readiness −0.05 |
| 3 | Advance into contested zone | global_tension +0.10, target defensive_posture likelihood↑ |
| 4 | Blockade active | Target economic −0.08/turn, global shipping disruption +0.05 |
| 5 | Nuclear signaling | global_tension +0.20, all actors readiness +0.15 |
| 6 | Alliance formed | Third-party threat perception shifts, tension adjusts |
| 7 | Negotiation accepted | global_tension −0.10 |
| 8 | Ceasefire accepted | crisis_phase → `post_conflict`, all readiness −0.20 |
| 9 | War termination | Final state snapshot, run ends |

---

## Measurement

**Doctrine Fidelity Score (DFS):** LLM-as-judge rubric. Each reasoning trace scored on 5 axes against the assigned doctrine. Scale 0–1.

**Behavioral Consistency Index (BCI):** Normalized entropy of action distributions across repeated runs of the same condition. Low BCI = high variance (doctrine not binding). High BCI = consistent behaviour.

---

## Running Experiments

```bash
# Single run
python -m cli.run --scenario taiwan_strait --doctrine realist --turns 15 --log-dir logs/runs/

# Compare doctrines, two providers
python -m experiments.runner \
  --scenarios taiwan_strait \
  --doctrines realist liberal constructivist baseline \
  --providers anthropic openrouter \
  --model-openrouter openai/gpt-4o \
  --turns 15 --runs-per-condition 3

# Query run log
sqlite3 logs/runs/run_latest.db "SELECT actor_id, action_type, turn FROM decisions ORDER BY turn, actor_id;"

# Generate analysis report
python -m analysis --run-dir logs/runs/ --output reports/ --format markdown
```

---

## Stack

| Component | Choice |
|---|---|
| Language | Python 3.11+ |
| Schema | Pydantic v2 |
| LLM (default) | `claude-sonnet-4-6` via Anthropic tool_use |
| Multi-provider | OpenRouter (OpenAI-compat) — 100+ models |
| Structured output | Tool/function calling — schema-enforced JSON |
| Logging | SQLite (stdlib) |
| CLI display | Rich |
| Dependency mgmt | `uv` + `pyproject.toml` |

---

## File Map

```
ose/
├── world/
│   ├── state.py          # WorldState · Actor · all Pydantic resource models
│   ├── events.py         # DecisionRecord · TurnLog · RunRecord
│   ├── graph.py          # RelationshipGraph bilateral query wrapper
│   ├── capabilities.py   # build_actor_capabilities() → 13-field vector
│   └── pressure.py       # ScenarioPressureModel · 8-dimension pressure state
│
├── providers/
│   ├── base.py           # LLMProvider ABC · ProviderCallResult dataclass
│   ├── anthropic_provider.py   # tool_use · input_schema · cache tokens
│   ├── openrouter_provider.py  # OpenAI-compat · function calling
│   └── factory.py        # build_provider() · require_provider_env()
│
├── actors/
│   ├── llm_actor.py      # Perception → CoT → provider.call() → retry → DecisionRecord
│   ├── persona.py        # build_persona_prompt() · 6 doctrine conditions
│   └── prompts/
│       ├── system.txt    # Actor identity · Simulation Research Contract
│       └── decision.txt  # Per-turn decision request · compliance anchor
│
├── engine/
│   ├── actions.py        # 32 typed action classes · ACTION_REGISTRY
│   ├── validator.py      # Capability-gated rule validator · pure logic
│   ├── resolver.py       # Simultaneous turn resolution · conflict adjudication
│   ├── cascade.py        # 9 cascade rules · escalatory + de-escalatory
│   ├── costs.py          # Per-action resource depletion
│   ├── perception.py     # Deterministic SHA-256 noise filter
│   ├── events.py         # Pressure + capability gated event generator
│   └── loop.py           # SimulationEngine · full turn lifecycle
│
├── scenarios/
│   ├── base.py           # ScenarioDefinition ABC
│   └── taiwan_strait.py  # 4-actor Taiwan Strait · pressure-gated event pool
│
├── scoring/
│   ├── fidelity.py       # Doctrine Fidelity Score · LLM-as-judge
│   └── bci.py            # Behavioral Consistency Index · entropy
│
├── experiments/
│   └── runner.py         # Batch orchestrator · multi-condition × multi-provider
│
├── analysis/
│   ├── engine.py         # Pure SQL + Python statistics
│   ├── analyst.py        # Optional Sonnet qualitative layer
│   ├── renderer.py       # Markdown + LaTeX dual output
│   └── report.py         # CLI entry point
│
├── cli/
│   └── run.py            # Entry point · --provider · --model · --doctrine flags
│
└── logs/
    └── logger.py         # SQLite-backed structured logger · full replay
```

---

## Known Limitations

- Non-determinism: even at temperature=0, OpenRouter models may vary between calls. BCI is designed to measure this.
- Action category mapping: new actions added in v0.4 must be manually added to the analysis engine's category map or they appear as `unknown`.
- No web UI. Terminal output via Rich only.
- Scenario pool is single-domain (Taiwan Strait). Framework is scenario-agnostic; adding scenarios requires implementing `ScenarioDefinition`.
- Replay fidelity: full prompt logging enables replay, but provider-side updates can change outputs over time.
