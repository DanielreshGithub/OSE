"""Platform-level unit roster for the Taiwan Strait scenario — 2030 projected.

This roster projects force structure to ~2030 based on programmed acquisitions,
declared modernization plans, and trendline analyses from public sources.

Projections are CONSERVATIVE — they reflect platforms already funded, contracted,
or under construction as of 2024, not speculative future programs. Confidence
on individual platform existence is high; confidence on operational status at
the precise 2030 mark is medium.

PROJECTED CHANGES vs 2026:
  - PRC: Type 003 Fujian carrier fully operational; 4th-6th Type 075 LHDs in
    service; expanded H-20 stealth bomber program (if delivered); ~1000-warhead
    nuclear arsenal per DoD CMPR trendline; expanded PLAN Marine Corps to 6+
    brigades.
  - USA: First Ford-class CVN in Pacific (replaces aging Nimitz); B-21 Raider
    initial operational capability; expanded Virginia-class SSN forward presence;
    additional Tomahawk-armed surface combatants.
  - TWN: ODC mature; full Hai Kun SSK class (~3-5 boats); F-16V transition
    complete (all wings); upgraded asymmetric coastal defense.
  - JPN: F-35B operational on Izumo/Kaga; ~400 Tomahawk Block V delivered and
    integrated; extended-range Type 12 SSM (1000+ km) deployed; counter-strike
    operational capability declared; ~2% GDP defense budget realized.

SOURCES (file-level):
  - US DoD CMPR (2023, 2024 editions) — PLA modernization trendlines.
  - FAS Nuclear Notebook; SIPRI nuclear forces assessments.
  - Japan MOD National Defense Strategy 2022 + Defense Buildup Program.
  - ROC MND Quadrennial Defense Review 2025.
  - CSBA, RAND, CSIS Indo-Pacific posture analyses.
  - USPACFLT / INDOPACOM posture statements; NDS 2022.

REVIEWED: 2026-05.
"""
from __future__ import annotations
from typing import Dict, Any

from scenarios.data.units_2026 import UNITS_2026


# Start from the 2026 roster and apply projected deltas.
# This is a pragmatic approach: most platforms exist in both; the variant captures
# only the additions and capability shifts.
UNITS_2030: Dict[str, Dict[str, Any]] = {**UNITS_2026}


# ── PROJECTED ADDITIONS — 2030 ────────────────────────────────────────────────

