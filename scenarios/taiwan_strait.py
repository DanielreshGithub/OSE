"""
Taiwan Strait Crisis 2026 — open-ended scenario template.

The scenario now evolves from state-dependent pressures and typed event
templates rather than a narrowly scripted event pool. The world remains
bounded: actors, capabilities, and event families are still explicitly
constrained by the state and by deterministic eligibility rules.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any

from engine.event_generation import CapabilityGate, EventTemplate, PressureGate
from engine.scenario_template import OpenEndedScenarioTemplate
from world.state import (
    WorldState, Actor, MilitaryResources, EconomicResources,
    PoliticalResources, TerritoryControl, BilateralRelationship,
    SystemicIndicators, RedLine,
)
from scenarios.base import ScenarioDefinition


_ALL_ACTORS = ["USA", "PRC", "TWN", "JPN"]

def _pg(pressure: str, min_value: float, max_value: float = 1.0, weight: float = 1.0) -> PressureGate:
    return PressureGate(pressure=pressure, min_value=min_value, max_value=max_value, weight=weight)


def _cg(actor: str, capability: str, min_value: float, weight: float = 1.0) -> CapabilityGate:
    return CapabilityGate(actor=actor, capability=capability, min_value=min_value, weight=weight)


class TaiwanStraitScenario(ScenarioDefinition, OpenEndedScenarioTemplate):

    def build_initial_state(self) -> WorldState:
        actors = {
            "USA": self._build_usa(),
            "PRC": self._build_prc(),
            "TWN": self._build_twn(),
            "JPN": self._build_jpn(),
        }
        relationships = self._build_relationships()
        systemic = SystemicIndicators(
            semiconductor_supply_chain_integrity=0.85,
            global_shipping_disruption=0.08,
            energy_market_volatility=0.18,
            alliance_system_cohesion=0.78,
        )
        return WorldState(
            scenario_id="taiwan_strait_2026",
            scenario_name="Taiwan Strait Crisis 2026",
            actors=actors,
            relationships=relationships,
            systemic=systemic,
            global_tension=0.55,
            crisis_phase="tension",
            max_turns=15,
        )

    def initialize(self) -> WorldState:
        return OpenEndedScenarioTemplate.initialize(self)

    def get_turn_events(self, turn: int, state: WorldState):
        return OpenEndedScenarioTemplate.get_turn_events(self, turn, state)

    def build_pressure_coefficients(self) -> Dict[str, Dict[str, float]]:
        return {
            "military_pressure": {
                "global_tension": 0.30,
                "military_heat": 0.25,
                "theater_pressure": 0.20,
                "recent_military": 0.15,
                "uncertainty_burst": 0.10,
            },
            "diplomatic_pressure": {
                "diplomatic_fragmentation": 0.30,
                "alliance_strain": 0.20,
                "recent_diplomatic": 0.20,
                "uncertainty_burst": 0.10,
                "global_tension": 0.20,
            },
            "alliance_pressure": {
                "alliance_strain": 0.35,
                "recent_military": 0.20,
                "recent_diplomatic": 0.15,
                "theater_pressure": 0.15,
                "uncertainty_burst": 0.15,
            },
            "domestic_pressure": {
                "domestic_fragility": 0.35,
                "recent_military": 0.20,
                "recent_information": 0.15,
                "economic_stress": 0.15,
                "global_tension": 0.15,
            },
            "economic_pressure": {
                "economic_stress": 0.40,
                "recent_economic": 0.25,
                "alliance_strain": 0.15,
                "global_tension": 0.20,
            },
            "information_pressure": {
                "information_fog": 0.40,
                "recent_information": 0.25,
                "recent_ambiguity": 0.20,
                "theater_pressure": 0.15,
            },
            "crisis_instability": {
                "global_tension": 0.35,
                "military_heat": 0.25,
                "economic_stress": 0.15,
                "alliance_strain": 0.15,
                "uncertainty_burst": 0.10,
            },
            "uncertainty": {
                "information_fog": 0.45,
                "recent_ambiguity": 0.25,
                "theater_pressure": 0.15,
                "recent_information": 0.15,
            },
        }

    def build_family_weights(self) -> Dict[str, float]:
        return {
            "gray_zone_incident": 1.10,
            "military_signal": 1.00,
            "diplomatic_signal": 1.00,
            "domestic_shock": 0.95,
            "alliance_coordination": 1.05,
            "economic_disruption": 0.92,
            "information_revelation": 1.00,
            "neutral_disturbance": 0.85,
        }

    def build_scenario_context(self, state: WorldState, pressures) -> Dict[str, Any]:
        return {
            "theater": "taiwan_strait",
            "base_event_budget": 1,
            "scenario_bias": 0.03 if pressures.crisis_instability >= 0.5 else 0.0,
        }

    def max_events_per_turn(self) -> int:
        return 3

    def build_event_templates(self) -> List[EventTemplate]:
        return [
            EventTemplate(
                event_id="prc_naval_probe",
                family="gray_zone_incident",
                category="military",
                description=(
                    "PLAN warship enters Taiwan's contiguous zone without warning. "
                    "TWN Coast Guard issues alert; US INDOPACOM raises watch level."
                ),
                caused_by_actor="PRC",
                affected_actors=_ALL_ACTORS,
                base_weight=0.20,
                pressure_gates=[
                    _pg("military_pressure", 0.35),
                    _pg("crisis_instability", 0.25),
                ],
                capability_gates=[
                    _cg("PRC", "local_naval_projection", 0.45),
                    _cg("PRC", "signaling_credibility", 0.25),
                ],
                phase_bias=["tension", "crisis"],
                recent_action_bias={"mobilize": 0.10, "signal_resolve": 0.08},
                world_state_delta={"global_tension_delta": 0.05},
            ),
            EventTemplate(
                event_id="prc_missile_test",
                family="military_signal",
                category="military",
                description=(
                    "PLA Rocket Force conducts ballistic missile test, with impact zones "
                    "north and south of Taiwan. US Strategic Command issues a terse statement."
                ),
                caused_by_actor="PRC",
                affected_actors=_ALL_ACTORS,
                base_weight=0.14,
                pressure_gates=[
                    _pg("military_pressure", 0.50),
                    _pg("crisis_instability", 0.35),
                ],
                capability_gates=[
                    _cg("PRC", "missile_a2ad", 0.65),
                    _cg("PRC", "local_air_projection", 0.35),
                ],
                phase_bias=["tension", "crisis"],
                recent_action_bias={"strike": 0.12, "mobilize": 0.10},
                world_state_delta={"global_tension_delta": 0.07},
            ),
            EventTemplate(
                event_id="prc_state_media_escalation",
                family="information_revelation",
                category="information",
                description=(
                    "PRC state media publishes an editorial asserting reunification "
                    "'cannot wait indefinitely,' widely read as leadership impatience."
                ),
                caused_by_actor="PRC",
                affected_actors=["USA", "TWN", "JPN"],
                base_weight=0.18,
                pressure_gates=[
                    _pg("information_pressure", 0.30),
                    _pg("military_pressure", 0.20),
                ],
                capability_gates=[
                    _cg("PRC", "signaling_credibility", 0.20),
                ],
                phase_bias=["tension", "crisis"],
                recent_action_bias={"propaganda": 0.14, "cyber_operation": 0.08},
                world_state_delta={"global_tension_delta": 0.04},
            ),
            EventTemplate(
                event_id="us_carrier_presence",
                family="military_signal",
                category="military",
                description=(
                    "US Navy carrier strike group transits the Taiwan Strait in a "
                    "freedom-of-navigation operation. PRC lodges a formal protest."
                ),
                caused_by_actor="USA",
                affected_actors=_ALL_ACTORS,
                base_weight=0.16,
                pressure_gates=[
                    _pg("alliance_pressure", 0.30),
                    _pg("military_pressure", 0.30),
                ],
                capability_gates=[
                    _cg("USA", "local_naval_projection", 0.55),
                    _cg("USA", "signaling_credibility", 0.45),
                ],
                phase_bias=["tension", "crisis"],
                recent_action_bias={"signal_resolve": 0.10, "mobilize": 0.08},
                world_state_delta={"global_tension_delta": 0.05},
            ),
            EventTemplate(
                event_id="prc_cyber_probe",
                family="information_revelation",
                category="information",
                description=(
                    "Suspected PRC cyber operation targets Taiwan power grid. "
                    "Power disruptions are reported in northern Taiwan."
                ),
                caused_by_actor="PRC",
                affected_actors=["TWN", "USA"],
                base_weight=0.15,
                pressure_gates=[
                    _pg("information_pressure", 0.40),
                    _pg("uncertainty", 0.35),
                ],
                capability_gates=[
                    _cg("PRC", "cyber_capability", 0.45),
                ],
                phase_bias=["tension", "crisis"],
                recent_action_bias={"cyber_operation": 0.12, "probe": 0.06},
                world_state_delta={"global_tension_delta": 0.04},
            ),
            EventTemplate(
                event_id="us_arms_transfer",
                family="diplomatic_signal",
                category="diplomatic",
                description=(
                    "US Congress authorizes additional arms transfers to Taiwan after "
                    "an expedited committee review."
                ),
                caused_by_actor="USA",
                affected_actors=_ALL_ACTORS,
                base_weight=0.13,
                pressure_gates=[
                    _pg("alliance_pressure", 0.35),
                    _pg("domestic_pressure", 0.15),
                ],
                capability_gates=[
                    _cg("USA", "alliance_leverage", 0.45),
                    _cg("USA", "domestic_stability", 0.45),
                ],
                recent_action_bias={"condemn": 0.08, "signal_resolve": 0.10},
                world_state_delta={"global_tension_delta": 0.04},
            ),
            EventTemplate(
                event_id="back_channel",
                family="diplomatic_signal",
                category="diplomatic",
                description=(
                    "US and PRC senior officials hold an unannounced back-channel call. "
                    "Both sides confirm a frank exchange with no joint statement."
                ),
                caused_by_actor=None,
                affected_actors=["USA", "PRC"],
                base_weight=0.18,
                pressure_gates=[
                    _pg("diplomatic_pressure", 0.30),
                    _pg("uncertainty", 0.25),
                ],
                capability_gates=[
                    _cg("USA", "signaling_credibility", 0.35),
                    _cg("PRC", "signaling_credibility", 0.25),
                ],
                recent_action_bias={"negotiate": 0.15, "back_channel": 0.12},
                world_state_delta={"global_tension_delta": -0.04},
            ),
            EventTemplate(
                event_id="asean_restraint",
                family="diplomatic_signal",
                category="diplomatic",
                description=(
                    "ASEAN foreign ministers issue a joint statement calling for "
                    "'maximum restraint' and reaffirming UNCLOS."
                ),
                caused_by_actor=None,
                affected_actors=_ALL_ACTORS,
                base_weight=0.16,
                pressure_gates=[
                    _pg("diplomatic_pressure", 0.20),
                    _pg("alliance_pressure", 0.20),
                ],
                recent_action_bias={"negotiate": 0.10, "intel_sharing": 0.08},
                world_state_delta={"global_tension_delta": -0.03},
            ),
            EventTemplate(
                event_id="g7_communique",
                family="alliance_coordination",
                category="diplomatic",
                description=(
                    "G7 foreign ministers issue a joint communiqué calling for a "
                    "peaceful resolution consistent with the wishes of Taiwan's people."
                ),
                caused_by_actor=None,
                affected_actors=_ALL_ACTORS,
                base_weight=0.11,
                pressure_gates=[
                    _pg("alliance_pressure", 0.25),
                    _pg("domestic_pressure", 0.15),
                ],
                capability_gates=[
                    _cg("USA", "alliance_leverage", 0.40),
                ],
                recent_action_bias={"intel_sharing": 0.08, "form_alliance": 0.10},
                world_state_delta={"global_tension_delta": -0.03},
            ),
            EventTemplate(
                event_id="twn_dialogue_signal",
                family="diplomatic_signal",
                category="diplomatic",
                description=(
                    "Taiwan's president signals openness to cross-strait economic dialogue "
                    "without preconditions."
                ),
                caused_by_actor="TWN",
                affected_actors=["PRC", "USA"],
                base_weight=0.10,
                pressure_gates=[
                    _pg("diplomatic_pressure", 0.30),
                    _pg("domestic_pressure", 0.25),
                ],
                capability_gates=[
                    _cg("TWN", "signaling_credibility", 0.35),
                ],
                phase_bias=["tension"],
                recent_action_bias={"negotiate": 0.12, "back_channel": 0.08},
                world_state_delta={"global_tension_delta": -0.04},
            ),
            EventTemplate(
                event_id="us_prc_hotline",
                family="diplomatic_signal",
                category="diplomatic",
                description=(
                    "US and PRC direct military-to-military hotline call is confirmed "
                    "by both defense ministries."
                ),
                caused_by_actor=None,
                affected_actors=["USA", "PRC"],
                base_weight=0.16,
                pressure_gates=[
                    _pg("uncertainty", 0.35),
                    _pg("diplomatic_pressure", 0.25),
                ],
                capability_gates=[
                    _cg("USA", "signaling_credibility", 0.35),
                    _cg("PRC", "signaling_credibility", 0.25),
                ],
                recent_action_bias={"negotiate": 0.12, "intel_sharing": 0.10},
                world_state_delta={"global_tension_delta": -0.03},
            ),
            EventTemplate(
                event_id="domestic_media_pressure",
                family="domestic_shock",
                category="information",
                description=(
                    "International media coverage of the Taiwan Strait crisis intensifies. "
                    "Domestic political pressure mounts in all capitals for visible action."
                ),
                caused_by_actor=None,
                affected_actors=_ALL_ACTORS,
                base_weight=0.18,
                pressure_gates=[
                    _pg("domestic_pressure", 0.35),
                    _pg("information_pressure", 0.25),
                ],
                recent_action_bias={"propaganda": 0.12, "condemn": 0.10},
                world_state_delta={"global_tension_delta": 0.02},
            ),
            EventTemplate(
                event_id="oil_shock",
                family="economic_disruption",
                category="economic",
                description=(
                    "Global oil prices spike on an unrelated Middle East supply disruption. "
                    "All parties face increased economic pressure."
                ),
                caused_by_actor=None,
                affected_actors=_ALL_ACTORS,
                base_weight=0.10,
                pressure_gates=[
                    _pg("economic_pressure", 0.35),
                    _pg("crisis_instability", 0.20),
                ],
                recent_action_bias={"embargo": 0.08, "technology_restriction": 0.06},
                world_state_delta={"global_tension_delta": 0.02},
            ),
            EventTemplate(
                event_id="earthquake_taiwan",
                family="neutral_disturbance",
                category="natural",
                description=(
                    "A magnitude 6.1 earthquake strikes eastern Taiwan. Domestic emergency "
                    "response mobilized; cross-strait military activity temporarily slows."
                ),
                caused_by_actor=None,
                affected_actors=["TWN"],
                base_weight=0.07,
                pressure_gates=[
                    _pg("uncertainty", 0.10),
                    _pg("domestic_pressure", 0.15),
                ],
                world_state_delta={"global_tension_delta": -0.02},
            ),
            EventTemplate(
                event_id="intelligence_contradiction",
                family="information_revelation",
                category="information",
                description=(
                    "Competing intelligence assessments emerge about PRC posture. "
                    "Some channels indicate restraint; others warn of coercive intent."
                ),
                caused_by_actor=None,
                affected_actors=_ALL_ACTORS,
                base_weight=0.11,
                pressure_gates=[
                    _pg("uncertainty", 0.45),
                    _pg("information_pressure", 0.30),
                ],
                recent_action_bias={"probe": 0.08, "cyber_operation": 0.08},
                world_state_delta={"global_tension_delta": 0.01},
            ),
            EventTemplate(
                event_id="exercise_wrapup",
                family="military_signal",
                category="military",
                description=(
                    "PRC confirms that major naval exercises are concluding and that "
                    "participating vessels are returning to home ports."
                ),
                caused_by_actor="PRC",
                affected_actors=_ALL_ACTORS,
                base_weight=0.12,
                pressure_gates=[
                    _pg("military_pressure", 0.30),
                    _pg("diplomatic_pressure", 0.15),
                ],
                capability_gates=[
                    _cg("PRC", "local_naval_projection", 0.40),
                ],
                recent_action_bias={"withdraw": 0.10, "negotiate": 0.08},
                world_state_delta={"global_tension_delta": -0.05},
            ),
            EventTemplate(
                event_id="alliance_coordination",
                family="alliance_coordination",
                category="diplomatic",
                description=(
                    "Japan and the United States activate the alliance coordination "
                    "mechanism to synchronize monitoring and messaging."
                ),
                caused_by_actor=None,
                affected_actors=["USA", "JPN"],
                base_weight=0.10,
                pressure_gates=[
                    _pg("alliance_pressure", 0.40),
                    _pg("diplomatic_pressure", 0.20),
                ],
                capability_gates=[
                    _cg("JPN", "alliance_leverage", 0.45),
                    _cg("USA", "alliance_leverage", 0.45),
                ],
                recent_action_bias={"intel_sharing": 0.12, "signal_resolve": 0.08},
                world_state_delta={"global_tension_delta": -0.02},
            ),
        ]

    # ── Actor Definitions ─────────────────────────────────────────────────────

    def _build_usa(self) -> Actor:
        return Actor(
            name="United States of America",
            short_name="USA",
            actor_type="state",
            military=MilitaryResources(
                conventional_forces=0.85,
                naval_power=0.90,
                air_superiority=0.88,
                nuclear_capability=0.95,
                logistics_capacity=0.80,
                readiness=0.70,
                # Low amphibious capacity: USA doesn't need to invade anyone in this scenario;
                # it projects deterrence through carrier strike groups and air assets
                amphibious_capacity=0.30,
                # Moderate A2/AD: strong globally but operating at end of supply lines in W. Pacific
                a2ad_effectiveness=0.52,
            ),
            economic=EconomicResources(
                gdp_strength=0.82,
                foreign_reserves=0.78,
                energy_independence=0.68,
                trade_openness=0.72,
                industrial_capacity=0.85,
                # USA is exposed to Taiwan semiconductor supply — 90%+ of advanced chips
                semiconductor_dependency=0.62,
            ),
            political=PoliticalResources(
                domestic_stability=0.68,
                regime_legitimacy=0.72,
                international_standing=0.82,
                decision_unity=0.62,     # Divided government constrains rapid commitment
                casualty_tolerance=0.42,  # Low post-Iraq/Afghanistan public tolerance
            ),
            territory=TerritoryControl(
                core_territory=0.98,
                contested_zones={"taiwan_strait": 0.72},  # Effective access, not control
                strategic_straits={"luzon_strait": 0.80, "miyako_strait": 0.65},
            ),
            goals=[
                "Maintain US-led rules-based international order and regional stability",
                "Deter PRC military aggression against Taiwan through credible commitment",
                "Preserve alliance credibility with Japan and regional partners",
                "Avoid direct US-PRC military conflict while defending vital interests",
                "Protect global semiconductor supply chains from disruption",
            ],
            red_lines=[
                RedLine(
                    description="PRC amphibious invasion of Taiwan",
                    trigger_condition="PRC executes advance action targeting TWN core territory with high amphibious capacity",
                    if_crossed="Direct US military intervention authorized; carrier strike group engagement",
                ),
                RedLine(
                    description="PRC strike on US military forces or territory",
                    trigger_condition="PRC executes strike action with actor_id=PRC targeting USA forces",
                    if_crossed="Full US military response; alliance Article 5 invocation",
                ),
                RedLine(
                    description="Nuclear first use by any party",
                    trigger_condition="Any actor with nuclear_capability > 0.5 executes strike at high intensity against nuclear-armed state",
                    if_crossed="Nuclear response posture activated; full escalation",
                ),
            ],
            ideology=(
                "Liberal democratic hegemon committed to rules-based international order, "
                "open markets, freedom of navigation, and alliance-based collective security. "
                "Views PRC as a revisionist challenger to the US-led order."
            ),
            strategic_culture=(
                "Prefers coalition-building, credible deterrence through forward presence, "
                "graduated escalation ladders, and multilateral legitimacy before unilateral action. "
                "Strong institutional inertia — decisions require interagency consensus."
            ),
            decision_style=(
                "Deliberate and process-driven; coalition-seeking before commitment; "
                "slow to escalate but decisive when threshold is clearly crossed. "
                "Highly sensitive to domestic political constraints and casualty tolerance."
            ),
            war_aversion=(
                "CASUALTIES AND DOMESTIC POLITICS: A US-PRC war would produce American combat "
                "deaths on a scale not seen since Korea. Unlike Iraq or Afghanistan, PRC has "
                "the capacity to sink US warships — a single carrier strike group lost means "
                "5,000+ dead in a day. The American public has not absorbed casualties at that "
                "scale in a generation. The political fallout would be immediate and severe. "
                "Any president who leads the US into a war over Taiwan must believe they can "
                "sustain public support through significant losses — and recent history says "
                "that support collapses fast.\n\n"
                "ECONOMIC DEVASTATION: A US-PRC war would be the first conflict between two "
                "nuclear-armed economies deeply intertwined through trade. Immediate consequences: "
                "semiconductor supply collapse (90%+ of advanced chips gone), $2+ trillion in "
                "bilateral trade disrupted, US Treasury securities held by PRC ($800B+) weaponized, "
                "global supply chain breakdown. The US economy would enter a severe recession "
                "within weeks. The dollar's reserve currency status would be tested.\n\n"
                "NUCLEAR ESCALATION RISK: PRC has a growing nuclear arsenal and a declared NFU "
                "policy, but NFU is a peacetime posture — under existential regime threat, all "
                "doctrines are revisable. Any US conventional strike on PRC homeland territory "
                "risks crossing the nuclear threshold. This is not a theoretical risk; it is "
                "the central constraint on US military planning in the Western Pacific.\n\n"
                "ALLIANCE SYSTEM STRESS: A war that goes badly — or even one that goes well but "
                "at high cost — would strain the alliance system. NATO allies would face pressure "
                "to support or distance. A protracted conflict would test whether the liberal "
                "international order survives the very war fought to defend it."
            ),
            historical_precedents=(
                "THIRD TAIWAN STRAIT CRISIS (1995-96): PRC conducted missile tests bracketing "
                "Taiwan. US responded by deploying two carrier strike groups (USS Nimitz, USS "
                "Independence) through the Strait — the largest US naval deployment in the Pacific "
                "since Vietnam. This established the template: US does not pre-position forces "
                "in anticipation; it surges them in response to PRC provocation. The deployment "
                "was authorized at the presidential level after interagency debate, not by "
                "theater commanders acting on standing orders.\n\n"
                "EP-3 INCIDENT (2001): PRC fighter collided with US surveillance aircraft over "
                "Hainan. US prioritized crew recovery over escalation. Accepted a carefully "
                "worded quasi-apology (saying 'very sorry' without accepting fault) to secure "
                "crew release. Pattern: US will absorb tactical humiliation to avoid strategic "
                "escalation, but sets firm limits on how far it will bend.\n\n"
                "SENKAKU/DIAOYU INCIDENTS (2010-2013): When PRC pressured Japan over the "
                "Senkakus, US explicitly stated Article 5 covers the islands — extending "
                "deterrent commitment in public. But did not deploy additional forces. Pattern: "
                "US prefers declaratory deterrence (public statements) before force deployment.\n\n"
                "PELOSI TAIWAN VISIT (2022): Despite PRC threats of 'serious consequences,' US "
                "did not cancel the visit but also did not send a carrier directly into the Strait "
                "during PRC exercises. Pattern: US does not acquiesce to PRC coercion but calibrates "
                "response to avoid giving PRC a casus belli."
            ),
            institutional_constraints=(
                "NATIONAL SECURITY COUNCIL PROCESS: All major decisions on Taiwan require NSC "
                "Principals Committee review. The Secretary of Defense, Secretary of State, "
                "Chairman of the Joint Chiefs, and DNI all have equities. No single official — "
                "not even the President — typically acts on Taiwan without this process. This "
                "creates a 24-72 hour decision lag for novel situations.\n\n"
                "CONGRESSIONAL AUTHORIZATION: The Taiwan Relations Act (1979) commits the US to "
                "provide Taiwan with 'arms of a defensive character' and to maintain US capacity "
                "to resist coercion. It does NOT commit the US to military intervention. Any "
                "decision to use force requires either Congressional authorization (slow) or "
                "presidential invocation of Article II authority (faster but politically costly). "
                "Strategic ambiguity is not a bug — it is the policy.\n\n"
                "COMBATANT COMMAND STRUCTURE: USINDOPACOM executes in the Western Pacific but "
                "does not decide policy. The commander can reposition forces within existing "
                "authorities but cannot initiate offensive operations without National Command "
                "Authority approval. Force deployment decisions involve TRANSCOM for strategic "
                "lift, which adds days to response timelines.\n\n"
                "ALLIANCE CONSULTATION: US is treaty-bound to consult Japan before taking "
                "military action that could trigger Article 5 obligations. Failure to consult "
                "damages alliance credibility — the very thing the US is trying to protect."
            ),
            cognitive_patterns=(
                "STATUS QUO BIAS: US decision-makers consistently overweight the cost of action "
                "relative to the cost of inaction. In ambiguous situations, the institutional "
                "default is to 'monitor and assess' rather than act. This bias is strongest when "
                "the intelligence picture is uncertain.\n\n"
                "DETERRENCE OVERCONFIDENCE: US frequently assumes its military superiority is "
                "self-evidently deterring. The belief that 'PRC knows we would respond' persists "
                "even when US signals are ambiguous. This can lead to under-signaling — assuming "
                "deterrence is working when the adversary reads US caution as weakness.\n\n"
                "CASUALTY SENSITIVITY: Post-Iraq, post-Afghanistan, the US political system has "
                "extremely low tolerance for combat casualties in conflicts that are not perceived "
                "as existential. Any scenario where US servicemembers die triggers immediate "
                "domestic political pressure that constrains further escalation. PRC is aware of "
                "this and may try to exploit it.\n\n"
                "MIRROR IMAGING ON RATIONALITY: US analysts tend to assume PRC decision-makers "
                "are rational utility maximizers who will 'see reason' given sufficient deterrent "
                "threat. This underestimates the role of face, domestic legitimacy pressure, and "
                "nationalist emotion in PRC decision-making.\n\n"
                "COALITION DEPENDENCY: US decision-makers are psychologically reluctant to act "
                "unilaterally. They prefer at minimum Japanese support before committing to "
                "military operations in the Western Pacific. If Japan hesitates, the US may delay."
            ),
            information_quality=0.82,
            perceived_threats={"PRC": 0.62, "TWN": 0.05, "JPN": 0.02},
        )

    def _build_prc(self) -> Actor:
        return Actor(
            name="People's Republic of China",
            short_name="PRC",
            actor_type="state",
            military=MilitaryResources(
                conventional_forces=0.82,
                naval_power=0.76,
                air_superiority=0.72,
                nuclear_capability=0.80,
                logistics_capacity=0.70,
                readiness=0.72,
                # HIGH amphibious capacity: PRC has invested heavily in PLAN amphibious
                # assault capability specifically for a Taiwan contingency
                amphibious_capacity=0.78,
                # HIGH A2/AD: DF-21D/DF-26 ASBMs are designed specifically to deny
                # US carrier access to the Western Pacific
                a2ad_effectiveness=0.82,
            ),
            economic=EconomicResources(
                gdp_strength=0.76,
                foreign_reserves=0.82,    # Largest FX reserves globally
                energy_independence=0.48,  # Vulnerable to energy supply disruption
                trade_openness=0.70,
                industrial_capacity=0.80,
                semiconductor_dependency=0.88,  # Critical dependency — TSMC produces
                                                  # chips PRC cannot manufacture domestically
            ),
            political=PoliticalResources(
                domestic_stability=0.68,
                regime_legitimacy=0.72,    # Xi's legitimacy tied to Taiwan narrative
                international_standing=0.62,
                decision_unity=0.85,       # Centralized decision-making under Xi
                casualty_tolerance=0.72,   # Higher tolerance; PLA casualties less politically costly
            ),
            territory=TerritoryControl(
                core_territory=0.96,
                contested_zones={
                    "taiwan_strait": 0.28,      # Limited current control; exercises assert claim
                    "south_china_sea": 0.70,
                    "east_china_sea": 0.45,
                },
                strategic_straits={"taiwan_strait": 0.32},
            ),
            goals=[
                "Achieve peaceful or coercive reunification of Taiwan with the mainland",
                "Establish PRC as the dominant power in the Western Pacific",
                "Erode US alliance credibility and forward military presence in East Asia",
                "Protect CCP domestic legitimacy through nationalist narrative on Taiwan",
                "Avoid economic collapse from sanctions while applying maximum pressure",
            ],
            red_lines=[
                RedLine(
                    description="Taiwan formal declaration of independence",
                    trigger_condition="TWN takes diplomatic action asserting formal sovereign independence",
                    if_crossed="Military action against Taiwan authorized; all means on table",
                ),
                RedLine(
                    description="Foreign military forces permanently stationed on Taiwan",
                    trigger_condition="USA or JPN executes form_alliance with TWN resulting in basing rights",
                    if_crossed="Military response; potential strike on Taiwan infrastructure",
                ),
                RedLine(
                    description="US strike on PRC homeland territory",
                    trigger_condition="USA executes strike action targeting PRC core territory",
                    if_crossed="Full military response including nuclear signaling",
                ),
            ],
            ideology=(
                "CCP-led socialist state pursuing national rejuvenation (中华民族伟大复兴). "
                "Revisionist of US-led unipolar order; views Taiwan as sacred sovereign territory. "
                "Territorial integrity is a non-negotiable core interest."
            ),
            strategic_culture=(
                "Patient strategic competition punctuated by decisive assertive moves at moments "
                "of perceived advantage. Uses ambiguity, gray-zone operations, and economic leverage. "
                "Deeply risk-averse on nuclear escalation; highly sensitive to loss of face."
            ),
            decision_style=(
                "Calculated, long-horizon, driven by Xi inner circle consensus. "
                "Willing to absorb short-term economic costs for strategic gains. "
                "Responds to perceived humiliation or disrespect with disproportionate signaling."
            ),
            war_aversion=(
                "CCP REGIME SURVIVAL: War is the single greatest threat to CCP rule. The Party's "
                "domestic legitimacy rests on two pillars: economic growth and nationalist pride. "
                "A war that produces economic collapse destroys the first pillar. A war that PRC "
                "loses — or even one that stalemates into a humiliating withdrawal — destroys "
                "both. Xi Jinping personally bears the political risk: a failed Taiwan campaign "
                "would be the most catastrophic CCP leadership failure since the Great Leap "
                "Forward. There is no graceful exit from a losing war.\n\n"
                "ECONOMIC CATASTROPHE: PRC's economy is deeply integrated into global trade. "
                "A US-led sanctions regime (modeled on the Russia response but vastly larger) "
                "would cut PRC off from advanced semiconductors, high-end machine tools, and "
                "Western financial markets. PRC's $3.2 trillion in foreign reserves would be "
                "partially frozen. Energy imports (PRC imports ~70% of its oil, mostly by sea) "
                "would be disrupted by US/allied naval interdiction. Youth unemployment is "
                "already ~20%; a war economy with sanctions could push it to depression levels. "
                "Social instability at that scale has ended Chinese dynasties before.\n\n"
                "MILITARY UNCERTAINTY: The PLA has not fought a war since the 1979 Sino-Vietnamese "
                "War, where its performance was poor. The current PLA is vastly more capable, but "
                "it has never conducted the kind of complex joint operation a Taiwan invasion "
                "requires — the largest opposed amphibious landing in history, under contested "
                "air and sea conditions, against an adversary with advanced anti-ship missiles, "
                "with the US Navy potentially intervening. PLA leadership knows this is untested. "
                "The risk of catastrophic operational failure is real and not dismissable.\n\n"
                "TAIWAN DESTRUCTION PARADOX: PRC claims Taiwan as sacred Chinese territory and "
                "its people as Chinese compatriots. A war that devastates Taiwan's infrastructure, "
                "kills Taiwanese civilians, and destroys TSMC's fabs contradicts the entire "
                "reunification narrative. 'Liberating' a smoking ruin is not a political victory. "
                "And a destroyed TSMC means PRC's own semiconductor dependency becomes permanent."
            ),
            historical_precedents=(
                "THIRD TAIWAN STRAIT CRISIS (1995-96): PRC conducted missile tests in waters "
                "north and south of Taiwan (DF-15 SRBMs) to punish President Lee Teng-hui's "
                "US visit and signal opposition to Taiwan's democratization. When the US deployed "
                "two carrier groups, PRC backed down — but the humiliation drove a 20-year "
                "military modernization program specifically designed to deny US carrier access "
                "in a future crisis (the A2/AD revolution). Lesson internalized: never again be "
                "in a position where US naval presence can coerce PRC into retreat.\n\n"
                "SOUTH CHINA SEA ISLAND BUILDING (2013-2016): PRC conducted massive artificial "
                "island construction while publicly denying militarization. When confronted, "
                "stated the islands were 'primarily for civilian purposes.' Once construction was "
                "complete, installed military radar, missile systems, and airstrips. Pattern: "
                "PRC uses salami-slicing — small, individually sub-threshold steps that "
                "accumulate into fait accompli. Each step is designed to be too small to justify "
                "a US military response.\n\n"
                "PELOSI VISIT RESPONSE (2022): PRC conducted the largest-ever military exercises "
                "around Taiwan, including firing ballistic missiles over the island for the first "
                "time. Exercises were pre-planned and disproportionate to the provocation. "
                "Pattern: PRC uses crises as opportunities to establish new military baselines — "
                "the exercises normalized PLA operations in areas previously considered "
                "off-limits, and post-crisis the baseline did not return to pre-crisis levels.\n\n"
                "SCARBOROUGH SHOAL (2012): PRC and Philippines had a naval standoff. US brokered "
                "a mutual withdrawal. Philippines withdrew; PRC did not, seizing effective control. "
                "Pattern: PRC will exploit diplomatic processes to gain tactical advantage. "
                "Trust in PRC compliance with withdrawal agreements is low.\n\n"
                "SINO-INDIAN BORDER (GALWAN 2020): PRC engaged in lethal hand-to-hand combat "
                "with Indian forces but strictly avoided firearms, maintaining plausible deniability "
                "of escalation. Pattern: PRC calibrates violence to stay below thresholds that "
                "would trigger adversary's escalation doctrine."
            ),
            institutional_constraints=(
                "CENTRAL MILITARY COMMISSION (CMC): Xi Jinping chairs the CMC and holds ultimate "
                "authority over all PLA operations. Unlike the US system, there is no independent "
                "military chain of command — the CMC IS the chain. This means decisions can be "
                "made faster than the US NSC process, but also that a single leader's psychology "
                "is load-bearing. Xi does not tolerate dissent within the CMC.\n\n"
                "POLITBURO STANDING COMMITTEE (PSC): For decisions with potential economic "
                "consequences (sanctions, trade disruption), the PSC must reach consensus. Members "
                "include officials responsible for economic stability who will push back against "
                "actions that risk severe economic disruption. This creates internal tension "
                "between the military track (CMC) and the economic track (PSC/State Council).\n\n"
                "PLA THEATER COMMAND STRUCTURE: The Eastern Theater Command (responsible for "
                "Taiwan contingency) has pre-authorized operational plans that can be activated "
                "on CMC order. However, PLA doctrine emphasizes 'informatized warfare' requiring "
                "coordination across all five theater services — a level of joint operations the "
                "PLA has never executed in actual combat. This is an untested capability.\n\n"
                "PROPAGANDA DEPARTMENT COORDINATION: Major military actions require coordinated "
                "domestic messaging. The Central Propaganda Department must prepare the domestic "
                "narrative before or simultaneously with military action. This means genuinely "
                "surprise attacks are institutionally difficult — the propaganda apparatus needs "
                "lead time.\n\n"
                "ESCALATION AUTHORITY: PRC nuclear doctrine is officially 'No First Use' (NFU). "
                "Nuclear release authority rests solely with Xi via CMC. Conventional operations "
                "can be authorized at theater level with CMC approval. This creates a sharp "
                "conventional-nuclear firebreak that PRC is reluctant to blur."
            ),
            cognitive_patterns=(
                "CENTURY OF HUMILIATION NARRATIVE (百年国耻): PRC decision-makers — and Xi "
                "personally — interpret international relations through the lens of China's "
                "historical subjugation by Western powers (1839-1949). Actions perceived as "
                "humiliating or disrespectful trigger disproportionate responses. Losing face "
                "on Taiwan is not merely a strategic setback — it is an existential threat to "
                "CCP legitimacy and the national rejuvenation narrative.\n\n"
                "TAIWAN AS SACRED TERRITORY: Taiwan is not analyzed as a strategic interest to "
                "be weighed against costs. It is treated as an inalienable part of China whose "
                "separation is a historical wrong. This means cost-benefit analysis underweights "
                "economic costs when Taiwan-related decisions are at stake. PRC will accept "
                "significant economic damage to advance reunification.\n\n"
                "WINDOW OF OPPORTUNITY THINKING: PRC strategic culture emphasizes shi (势) — "
                "the propensity of a situation. Decision-makers look for moments when 'the "
                "situation is ripe' and act decisively. If PRC perceives a window (US distracted, "
                "Taiwan isolated, alliance weakened), it may move faster than rational cost-benefit "
                "would predict.\n\n"
                "STRATEGIC PATIENCE WITH SUDDEN BREAKS: PRC typically exhibits extreme patience "
                "in strategic competition, accepting unfavorable situations for years. But this "
                "patience can break suddenly — usually triggered by perceived humiliation, "
                "closing windows, or domestic legitimacy pressure. The transition from patience "
                "to action is often abrupt and surprises adversaries.\n\n"
                "UNDERESTIMATION OF ALLIANCE COHESION: PRC analysts consistently predict that "
                "US alliances will fracture under pressure — that Japan will not fight, that "
                "the US will not risk war for Taiwan. This is partly wishful thinking and partly "
                "informed by the PRC's own experience of unreliable allies (Soviet split). "
                "This bias may lead PRC to test alliance resolve more aggressively than warranted."
            ),
            information_quality=0.75,
            perceived_threats={"USA": 0.72, "TWN": 0.20, "JPN": 0.52},
        )

    def _build_twn(self) -> Actor:
        return Actor(
            name="Taiwan (Republic of China)",
            short_name="TWN",
            actor_type="state",
            military=MilitaryResources(
                conventional_forces=0.50,
                naval_power=0.45,
                air_superiority=0.55,
                nuclear_capability=0.0,    # No nuclear capability
                logistics_capacity=0.55,
                readiness=0.62,
                amphibious_capacity=0.12,  # Minimal offensive amphibious
                # HIGH A2/AD relative to size: "porcupine strategy" — Harpoon missiles,
                # sea mines, mobile artillery designed to make invasion costly
                a2ad_effectiveness=0.68,
            ),
            economic=EconomicResources(
                gdp_strength=0.72,
                foreign_reserves=0.70,
                energy_independence=0.22,  # Almost entirely import-dependent
                trade_openness=0.80,       # Highly trade-dependent economy
                industrial_capacity=0.75,
                semiconductor_dependency=0.10,  # Taiwan IS the supply; benefits from it
            ),
            political=PoliticalResources(
                domestic_stability=0.72,
                regime_legitimacy=0.78,    # Strong democratic legitimacy
                international_standing=0.55,  # Limited formal recognition
                decision_unity=0.68,
                casualty_tolerance=0.55,
            ),
            territory=TerritoryControl(
                core_territory=0.95,
                contested_zones={"taiwan_strait": 0.68},
                strategic_straits={"taiwan_strait": 0.62},
            ),
            goals=[
                "Preserve Taiwan's de facto independence and democratic governance",
                "Deter PRC invasion through asymmetric defense (porcupine strategy)",
                "Maintain and strengthen US security commitment and arms sales",
                "Avoid any action that provokes PRC into kinetic military action",
                "Preserve access to global markets and semiconductor export revenues",
            ],
            red_lines=[
                RedLine(
                    description="PRC amphibious landing on Taiwan",
                    trigger_condition="PRC executes advance action targeting TWN core_territory",
                    if_crossed="Full military resistance; emergency US intervention request",
                ),
                RedLine(
                    description="PRC naval blockade of Taiwan ports",
                    trigger_condition="PRC executes blockade action targeting TWN",
                    if_crossed="Declare state of war; activate all asymmetric defenses",
                ),
                RedLine(
                    description="PRC air strikes on civilian infrastructure",
                    trigger_condition="PRC executes strike at high intensity targeting TWN",
                    if_crossed="Maximum military resistance; international condemnation campaign",
                ),
            ],
            ideology=(
                "Liberal democratic state with complex identity — sees itself as legitimate "
                "Chinese democracy; deeply ambivalent about formal independence declaration "
                "due to PRC red line. Strongly pro-US and pro-democratic values."
            ),
            strategic_culture=(
                "Asymmetric defense posture (porcupine strategy): make invasion prohibitively "
                "costly without provoking pre-emptive strike. Heavily reliant on US deterrent. "
                "Avoids provocative unilateral moves."
            ),
            decision_style=(
                "Reactive and defensive; prioritizes signaling resolve without triggering "
                "escalation. Highly sensitive to US political signals — interprets ambiguity "
                "as abandonment risk. Reluctant to act without US backing."
            ),
            war_aversion=(
                "EXISTENTIAL STAKES: For Taiwan, war is not a policy instrument — it is an "
                "existential event. Taiwan is 180km from the Chinese mainland. Its population "
                "of 23 million lives on an island 394km long. There is no strategic depth, no "
                "hinterland to retreat to, no overland escape route. A full-scale PRC attack "
                "means missiles hitting Taipei, Kaohsiung, and Hsinchu. Civilian casualties "
                "would be massive. The entire population is in the target zone.\n\n"
                "ECONOMIC ANNIHILATION: Taiwan's economy is the most concentrated single point "
                "of failure in the global technology supply chain. TSMC's fabs in Hsinchu and "
                "Tainan represent ~$100B in irreplaceable infrastructure. War — even a short "
                "one — would destroy or disable these facilities. Taiwan's economy is trade-"
                "dependent (trade = ~120% of GDP); a blockade alone would collapse GDP within "
                "weeks. Energy imports (97% of energy is imported) would cease. The island has "
                "approximately 90 days of strategic petroleum reserves and 8 days of natural "
                "gas. A prolonged conflict means lights-out.\n\n"
                "NO WINNING A WAR ALONE: Taiwan's entire defense strategy is premised on "
                "surviving long enough for US intervention. Taiwan cannot defeat PRC alone — "
                "the asymmetric defense strategy is about imposing cost, not about winning. "
                "If the US does not intervene, or intervenes too late, Taiwan falls regardless "
                "of how well the porcupine strategy performs. Every escalatory action Taiwan "
                "takes must be evaluated against the risk that it triggers PRC attack before "
                "US commitment is secured.\n\n"
                "DEMOCRATIC LEGITIMACY AT STAKE: Taiwan's global moral claim rests on being "
                "a peaceful democracy that doesn't provoke conflict. If Taiwan is seen as having "
                "triggered the war — through a declaration of independence, a first strike, or "
                "needless provocation — international sympathy evaporates. The narrative must "
                "always be: PRC attacked; Taiwan defended. Losing that narrative is almost as "
                "catastrophic as losing the war itself."
            ),
            historical_precedents=(
                "THIRD TAIWAN STRAIT CRISIS (1995-96): Taiwan held its first direct presidential "
                "election despite PRC missile tests. The population rallied rather than submitted — "
                "Lee Teng-hui won in a landslide. Pattern: PRC military coercion historically "
                "strengthens Taiwanese domestic resolve and democratic legitimacy rather than "
                "weakening it. Taiwan's political leadership knows this and factors it into "
                "crisis calculations.\n\n"
                "SUNFLOWER MOVEMENT (2014): Mass citizen protest blocked a cross-strait trade "
                "agreement (CSSTA) seen as giving PRC too much economic leverage. Pattern: "
                "Taiwan's democratic public acts as a hard constraint on accommodation with PRC. "
                "Any leader who appears to be 'selling out to Beijing' faces immediate domestic "
                "political costs. This limits the space for diplomatic concessions.\n\n"
                "PORCUPINE STRATEGY EVOLUTION (2017-present): Under US pressure, Taiwan shifted "
                "from symmetric defense (buying fighter jets, tanks) to asymmetric denial — "
                "mobile anti-ship missiles (Harpoon/HF-2E), naval mines, mobile SAMs, and "
                "dispersed coastal defense. Pattern: Taiwan does not plan to win a conventional "
                "war. It plans to make the first 72 hours of an amphibious landing so costly "
                "that PRC either fails or the US has time to intervene.\n\n"
                "COVID-19 RESPONSE (2020): Taiwan acted early and decisively with border controls "
                "and contact tracing despite WHO exclusion (due to PRC pressure). Pattern: Taiwan "
                "is institutionally capable of fast crisis response when the threat is clear and "
                "the bureaucracy is aligned. The lag comes from political ambiguity, not "
                "institutional incapacity.\n\n"
                "MEDIAN LINE EROSION (2020-2022): PRC aircraft increasingly crossed the Taiwan "
                "Strait median line. Taiwan initially scrambled interceptors but eventually "
                "shifted to monitoring and tracking (to reduce pilot fatigue and aircraft wear). "
                "Pattern: Taiwan manages escalation by absorbing provocations rather than "
                "matching them — but this can be mistaken for acquiescence."
            ),
            institutional_constraints=(
                "NATIONAL SECURITY COUNCIL (NSC): The President chairs Taiwan's NSC, which "
                "includes the VP, Premier, and heads of defense, foreign affairs, and intelligence. "
                "Unlike the US NSC, Taiwan's NSC is a direct executive body — the President "
                "holds genuine command authority. But coalition government dynamics (DPP/KMT "
                "tensions in the legislature) constrain funding and authorization for provocative "
                "actions.\n\n"
                "MINISTRY OF NATIONAL DEFENSE (MND): Taiwan's military reports to the civilian "
                "MND, which reports to the Premier and President. The chain of command is clear "
                "but untested in actual high-intensity combat. Peacetime readiness is strong; "
                "wartime command-and-control under PLA electronic warfare is unknown.\n\n"
                "US DEPENDENCY CHANNEL: Taiwan's most critical institutional constraint is the "
                "de facto requirement for US consultation before major defensive decisions. "
                "Taiwan receives US intelligence products, US-supplied weapons require US "
                "approval for employment doctrine, and Taiwan's defense plans are coordinated "
                "(informally) with US Pacific Command. Acting without US knowledge risks losing "
                "the security guarantee.\n\n"
                "RESERVE MOBILIZATION: Taiwan's active military is ~215,000 but its reserve "
                "system is being reformed. Full mobilization of reserves takes 48-72 hours and "
                "is highly visible (impossible to do covertly). Early mobilization signals "
                "preparation for conflict, which PRC may interpret as provocation. Late "
                "mobilization risks being caught unprepared."
            ),
            cognitive_patterns=(
                "ABANDONMENT ANXIETY: Taiwan's deepest strategic fear is US abandonment — that "
                "in a crisis, the US will calculate that defending Taiwan is not worth the cost "
                "of war with a nuclear-armed PRC. Every ambiguous US signal is parsed for signs "
                "of wavering commitment. This anxiety is not paranoid; it is grounded in "
                "historical precedent (US recognition switch to PRC in 1979, periodic arms sales "
                "pauses). This fear can cause Taiwan to escalate signaling to 'lock in' US "
                "commitment — or conversely, to avoid any action that might give the US an "
                "excuse to disengage.\n\n"
                "SILICON SHIELD BELIEF: Taiwan's political and business elite operate on the "
                "assumption that global semiconductor dependency (TSMC produces ~90% of the "
                "world's most advanced chips) makes Taiwan too important to abandon. This "
                "'silicon shield' gives Taiwan a sense of strategic insurance that may cause "
                "it to underestimate scenarios where the shield fails (e.g., if the US "
                "successfully onshores chip production).\n\n"
                "THREAT NORMALIZATION: After decades of PRC military pressure (missile tests, "
                "air incursions, naval exercises), Taiwan's population has partially normalized "
                "the threat. Surveys consistently show that while Taiwanese take PRC threats "
                "seriously, they do not believe an invasion is imminent. This can create a "
                "dangerous gap between elite threat perception and public mobilization readiness.\n\n"
                "DEFENSIVE IDENTITY: Taiwan sees itself as the defender, never the aggressor. "
                "This identity is psychologically deep and structurally constraining. Taiwan "
                "will absorb significant provocation before responding kinetically because "
                "firing first — even in self-defense — risks losing the moral high ground and "
                "the international sympathy that is Taiwan's most important non-military asset."
            ),
            information_quality=0.70,
            perceived_threats={"PRC": 0.92, "USA": 0.02, "JPN": 0.03},
        )

    def _build_jpn(self) -> Actor:
        return Actor(
            name="Japan",
            short_name="JPN",
            actor_type="state",
            military=MilitaryResources(
                conventional_forces=0.62,
                naval_power=0.68,          # JMSDF is one of the strongest in the region
                air_superiority=0.64,
                nuclear_capability=0.0,    # Non-nuclear; covered by US extended deterrence
                logistics_capacity=0.65,
                readiness=0.58,
                amphibious_capacity=0.22,  # JGSDF amphibious rapid deployment brigade
                a2ad_effectiveness=0.58,
            ),
            economic=EconomicResources(
                gdp_strength=0.74,
                foreign_reserves=0.80,
                energy_independence=0.18,  # Almost entirely import-dependent; LNG via sea lanes
                trade_openness=0.75,
                industrial_capacity=0.78,
                semiconductor_dependency=0.58,  # Significant advanced chip dependency
            ),
            political=PoliticalResources(
                domestic_stability=0.72,
                regime_legitimacy=0.70,
                international_standing=0.76,
                decision_unity=0.65,       # Coalition government; constitutional constraints
                casualty_tolerance=0.35,   # Very low — post-WWII pacifist norm deeply embedded
            ),
            territory=TerritoryControl(
                core_territory=0.97,
                contested_zones={
                    "east_china_sea": 0.62,     # Senkaku/Diaoyu dispute with PRC
                    "miyako_strait": 0.80,      # Key strategic chokepoint for PLAN access
                },
                strategic_straits={"miyako_strait": 0.78, "tsugaru_strait": 0.92},
            ),
            goals=[
                "Preserve Japan's security and economic stability",
                "Maintain US-Japan alliance as the primary security guarantee",
                "Prevent PRC military dominance of the Western Pacific and key shipping lanes",
                "Support Taiwan's de facto independence without direct military commitment",
                "Protect Japanese energy supply lines through the Taiwan Strait region",
            ],
            red_lines=[
                RedLine(
                    description="PRC military strike on Japanese territory or JSDF forces",
                    trigger_condition="PRC executes strike action targeting JPN or JPN territory",
                    if_crossed="Article 9 reinterpretation activated; full US-Japan alliance response",
                ),
                RedLine(
                    description="PRC blockade disrupting Japanese shipping through Taiwan Strait",
                    trigger_condition="PRC executes blockade action affecting miyako_strait or taiwan_strait access",
                    if_crossed="Economic countermeasures; JSDF escort operations; US consultation",
                ),
                RedLine(
                    description="Collapse of US extended deterrence credibility",
                    trigger_condition="USA executes withdraw action while PRC is in crisis phase",
                    if_crossed="Emergency cabinet review of Japan's independent defense posture",
                ),
            ],
            ideology=(
                "Constitutional pacifist state undergoing gradual strategic normalization. "
                "Values multilateral rules-based order and US alliance above all. "
                "Increasing willingness to contribute to regional security under threat."
            ),
            strategic_culture=(
                "Reactive, alliance-dependent; prefers diplomatic and economic tools over "
                "military. Post-WWII trauma is structurally load-bearing in decision culture. "
                "Increasing strategic autonomy under PRC pressure but slow-moving institutionally."
            ),
            decision_style=(
                "Cautious, consensus-driven internally (LDP coalition dynamics). "
                "Slow to commit military assets; will signal alongside US but hesitates on "
                "independent action. Highly sensitive to US signals of commitment."
            ),
            war_aversion=(
                "ENERGY STRANGULATION: Japan imports 99% of its oil, 97% of its natural gas, "
                "and ~60% of its food. The vast majority transits sea lanes that a PRC-US war "
                "would disrupt or close — the Taiwan Strait, South China Sea, and Malacca Strait. "
                "Japan has approximately 200 days of strategic petroleum reserves, but LNG storage "
                "is only ~20 days. A protracted conflict means Japanese industry shuts down, "
                "heating/cooling fails in a country of 125 million, and food supply chains break. "
                "This is not a theoretical risk — it is Japan's fundamental strategic vulnerability "
                "and the single most important factor in every decision.\n\n"
                "CONSTITUTIONAL AND POLITICAL CRISIS: Japanese participation in a war would "
                "trigger the deepest constitutional crisis since 1945. Article 9's 'renunciation "
                "of war' is not merely legal text — it is the foundation of Japan's post-war "
                "identity. Even the 2015 collective self-defense reinterpretation was massively "
                "controversial. Actual combat operations would split the Diet, trigger mass "
                "protests, and potentially bring down the government. The political cost of "
                "fighting may exceed the political cost of not fighting — a paralyzing dilemma.\n\n"
                "PRC RETALIATION AGAINST THE HOMELAND: Japan is within range of PRC ballistic "
                "and cruise missiles. PLA DF-26 IRBMs can reach all of Japan. If Japan allows "
                "US forces to use Japanese bases (Kadena, Yokosuka, Misawa, Sasebo) for combat "
                "operations against PRC, those bases — and the Japanese cities near them — become "
                "legitimate targets under PRC doctrine. Okinawa, with 1.4 million Japanese "
                "civilians, hosts the largest concentration of US military bases in the Pacific. "
                "It would be in the opening target set.\n\n"
                "ECONOMIC DEVASTATION: Japan and China are deeply intertwined economically. "
                "China is Japan's largest trade partner ($350B+ annually). Japanese corporations "
                "have massive investments in China. War means: those investments are seized, "
                "that trade evaporates, supply chains for Japanese manufacturing (automotive, "
                "electronics) collapse, and the yen destabilizes. Japan's $4.9 trillion in "
                "government debt (264% of GDP) makes it uniquely vulnerable to financial shock."
            ),
            historical_precedents=(
                "SENKAKU/DIAOYU NATIONALIZATION CRISIS (2012): Japan's central government "
                "purchased the Senkaku Islands from their private owner. PRC responded with "
                "massive anti-Japanese protests, economic sanctions (rare earth export "
                "restrictions), and escalated maritime patrols. Japan held firm on sovereignty "
                "but did not further escalate. Pattern: Japan will defend sovereignty claims "
                "but absorbs economic punishment rather than counter-escalating militarily. The "
                "crisis permanently increased JSDF readiness posture in the Nansei Islands.\n\n"
                "NORTH KOREAN MISSILE OVERFLIGHTS (1998, 2017, 2022): When DPRK missiles "
                "overflew Japanese territory, Japan's response was diplomatic protest, UN "
                "Security Council action, enhanced missile defense deployment, and closer US "
                "coordination. No military strike was considered. Pattern: even direct security "
                "threats produce a diplomatic-first, defense-enhancement response — not offensive "
                "action.\n\n"
                "COLLECTIVE SELF-DEFENSE REINTERPRETATION (2014-2015): Abe government "
                "reinterpreted Article 9 to allow 'collective self-defense' — Japan can use "
                "force to defend allies under attack if Japan's survival is threatened. This was "
                "enormously controversial domestically and took 18+ months of political process. "
                "Pattern: changing Japan's security posture requires sustained political capital "
                "and cannot be improvised during a crisis.\n\n"
                "TAIWAN STRAIT 'EXISTENTIAL' STATEMENTS (2021-2022): Senior Japanese officials "
                "(Aso, Kishi, Kishida) publicly stated that Taiwan's security is linked to "
                "Japan's survival. These statements were unprecedented and reflected a genuine "
                "strategic shift. Pattern: Japan has moved from studied ambiguity on Taiwan to "
                "conditional commitment — but the commitment remains conditional on US leadership.\n\n"
                "NANSEI ISLANDS MILITARIZATION (2016-present): Japan has steadily deployed "
                "anti-ship missiles, SAM batteries, and radar to the Nansei/Ryukyu island chain "
                "including Miyako-jima, Ishigaki, and Yonaguni. Pattern: Japan prepares "
                "defensively in peacetime with long lead times. This is the opposite of crisis "
                "improvisation — if Japan hasn't pre-positioned, it cannot respond quickly."
            ),
            institutional_constraints=(
                "ARTICLE 9 OF THE CONSTITUTION: 'The Japanese people forever renounce war as a "
                "sovereign right of the nation and the threat or use of force as means of "
                "settling international disputes.' While reinterpreted to allow self-defense and "
                "(since 2015) collective self-defense, Article 9 remains a binding constraint on "
                "offensive operations. Japan cannot legally initiate strikes on another country's "
                "territory unless Japan itself is under armed attack or an ally under attack "
                "poses an existential threat to Japan. This is not a political preference — it "
                "is constitutional law that constrains the entire chain of command.\n\n"
                "NATIONAL SECURITY SECRETARIAT (NSS): Established in 2013, Japan's NSS is "
                "modeled on the US NSC but is smaller, newer, and still developing institutional "
                "muscle. The NSS coordinates policy but actual authority flows through the "
                "Cabinet. A decision to deploy JSDF in a combat capacity requires full Cabinet "
                "approval and may require Diet (parliament) consultation depending on the legal "
                "framework invoked.\n\n"
                "US-JAPAN ALLIANCE COORDINATION MECHANISM: Established in the 2015 Defense "
                "Guidelines revision. In a Taiwan contingency, Japan would coordinate with US "
                "forces through the Alliance Coordination Mechanism (ACM). Japan's role would "
                "likely be: rear-area support (basing, logistics, intelligence), maritime "
                "domain awareness (JMSDF surveillance), and potentially Nansei Islands defense. "
                "Direct Japanese combat operations against PRC forces would require the highest "
                "level of political authorization and is not pre-authorized.\n\n"
                "RULES OF ENGAGEMENT CONSTRAINTS: JSDF rules of engagement are highly restrictive "
                "compared to US military ROE. Warning shots, proportional response, and "
                "escalation-avoidance are deeply embedded in JSDF operational culture. JSDF "
                "commanders will err heavily on the side of restraint in ambiguous situations."
            ),
            cognitive_patterns=(
                "ENTRAPMENT-ABANDONMENT DILEMMA: Japan's central strategic anxiety is a double "
                "bind. Fear of entrapment: being dragged into a US-PRC war that Japan did not "
                "choose. Fear of abandonment: if Japan fails to support the US, the alliance "
                "weakens and Japan faces PRC alone. Every crisis decision is filtered through "
                "this dilemma. Japan will try to demonstrate alliance solidarity while avoiding "
                "actions that directly commit it to combat.\n\n"
                "PACIFIST NORM AS STRUCTURAL CONSTRAINT: Japan's post-WWII pacifist identity "
                "is not merely a policy preference — it is deeply embedded in institutional "
                "culture, public opinion, media discourse, and the self-image of JSDF officers "
                "themselves. Even when political leaders want to act, the institutional friction "
                "from pacifist norms slows decision-making. The JSDF's worst nightmare is being "
                "seen as the aggressor.\n\n"
                "ECONOMIC INTERDEPENDENCE AWARENESS: Japan's political and business elite are "
                "acutely aware of Japan's economic interdependence with China (Japan's largest "
                "trade partner). Economic considerations act as a genuine constraint on military "
                "action — not just as a cost to be weighed, but as a visceral institutional "
                "reluctance. METI (trade ministry) will push back hard against any action "
                "that risks PRC economic retaliation.\n\n"
                "GEOGRAPHIC VULNERABILITY CONSCIOUSNESS: Japan's political class is constantly "
                "aware that Japan is an island nation dependent on sea lanes for energy (99% "
                "imported oil, 97% imported LNG) and food (60%+ imported calories). Any "
                "disruption to shipping through the Taiwan Strait or South China Sea is an "
                "existential economic threat. This makes Japan simultaneously hawkish on freedom "
                "of navigation and extremely cautious about actions that could provoke PRC "
                "economic retaliation against Japanese shipping.\n\n"
                "INCREMENTALISM BIAS: Japanese decision-making culture strongly favors incremental "
                "steps over bold moves. The political system rewards consensus and punishes "
                "leaders who get ahead of public opinion. In a fast-moving crisis, this "
                "incrementalism can look like paralysis — but it also prevents rash escalation."
            ),
            information_quality=0.76,
            perceived_threats={"PRC": 0.62, "TWN": 0.02, "USA": 0.02},
        )

    # ── Relationship Graph (all 12 directed pairs) ───────────────────────────

    def _build_relationships(self) -> list:
        return [
            # ── USA relationships ──────────────────────────────────────────────
            BilateralRelationship(
                from_actor="USA", to_actor="PRC",
                relationship_type="competitor",
                trust_score=0.22,
                alliance_strength=0.0,
                trade_dependency=0.42,      # USA-China trade; vulnerable but not decisive
                threat_perception=0.62,
                deterrence_credibility=0.55, # USA uncertain if PRC will back down under pressure
            ),
            BilateralRelationship(
                from_actor="USA", to_actor="TWN",
                relationship_type="partner",
                trust_score=0.72,
                alliance_strength=0.58,      # TRA commitment; ambiguous but real
                trade_dependency=0.35,
                threat_perception=0.08,
                deterrence_credibility=0.62, # USA uncertain if its commitment is fully credible to TWN
            ),
            BilateralRelationship(
                from_actor="USA", to_actor="JPN",
                relationship_type="ally",
                trust_score=0.87,
                alliance_strength=0.92,      # Treaty of Mutual Cooperation and Security; Article 5
                trade_dependency=0.48,
                threat_perception=0.04,
                deterrence_credibility=0.88,
            ),

            # ── PRC relationships ──────────────────────────────────────────────
            BilateralRelationship(
                from_actor="PRC", to_actor="USA",
                relationship_type="adversary",
                trust_score=0.15,
                alliance_strength=0.0,
                trade_dependency=0.42,
                threat_perception=0.75,
                deterrence_credibility=0.58, # PRC takes US military threat seriously but tests resolve
            ),
            BilateralRelationship(
                from_actor="PRC", to_actor="TWN",
                relationship_type="hostile",
                trust_score=0.05,
                alliance_strength=0.0,
                trade_dependency=0.28,       # Cross-strait trade exists but declining
                threat_perception=0.85,      # PRC sees TWN as existential legitimacy threat
                deterrence_credibility=0.18, # PRC does not believe TWN can resist alone
            ),
            BilateralRelationship(
                from_actor="PRC", to_actor="JPN",
                relationship_type="competitor",
                trust_score=0.20,
                alliance_strength=0.0,
                trade_dependency=0.38,
                threat_perception=0.55,
                deterrence_credibility=0.38,
            ),

            # ── TWN relationships ──────────────────────────────────────────────
            BilateralRelationship(
                from_actor="TWN", to_actor="USA",
                relationship_type="partner",
                trust_score=0.75,
                alliance_strength=0.58,
                trade_dependency=0.40,
                threat_perception=0.06,
                deterrence_credibility=0.65, # TWN trusts US but fears strategic ambiguity
            ),
            BilateralRelationship(
                from_actor="TWN", to_actor="PRC",
                relationship_type="hostile",
                trust_score=0.05,
                alliance_strength=0.0,
                trade_dependency=0.25,
                threat_perception=0.93,
                deterrence_credibility=0.12,
            ),
            BilateralRelationship(
                from_actor="TWN", to_actor="JPN",
                relationship_type="partner",
                trust_score=0.68,
                alliance_strength=0.32,      # Informal but real security alignment
                trade_dependency=0.28,
                threat_perception=0.04,
                deterrence_credibility=0.52,
            ),

            # ── JPN relationships ──────────────────────────────────────────────
            BilateralRelationship(
                from_actor="JPN", to_actor="USA",
                relationship_type="ally",
                trust_score=0.88,
                alliance_strength=0.92,
                trade_dependency=0.44,
                threat_perception=0.04,
                deterrence_credibility=0.86,
            ),
            BilateralRelationship(
                from_actor="JPN", to_actor="PRC",
                relationship_type="competitor",
                trust_score=0.22,
                alliance_strength=0.0,
                trade_dependency=0.40,       # Japan's largest trade partner despite tensions
                threat_perception=0.65,
                deterrence_credibility=0.40,
            ),
            BilateralRelationship(
                from_actor="JPN", to_actor="TWN",
                relationship_type="partner",
                trust_score=0.70,
                alliance_strength=0.30,
                trade_dependency=0.26,
                threat_perception=0.04,
                deterrence_credibility=0.55,
            ),
        ]
