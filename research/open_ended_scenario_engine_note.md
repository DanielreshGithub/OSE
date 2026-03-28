# Open-Ended Scenario Engine Note

## What Changed

OSE now supports bounded open-ended scenario evolution instead of relying mainly on a fixed stochastic event pool. The refactor adds:

- explicit actor capability vectors
- explicit scenario pressure state
- deterministic perception derived from seed + state + uncertainty
- pressure-conditioned typed event generation
- scenario-template support for open-ended crisis evolution
- seed-aware engine/runtime wiring
- expanded audit logging for pressures, event eligibility, perception packets, and terminal checks

The validator firewall remains in place. Actors still output typed actions, and the engine still owns world mutation.

## How Pressures Work

The engine now carries a structured pressure state with these dimensions:

- `military_pressure`
- `diplomatic_pressure`
- `alliance_pressure`
- `domestic_pressure`
- `economic_pressure`
- `informational_pressure`
- `crisis_instability`
- `uncertainty`

Pressures are derived from:

- current world state
- crisis phase
- systemic indicators
- recent actor actions
- recent generated or cascade events

The pressure computation is explicit and logged. Each turn stores:

- pressures before actor decisions
- pressures after resolution and cascades
- contribution metadata used to explain the change

This keeps scenario evolution inspectable rather than burying it inside prompt text.

## How Event Generation Works

Scenarios now define typed `EventTemplate` objects instead of a narrow authored turn script. Templates are evaluated against:

- current pressures
- crisis phase
- recent actions
- capability gates
- scenario-specific family weights

Only eligible typed events enter the candidate pool. The generator then samples from those candidates with a seed-stable RNG. Each turn logs:

- the pressure snapshot used for generation
- the evaluated candidates
- rejection reasons
- selected events
- event-family and provenance metadata

This makes scenario progression more open-ended without letting the model invent arbitrary world developments.

## How Capability Boundaries Are Enforced

Actors now have structured capability vectors that the engine derives from material and political state. These vectors are used to:

- shape action availability
- reject infeasible actions
- adjust action cost and tension impact
- enrich prompts with bounded qualitative capability summaries

The validator remains the enforcement point. The LLM still chooses from typed actions only, and those actions are checked against current world state plus capability constraints.

## Simplifying Assumptions That Remain

- capabilities are still coarse normalized abstractions, not detailed order-of-battle models
- theater geography is still simplified to zones and localities rather than full spatial simulation
- event generation remains scenario-ontology driven, not a generic geopolitical world model
- action effectiveness is still deliberately interpretable and limited in complexity
- timestamped log records are not designed as wall-clock replay artifacts; the deterministic target is simulation state evolution

## What This Refactor Still Does Not Solve

- It does not create realistic military campaign modeling. The action system is still an intentionally abstract crisis layer.
- It does not solve all ontology duplication yet. The scenario-side open-ended template layer and engine-side pressure/capability layer are aligned conceptually but are not fully unified into one shared representation.
- It does not eliminate all authored content. Scenario templates still define the event families and ontology; they are just no longer narrow story arcs.
- It does not make provider-side LLM responses cryptographically deterministic. The deterministic guarantee applies to seeded scenario evolution, perception noise, and engine-side state progression.
- It does not produce fully exhaustive audit diffs for every field mutation. The current audit trail is substantially better than before, but state mutation logging is still summarized rather than fully normalized.