UNITS_2030.update({
    # PRC additions
    "PRC_CV_FUJIAN": {
        "owner": "PRC", "unit_type": "csg",
        "platform_class": "Type 003 CV-18 Fujian (PLAN Eastern Theater; EMALS-equipped)",
        "home_port": "ningbo", "lat": 29.86, "lon": 121.55,
        "speed_kts": 30, "range_km_per_turn": 1300, "state": "standby",
        "composition": {
            "air_wing": "~40-48 J-15B/T + J-35 stealth + KJ-600 AEW (catapult-launched)",
            "escorts": ["Type 055", "2x Type 052D", "Type 054A"],
        },
        "source": "DoD CMPR 2024; Fujian launched 2022, sea trials 2024+, full IOC ~2026-27.",
        "confidence": "HIGH",
    },
    "PRC_CV_FOURTH": {
        "owner": "PRC", "unit_type": "csg",
        "platform_class": "Type 004 CV-19 (4th carrier; nuclear-powered per CMPR projection)",
        "home_port": "zhanjiang", "lat": 21.27, "lon": 110.36,
        "speed_kts": 30, "range_km_per_turn": 1300, "state": "standby",
        "composition": {"air_wing": "Projected J-35 stealth + KJ-600 AEW"},
        "source": "DoD CMPR 2024 projection; construction reported 2024-25, IOC late 2020s.",
        "confidence": "MEDIUM",
    },
    "PRC_TYPE075_3": {
        "owner": "PRC", "unit_type": "amphibious_group",
        "platform_class": "Type 075 LHD Anhui (Hull 3) + Type 071 LPDs",
        "home_port": "ningbo", "lat": 29.86, "lon": 121.55,
        "speed_kts": 22, "range_km_per_turn": 970, "state": "standby",
        "composition": {"embarked": "PLANMC brigade element"},
        "source": "DoD CMPR; Hull 3 in fitting-out / commissioning by 2026.",
        "confidence": "HIGH",
    },
    "PRC_TYPE076_LHA": {
        "owner": "PRC", "unit_type": "amphibious_group",
        "platform_class": "Type 076 LHA (EMALS catapult + fixed-wing; UAV-heavy)",
        "home_port": "zhanjiang", "lat": 21.27, "lon": 110.36,
        "speed_kts": 22, "range_km_per_turn": 970, "state": "standby",
        "composition": {"embarked": "UCAVs + helicopters + PLANMC"},
        "source": "DoD CMPR 2024; Type 076 launched 2024, IOC ~2027-28.",
        "confidence": "MEDIUM",
    },
    "PRC_H20_BOMBER": {
        "owner": "PRC", "unit_type": "bomber_squadron",
        "platform_class": "PLAAF H-20 stealth strategic bomber (projected IOC)",
        "home_port": "fuzhou", "lat": 26.07, "lon": 119.30,
        "speed_kts": 480, "range_km_per_turn": 3000, "state": "standby",
        "composition": {"airframes": "Initial flight unit; subsonic stealth flying wing"},
        "source": "DoD CMPR 2023/24 projections; H-20 IOC uncertain (late 2020s).",
        "confidence": "LOW",
    },
    "PRC_MARINE_BRIGADE_3": {
        "owner": "PRC", "unit_type": "infantry_brigade",
        "platform_class": "PLAN Marine Corps brigade (additional; expansion to 8 brigades)",
        "home_port": "ningbo", "lat": 29.86, "lon": 121.55,
        "speed_kts": 0, "range_km_per_turn": 0, "state": "standby",
        "composition": {"forces": "~6000 PLANMC; new brigade per expansion plan"},
        "source": "DoD CMPR; PLAN Marines from 2 to 6-8 brigades target.",
        "confidence": "MEDIUM",
    },

    # USA additions / replacements
    "USA_CSG_FORD": {
        "owner": "USA", "unit_type": "csg",
        "platform_class": "Gerald R. Ford CVN-78/79/80 class (first Pacific deployment)",
        "home_port": "yokosuka", "lat": 35.29, "lon": 139.66,
        "speed_kts": 30, "range_km_per_turn": 1300, "state": "standby",
        "composition": {
            "air_wing": "CVW with F-35C IOC; F/A-18E/F; EA-18G; E-2D; MQ-25 tanker",
            "escorts": ["DDG Flight III"],
        },
        "source": "USPACFLT; Ford-class Pacific rotation late 2020s.",
        "confidence": "MEDIUM",
    },
    "USA_B21_GUAM": {
        "owner": "USA", "unit_type": "bomber_squadron",
        "platform_class": "B-21 Raider stealth bomber task force (rotational)",
        "home_port": "andersen_guam", "lat": 13.58, "lon": 144.92,
        "speed_kts": 500, "range_km_per_turn": 3200, "state": "standby",
        "composition": {"airframes": "4-8 B-21; IOC late 2020s per USAF plan"},
        "source": "USAF B-21 program; first flight 2023, IOC mid-late 2020s.",
        "confidence": "MEDIUM",
    },
    "USA_SSN_VIRGINIA_AUGMENT": {
        "owner": "USA", "unit_type": "submarine",
        "platform_class": "Virginia-class Block V SSN (Pacific augmentation)",
        "home_port": "apra_guam", "lat": 13.46, "lon": 144.66,
        "speed_kts": 25, "range_km_per_turn": 1100, "state": "standby",
        "composition": {"boats": "Additional Virginia-class with VPM module"},
        "source": "USN shipbuilding plan; Virginia Payload Module 40-Tomahawk capacity.",
        "confidence": "MEDIUM",
    },

    # TWN additions / upgrades
    "TWN_HAI_KUN_2": {
        "owner": "TWN", "unit_type": "submarine",
        "platform_class": "Hai Kun-class IDS (boats 2-3)",
        "home_port": "tsoying", "lat": 22.66, "lon": 120.27,
        "speed_kts": 20, "range_km_per_turn": 890, "state": "standby",
        "composition": {"boats": "2-3 additional Hai Kun by 2030 per ROC MND plan"},
        "source": "ROC MND; IDS program plans 8 boats long-term.",
        "confidence": "MEDIUM",
    },
    "TWN_HF3_EXTENDED": {
        "owner": "TWN", "unit_type": "coastal_defense",
        "platform_class": "HF-3 Extended Range coastal defense battalion",
        "home_port": "hualien_ab", "lat": 23.98, "lon": 121.62,
        "speed_kts": 50, "range_km_per_turn": 250, "state": "on_station",
        "composition": {"launchers": "HF-3 ER (400+ km); east coast dispersal"},
        "source": "ROC MND; HF-3 ER program announced 2023.",
        "confidence": "MEDIUM",
    },
    "TWN_TIEN_KUNG_IV": {
        "owner": "TWN", "unit_type": "sam_battery",
        "platform_class": "Tien Kung IV (Sky Bow IV) ABM-class SAM",
        "home_port": "hsinchu_ab", "lat": 24.82, "lon": 120.94,
        "speed_kts": 0, "range_km_per_turn": 0, "state": "on_station",
        "composition": {"launchers": "Sky Bow IV; ABM intercept of MRBM-class"},
        "source": "NCSIST; in development 2024+.",
        "confidence": "LOW",
    },

    # JPN additions
    "JPN_TOMAHAWK_LAND": {
        "owner": "JPN", "unit_type": "missile_brigade",
        "platform_class": "JGSDF Tomahawk Block V land-attack cruise missile battalion",
        "home_port": "miyako_jima", "lat": 24.78, "lon": 125.30,
        "speed_kts": 50, "range_km_per_turn": 200, "state": "on_station",
        "composition": {"launchers": "Land-based Tomahawks; 400 missiles ordered 2023, delivery 2025-28"},
        "source": "MOD; counter-strike capability per NSS 2022; first deliveries 2025.",
        "confidence": "HIGH",
    },
    "JPN_TYPE12_EXTENDED": {
        "owner": "JPN", "unit_type": "coastal_defense",
        "platform_class": "Type 12 SSM extended-range (1000+ km) battalion",
        "home_port": "ishigaki", "lat": 24.34, "lon": 124.16,
        "speed_kts": 50, "range_km_per_turn": 200, "state": "on_station",
        "composition": {"launchers": "Upgraded Type 12 ER; counter-strike capable"},
        "source": "MOD; Type 12 ER program funded 2023.",
        "confidence": "HIGH",
    },
    "JPN_F35B_OPERATIONAL": {
        "owner": "JPN", "unit_type": "fighter_squadron",
        "platform_class": "JASDF/JMSDF F-35B operational squadron (Izumo air wing)",
        "home_port": "yokosuka", "lat": 35.29, "lon": 139.66,
        "speed_kts": 400, "range_km_per_turn": 2500, "state": "standby",
        "composition": {"airframes": "~10-20 F-35B; Izumo/Kaga embarked"},
        "source": "MOD; 42 F-35B order; Izumo carrier IOC 2027-28.",
        "confidence": "HIGH",
    },
})


# ── CAPABILITY SHIFTS FROM 2026 → 2030 (applied to MilitaryResources) ────────
# These deltas inform scenarios/taiwan_strait.py year_horizon swap.
# Values shown as float deltas from 2026 baseline.

CAPABILITY_DELTAS_2030: Dict[str, Dict[str, float]] = {
    "PRC": {
        "amphibious_capacity": +0.10,    # 0.62 → 0.72; more Type 075/076; mature PLANMC
        "nuclear_capability": +0.14,     # 0.58 → 0.72; ~1000 warheads per CMPR projection
        "naval_power": +0.04,            # Fujian + 4th carrier
        "air_superiority": +0.04,        # More J-20; potential H-20
    },
    "TWN": {
        "a2ad_effectiveness": +0.17,     # 0.55 → 0.72; ODC mature; HF-3 ER; more Hai Kun
        "naval_power": +0.03,            # More Hai Kun SSK
    },
    "JPN": {
        "conventional_forces": +0.05,    # 2% GDP defense by 2027
        "a2ad_effectiveness": +0.10,     # Type 12 ER; Tomahawk; counter-strike
    },
    "USA": {
        # Held relatively stable; force modernization but theater balance shifts
        # toward parity rather than US growth in absolute terms.
    },
}
