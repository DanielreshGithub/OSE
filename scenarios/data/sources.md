# Scenario Data Sources & Calibration Methodology

This document describes how the structured (numeric) and narrative (textual) inputs to the Taiwan Strait scenario are derived from open sources. The goal is auditability: anyone reviewing the scenario should be able to trace a number or claim back to a public source family, and re-derive it from current data on the next review cycle.

## Two Layers of Inputs

OSE actor models consume two kinds of inputs that should be sourced separately:

**1. Structured capabilities (numeric, [0.0, 1.0])**

Fields in `MilitaryResources`, `EconomicResources`, `PoliticalResources`, `TerritoryControl`, `BilateralRelationship`, `SystemicIndicators`. These are normalized capability scores. They drive `CapabilityVector` derivation, action gating, and perception bands.

**2. Narrative grounding (long-form text)**

Fields on `Actor`: `ideology`, `strategic_culture`, `decision_style`, `historical_precedents`, `institutional_constraints`, `cognitive_patterns`, `war_aversion`, `military_doctrine_narrative`. These shape the LLM system prompt and constrain behavior toward observed patterns.

Both layers should be sourced. This document covers methodology; per-actor doctrine narratives live in `doctrine_USA.md`, `doctrine_PRC.md`, `doctrine_TWN.md`, `doctrine_JPN.md`.

## Authoritative Open Sources by Domain

| Domain | Primary source family | Update cadence |
|---|---|---|
| Military force structure (all actors) | IISS *The Military Balance* (annual) | Yearly |
| Defense spending | SIPRI Military Expenditure Database | Yearly |
| PRC force structure & doctrine | US DoD *Annual Report to Congress: Military and Security Developments Involving the PRC* (CMPR) | Yearly |
| PRC doctrinal writings | PLA Academy of Military Science *Science of Military Strategy* (战略学), translated editions; National Defense University publications | Periodic |
| US doctrine | DoD Joint Publication series (JP 3-0 family); National Defense Strategy; INDOPACOM posture statements | NDS quadrennial, posture annual |
| Taiwan force structure & doctrine | ROC MND Quadrennial Defense Review; National Defense Report | Quadrennial / biennial |
| Japan force structure & doctrine | Japan MOD *Defense of Japan* whitepaper; National Security Strategy 2022 | Annual whitepaper |
| Nuclear forces | FAS *Nuclear Notebook* (Bulletin of the Atomic Scientists); SIPRI Yearbook chapter on world nuclear forces | Periodic |
| Casualty tolerance | Pew Research Center, Gallup, CCAP (Asian Barometer) polling | Periodic |
| Alliance cohesion | Pew international polling; Lowy Institute Asia Power Index | Annual / periodic |
| Economic dependency | World Bank, IMF, OECD; UN Comtrade for bilateral trade; supply-chain analysis from CSIS, CNAS, RAND | Annual |
| Semiconductor supply chain | SEMI World Fab Forecast; SIA reports; CSIS semiconductor analyses | Quarterly / annual |

## Calibration Notes — Current Numeric Inputs

The `MilitaryResources` floats currently hardcoded in `scenarios/taiwan_strait.py` reflect author judgment as of approximately 2024–2025, with limited explicit sourcing. They are *directionally* defensible (inter-actor rankings match open consensus) but lack a documented derivation rule for any individual field. Confidence by actor:

| Actor | Confidence | Specific concerns |
|---|---|---|
| USA | MEDIUM-HIGH | Inventory data is widely public; key calibration question is *forward-deployed capacity in WestPac*, not total inventory. Current `amphibious_capacity=0.30` correctly reflects that USA does not need amphibious for this scenario. |
| PRC | MEDIUM | Numbers track DoD CMPR directional consensus, but `amphibious_capacity=0.78` may overstate current opposed-landing capacity (open analyses suggest ~30+ LHD/LPD + civilian RoRo would be needed for a Taiwan-scale op; PRC has ~3 Type 075 + ~8 Type 071). Suggested review: 0.55–0.65 for current force, trending up. `nuclear_capability=0.80` overstates current arsenal ratio (DoD CMPR estimates PRC ~500 warheads vs. US ~1700 deployed) but maps better to projected 2030 force. |
| TWN | MEDIUM | `a2ad_effectiveness=0.68` is defensible for the ODC-mature force, but ODC implementation is incomplete. Real 2024 a2ad effectiveness may be 0.55, projected 2027–2030 reaching 0.70. |
| JPN | MEDIUM | JMSDF naval ratings track open consensus. `casualty_tolerance=0.35` is a judgment call without polling data citation; defensible but should be sourced against current Japanese public opinion data. |

