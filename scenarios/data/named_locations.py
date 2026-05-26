"""Named geographic locations referenced by actions, events, and unit roster.

Coordinates are rounded to 2 decimal places (~1 km precision) — this is honest
public-record precision, not fake-precise. Source: widely-available open
geographic data (Wikipedia, OpenStreetMap, official base addresses, IHO
maritime feature definitions).

Reviewed: 2026-05.
"""
from __future__ import annotations
from typing import Dict, Any


NAMED_LOCATIONS: Dict[str, Dict[str, Any]] = {
    # ── US bases (forward-deployed, Pacific) ──────────────────────────────
    "yokosuka": {
        "lat": 35.29, "lon": 139.66,
        "location_type": "naval_base",
        "description": "Yokosuka Naval Base, Japan. Homeport of forward-deployed USN 7th Fleet, "
                       "including the only forward-deployed US carrier strike group.",
    },
    "sasebo": {
        "lat": 33.16, "lon": 129.72,
        "location_type": "naval_base",
        "description": "Sasebo Naval Base, Japan. Forward-deployed USN amphibious group; "
                       "homeport of US 7th Fleet expeditionary strike group.",
    },
    "kadena": {
        "lat": 26.36, "lon": 127.77,
        "location_type": "air_base",
        "description": "Kadena Air Base, Okinawa. Largest USAF installation in the Pacific; "
                       "F-15 / F-22 / F-35 / KC-135 / E-3 / RC-135 operations.",
    },
    "misawa": {
        "lat": 40.71, "lon": 141.37,
        "location_type": "joint_base",
        "description": "Misawa Air Base, northern Honshu. USAF F-16, USN P-8 / EP-3 ISR.",
    },
    "iwakuni": {
        "lat": 34.14, "lon": 132.24,
        "location_type": "air_base",
        "description": "MCAS Iwakuni, Japan. USMC F-35B, F/A-18, and supporting aviation.",
    },
    "andersen_guam": {
        "lat": 13.58, "lon": 144.92,
        "location_type": "air_base",
        "description": "Andersen AFB, Guam. USAF bomber rotational presence (B-1/B-2/B-52); "
                       "key second-island-chain hub.",
    },
    "apra_guam": {
        "lat": 13.46, "lon": 144.66,
        "location_type": "naval_base",
        "description": "Naval Base Guam, Apra Harbor. USN submarine squadron, expeditionary support.",
    },
    "pearl_harbor": {
        "lat": 21.36, "lon": -157.97,
        "location_type": "naval_base",
        "description": "Naval Station Pearl Harbor-Hickam, Hawaii. USPACFLT HQ; "
                       "submarine and surface forces.",
    },
    "san_diego": {
        "lat": 32.69, "lon": -117.13,
        "location_type": "naval_base",
        "description": "Naval Base San Diego. USPACFLT carrier and surface combatant homeport.",
    },
    "bremerton": {
        "lat": 47.55, "lon": -122.65,
        "location_type": "naval_base",
        "description": "Naval Base Kitsap-Bremerton, Washington. USN Pacific carrier homeport.",
    },

    # ── PRC bases (PLAN, PLAAF, PLARF — Eastern and Southern theater) ─────
    "ningbo": {
        "lat": 29.86, "lon": 121.55,
        "location_type": "naval_base",
        "description": "Ningbo / Zhoushan, Eastern Theater Command naval HQ. PLAN East Sea Fleet; "
                       "primary force opposite Taiwan.",
    },
    "qingdao": {
        "lat": 36.07, "lon": 120.32,
        "location_type": "naval_base",
        "description": "Qingdao, Northern Theater Command. PLAN North Sea Fleet; "
                       "Liaoning carrier homeport.",
    },
    "zhanjiang": {
        "lat": 21.27, "lon": 110.36,
        "location_type": "naval_base",
        "description": "Zhanjiang, Southern Theater Command naval HQ. PLAN South Sea Fleet; "
                       "Shandong carrier homeport; primary SCS force.",
    },
    "yulin_hainan": {
        "lat": 18.21, "lon": 109.69,
        "location_type": "naval_base",
        "description": "Yulin Naval Base, Hainan. PLAN strategic submarine base "
                       "(Type 094 SSBN); SCS launch point.",
    },
    "fuzhou": {
        "lat": 26.07, "lon": 119.30,
        "location_type": "air_base",
        "description": "Fuzhou region, Eastern Theater. PLAAF SU-30/J-10/J-16 brigades "
                       "directly opposite Taiwan.",
    },
    "quanzhou": {
        "lat": 24.87, "lon": 118.68,
        "location_type": "air_base",
        "description": "Quanzhou / Longtian, Fujian. PLAAF and PLA Rocket Force assets "
                       "within direct strike range of Taiwan.",
    },
    "leizhou": {
        "lat": 20.91, "lon": 110.10,
        "location_type": "naval_base",
        "description": "Leizhou Peninsula. PLA Marine Corps brigades; amphibious assembly.",
    },

    # ── Taiwan (ROC) bases ────────────────────────────────────────────────
    "tsoying": {
        "lat": 22.66, "lon": 120.27,
        "location_type": "naval_base",
        "description": "Tsoying Naval Base, Kaohsiung. ROCN HQ; primary surface and submarine force.",
    },
    "suao": {
        "lat": 24.59, "lon": 121.86,
        "location_type": "naval_base",
        "description": "Suao Naval Base, eastern Taiwan. ROCN eastern fleet; "
                       "less exposed to opening PLA strike than west-coast bases.",
    },
    "magong": {
        "lat": 23.57, "lon": 119.59,
        "location_type": "naval_base",
        "description": "Magong, Penghu Islands. ROCN forward base in Taiwan Strait.",
    },
    "hsinchu_ab": {
        "lat": 24.82, "lon": 120.94,
        "location_type": "air_base",
        "description": "Hsinchu Air Base. ROCAF Mirage 2000-5 wing; F-16V transition site.",
    },
    "ccd_taichung": {
        "lat": 24.18, "lon": 120.62,
        "location_type": "air_base",
        "description": "Ching Chuan Kang AB (CCK), Taichung. ROCAF F-16V wing; major air hub.",
    },
    "hualien_ab": {
        "lat": 23.98, "lon": 121.62,
        "location_type": "air_base",
        "description": "Hualien Air Base, east Taiwan. Hardened mountain shelter complex; "
                       "F-16V and Mirage dispersal site.",
    },
    "tainan": {
        "lat": 22.95, "lon": 120.21,
        "location_type": "air_base",
        "description": "Tainan Air Base, southwest Taiwan. ROCAF IDF 'Ching Kuo' indigenous "
                       "fighter wing.",
    },

    # ── Japan (JSDF) bases ────────────────────────────────────────────────
    "yokota": {
        "lat": 35.75, "lon": 139.35,
        "location_type": "air_base",
        "description": "Yokota AB, Tokyo region. USFJ HQ; JASDF Air Defense Command.",
    },
    "naha_ab": {
        "lat": 26.20, "lon": 127.65,
        "location_type": "air_base",
        "description": "Naha Air Base, Okinawa. JASDF F-15J wing covering Senkakus and southwest islands.",
    },
    "miyako_jima": {
        "lat": 24.78, "lon": 125.30,
        "location_type": "joint_base",
        "description": "Miyako-jima JGSDF base. Type 12 SSM coastal defense; SAM battery; "
                       "Miyako Strait chokepoint guard.",
    },
    "ishigaki": {
        "lat": 24.34, "lon": 124.16,
        "location_type": "joint_base",
        "description": "Ishigaki JGSDF base (operational from 2023). Type 12 SSM and SAM; "
                       "Senkaku-proximate.",
    },
    "yonaguni": {
        "lat": 24.46, "lon": 122.99,
        "location_type": "joint_base",
        "description": "Yonaguni Coast Observation Unit. Westernmost JSDF position; "
                       "111 km from Taiwan.",
    },
    "kure": {
        "lat": 34.24, "lon": 132.56,
        "location_type": "naval_base",
        "description": "Kure JMSDF base. Submarine flotilla; major escort homeport.",
    },

    # ── Straits, channels, contested features ─────────────────────────────
    "taiwan_strait_centerline": {
        "lat": 24.50, "lon": 119.50,
        "location_type": "strait",
        "description": "Approximate centerline of the Taiwan Strait. ~180 km wide; "
                       "primary contested transit corridor.",
    },
    "bashi_channel": {
        "lat": 21.50, "lon": 121.00,
        "location_type": "channel",
        "description": "Bashi Channel, between Taiwan and the Philippines. Primary PLAN access "
                       "route to the Western Pacific; US chokepoint surveillance focus.",
    },
    "miyako_strait": {
        "lat": 25.00, "lon": 125.00,
        "location_type": "strait",
        "description": "Miyako Strait, between Miyako-jima and Okinawa. ~250 km wide; "
                       "key PLAN access to Western Pacific north of Taiwan.",
    },
    "luzon_strait": {
        "lat": 20.50, "lon": 121.50,
        "location_type": "strait",
        "description": "Luzon Strait. ~250 km between Taiwan and Luzon; deep-water access.",
    },
    "senkaku_islands": {
        "lat": 25.74, "lon": 123.47,
        "location_type": "contested_feature",
        "description": "Senkaku Islands (Diaoyu). Japan-administered; PRC-claimed. "
                       "Routine PRC coast guard intrusions.",
    },
    "kinmen": {
        "lat": 24.45, "lon": 118.39,
        "location_type": "contested_feature",
        "description": "Kinmen Islands. ROC-controlled archipelago ~2 km from PRC Fujian coast.",
    },
    "matsu": {
        "lat": 26.16, "lon": 119.95,
        "location_type": "contested_feature",
        "description": "Matsu Islands. ROC-controlled; close to Fuzhou.",
    },
    "pratas_dongsha": {
        "lat": 20.71, "lon": 116.72,
        "location_type": "contested_feature",
        "description": "Pratas Islands (Dongsha). ROC-administered atoll in northern SCS.",
    },

    # ── Capitals (for diplomatic / political reference) ────────────────────
    "taipei": {
        "lat": 25.04, "lon": 121.56,
        "location_type": "capital",
        "description": "Taipei, Republic of China capital.",
    },
    "beijing": {
        "lat": 39.90, "lon": 116.41,
        "location_type": "capital",
        "description": "Beijing, PRC capital; CMC/CCP HQ.",
    },
    "tokyo": {
        "lat": 35.68, "lon": 139.69,
        "location_type": "capital",
        "description": "Tokyo, Japan capital; Cabinet and NSS HQ.",
    },
    "washington_dc": {
        "lat": 38.91, "lon": -77.04,
        "location_type": "capital",
        "description": "Washington D.C., US capital; NCA, Pentagon, NSC.",
    },
}
