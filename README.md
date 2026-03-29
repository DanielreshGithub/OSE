# OSE — Omni-Simulation Engine

**Status:** Active | **Version:** v0.4

OSE is an LLM-driven geopolitical crisis simulation framework. Each actor is assigned an IR doctrine, chooses one action per turn from a constrained action menu, and the engine resolves all actions simultaneously against a bounded world state.

**Research thesis:** if you force the same model to reason through different doctrines, do you get measurably different crisis behavior?

## What OSE Does

- Runs a bounded multi-actor crisis simulation rather than open-ended roleplay.
- Assigns each run one doctrine condition: `realist`, `liberal`, `org_process`, `constructivist`, `marxist`, or `baseline`.
- Logs every decision, rationale, state snapshot, and outcome to SQLite.
- Generates Markdown / JSON / LaTeX reports from run logs.
- Supports Anthropic directly and OpenRouter for broad model coverage.

## Canonical Interface

Examples below use `python3 ose` from the repo root, which is the workflow this repo is built around.

After editable install, `ose` works the same way.

## Install

```bash
uv pip install -e ".[dev]"
cp .env.example .env
```

Add at least one provider key to `.env`:

- `ANTHROPIC_API_KEY` for Anthropic decision runs and LLM analytics
- `OPENROUTER_API_KEY` for OpenRouter models

## Quick Start

### Single Run

Anthropic default model:

```bash
python3 ose realist --turns 5
```

OpenRouter model:

```bash
python3 ose liberal openai/gpt-5.4 --turns 5 --seed 0
```

Another OpenRouter model:

```bash
python3 ose constructivist meta-llama/llama-4-maverick --turns 5 --seed 0
```

### Generate Reports

Basic report:

```bash
python3 ose reports --runs logs/runs --output reports/
```

Report with LLM narrative and LaTeX:

```bash
python3 ose reports --runs logs/runs --llm --latex --output reports/
```

### Batch Runs

```bash
python3 ose batch \
  --scenario taiwan_strait \
  --provider openrouter \
  --model openai/gpt-5.4 \
  --conditions realist liberal constructivist baseline \
  --runs 3 \
  --turns 5 \
  --skip-scoring \
  --skip-bci
```

## Launcher Rules

The top-level launcher is intentionally simple:

- `python3 ose <doctrine> [model] --turns N`
- `python3 ose reports ...`
- `python3 ose batch ...`

Provider inference:

- model string contains `/` -> defaults to `openrouter`
- model string without `/` -> defaults to `anthropic`

Examples:

```bash
python3 ose realist claude-sonnet-4-6 --turns 5
python3 ose marxist deepseek/deepseek-v3.2 --turns 5
python3 ose baseline x-ai/grok-4.20-beta --turns 5
```

## Doctrine Conditions

Each run uses one doctrine condition across all actors.

| Condition | IR Theory | Core Logic |
|---|---|---|
| `realist` | Structural Realism | Relative gains, survival, threat balancing, distrust of restraint |
| `liberal` | Liberal Institutionalism | Absolute gains, interdependence, institutions, reputation |
| `org_process` | Organizational Process | SOPs, bureaucratic inertia, satisficing, constrained menus |
| `constructivist` | Constructivism | Identity, legitimacy, norms, signaling, role behavior |
| `marxist` | Marxist / Radical IR | Dependency, hierarchy, capital autonomy, anti-hegemonic leverage |
| `baseline` | Rational Actor Model | Explicit expected utility, cost-benefit optimization |

## Action Space

OSE currently exposes `32` engine-validated actions.

| Category | Actions |
|---|---|
| Military | `mobilize` `strike` `advance` `withdraw` `blockade` `defensive_posture` `probe` `signal_resolve` `deploy_forward` |
| Diplomatic / Legal | `negotiate` `targeted_sanction` `comprehensive_sanction` `form_alliance` `condemn` `intel_sharing` `back_channel` `lawfare_filing` `multilateral_appeal` `expel_diplomats` |
| Economic | `embargo` `foreign_aid` `cut_supply` `technology_restriction` `asset_freeze` `supply_chain_diversion` |
| Information / Cyber | `propaganda` `partial_coercion` `cyber_operation` `hack_and_leak` |
| Nuclear | `nuclear_signal` |
| Standby | `hold_position` `monitor` |

The validator is rule-based. If a model produces an illegal or incompatible action, OSE retries and ultimately falls back to `hold_position` if necessary.

## Scenario Model

Current primary scenario:

- `taiwan_strait`

Default setting:

- 4 actors: `USA`, `PRC`, `TWN`, `JPN`
- initial phase: `tension`
- initial global tension: `0.55`
- open-ended pressure-gated event generation

OSE is bounded, not freeform:

- action menus are constrained
- capabilities are explicit
- event templates are authored and eligibility-gated
- world state transitions are engine-resolved

## Capability and Pressure Layers

Each actor gets a 13-field capability vector, shown to the model as qualitative bands:

`local_naval_projection`, `local_air_projection`, `missile_a2ad_capability`, `cyber_capability`, `intelligence_quality`, `economic_coercion_capacity`, `alliance_leverage`, `logistics_endurance`, `domestic_stability`, `war_aversion`, `escalation_tolerance`, `bureaucratic_flexibility`, `signaling_credibility`

Each turn also computes an 8-field pressure state:

`military_pressure`, `diplomatic_pressure`, `alliance_pressure`, `domestic_pressure`, `economic_pressure`, `informational_pressure`, `crisis_instability`, `uncertainty`

These drive:

- prompt shaping
- event eligibility
- action feasibility and downstream costs
- later analysis and comparison

## Outputs

### Run Logs

Single runs write SQLite logs to:

```text
logs/runs/<run_id>.db
```

Batch runs write per-experiment directories under:

```text
logs/experiments/<experiment_id>/
```

### Reports

Reports write to:

```text
reports/
```

Typical outputs:

- `*.md`
- `*.json`
- `*.tex` when `--latex` is enabled
- graph assets in a sibling `*_assets/` directory

## Useful Commands

Query actions from a run:

```bash
sqlite3 logs/runs/<run_id>.db \
  "SELECT turn, actor_short_name, json_extract(parsed_action, '$.action_type') AS action_type, validation_result FROM decisions ORDER BY turn, actor_short_name;"
```

Show available launcher modes:

```bash
python3 ose --help
python3 ose batch --help
python3 ose reports --help
```

## Analytics

OSE supports two main post-run measures:

- **Doctrine Fidelity Score (DFS)**: LLM-as-judge scoring of reasoning traces against the assigned doctrine
- **Behavioral Consistency Index (BCI)**: entropy-style consistency metric across repeated same-condition runs

Important note:

- BCI only makes sense when you have repeated runs for the same configuration
- single-run sweeps should be treated as qualitative / pilot comparisons, not BCI studies

### Anthropic Analytics Overrides

Analytics and DFS scoring use the Anthropic API directly.

You can override the analyst / scorer models with:

```bash
OSE_ANALYTICS_MODEL=claude-opus-4-6
OSE_SCORER_MODEL=claude-opus-4-6
OSE_ANALYST_MODEL=claude-opus-4-6
```

These use Anthropic-native model IDs, not OpenRouter-style names.

## Environment Defaults

The repo exposes a few runtime defaults through `.env`:

```bash
OSE_LOG_DIR=logs/runs
OSE_DEFAULT_TURNS=15
OSE_DEFAULT_TEMPERATURE=0
OSE_SCENARIO_SEED=0
```

OpenRouter compatibility tuning:

```bash
OSE_OPENROUTER_MAX_TOKENS=1024
OSE_OPENROUTER_JSON_MAX_TOKENS=384
```

## Advanced / Internal Entry Points

If you want to bypass the `ose` launcher, these still work:

```bash
python -m cli.run --help
python -m experiments.runner --help
python -m analysis --help
```

The launcher is the recommended public interface. The module entry points are lower-level.

## Repository Layout

```text
world/         core state, events, graph, capabilities, pressures
actors/        personas, prompts, LLM actor pipeline
engine/        actions, validator, resolver, loop, event generation
scenarios/     scenario definitions and event templates
providers/     Anthropic + OpenRouter adapters
experiments/   repeated-run batch orchestration
scoring/       DFS and BCI
analysis/      report extraction, graphs, rendering, LLM analysis
logs/          SQLite logger
cli/           launcher and lower-level CLIs
```

## Known Limitations

- OpenRouter compatibility varies by model and route. OSE has fallbacks, but not every model is equally reliable.
- Even at `temperature=0`, provider-side nondeterminism can still appear.
- The current benchmark focus is the Taiwan Strait scenario; the framework is extensible but still scenario-light.
- BCI is only meaningful for repeated same-model runs, not one-off model sweeps.
- Provider-side model updates can change outputs over time, even with identical prompts and seeds.