**Action item** (deferred to a future calibration session): introduce a per-field source citation in scenario code, e.g.:

```python
naval_power=0.76,  # PRC. Source: IISS Military Balance 2024 + DoD CMPR 2024. Reviewed 2026-05.
```

This keeps the audit trail in-line. Alternatively, externalize to `scenarios/data/capabilities_<year>.json` once the doctrine layer is stable.

## Calibration Notes — Narrative Doctrine

Per-actor doctrine narratives (`doctrine_*.md`) are written to one consistent template:

1. **Doctrine summary** (1–2 paragraphs) — high-level operational concept.
2. **Revealed Patterns** (10 items) — observable behavioral patterns anchored in widely-documented historical operations.
3. **Operational Tempo** — pace and timing pattern.
4. **Rules of Engagement** — restrictiveness level and characteristic limits.
5. **Anti-Patterns** — what this actor doctrinally would *not* do.
6. **Action-Type Bias (qualitative)** — preferred and avoided action categories from the OSE 32-action registry.
7. **Sources** — organization-level only; specific paper IDs only cited when the paper is canonically known.

**Important caveat on doctrine claims.** Doctrine narratives describe *revealed* patterns from historical observation. Two limitations:

- For PRC, observed combat history is thin (1979 Sino-Vietnamese, 2020 Galwan, plus exercises). Many doctrinal claims are inferred from doctrinal writings + exercises rather than from actual combat performance. This gap is explicit in the PRC doctrine file ("untested at scale").
- For all actors, doctrine evolves. The 2003 OIF US is not the 2025 INDOPACOM-postured US. The narratives note shifts where relevant (e.g., AirSea Battle → JAM-GC for USA, 2022 NSS for Japan) but cannot capture every revision.

**Citations are organization-level by design.** Naming specific reports without high-confidence access to them risks fabrication. The source lists name *which organization to consult* (RAND, CSIS, DoD CMPR, MOD whitepapers) rather than fabricating paper titles or URLs.

## Review Cadence

| Cycle | Trigger | What to update |
|---|---|---|
| Annual | New IISS Military Balance / DoD CMPR / MOD whitepaper publication | Numeric capabilities, doctrine narrative footnotes |
| Per-event | Major posture shift (e.g., 2022 NSS in Japan; ODC reform in Taiwan) | Doctrine narrative; affected capability fields |
| Per-scenario | New scenario added (e.g. Iran, Korea, Arctic) | New `doctrine_<ACTOR>.md` files following the same template |

## Known Open Questions

- Should `MilitaryResources` floats be externalized to versioned JSON? Pro: clean audit, easy diff across years. Con: indirection cost, harder to read scenario code. Defer until v1 of doctrine layer ships.
- Should a "year horizon" parameter (2026 baseline vs ~2030 projected) be added to `TaiwanStraitScenario.__init__`? Useful for capability-shift sensitivity analysis. Deferred from this pass.
- Should there be a *doctrine consistency scorer* analogous to the existing `scoring/fidelity.py` IR-doctrine scorer? Could score whether an actor's chosen actions align with its revealed military doctrine. Promising but out of scope here.

## Provenance Note

This document and the four doctrine narrative files were drafted as part of the OSE operational-realism work in May 2026. They reflect the author's reading of the cited source families and should not be treated as authoritative on any individual factual claim. The purpose is *prompt-shaping* — to push LLM actors toward behavior consistent with observed patterns — not to produce a peer-reviewed military assessment.

For any claim that materially affects scenario outcome, verify against the cited primary source before relying on it.
