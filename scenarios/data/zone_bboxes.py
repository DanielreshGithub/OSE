"""Bounding boxes per named zone — used by zone-control derivation.

Each entry: ``{lat_min, lat_max, lon_min, lon_max}``. Boxes are deliberately
generous to capture units operating in the broader theater of the zone, not
just the strict geographic centroid. They are approximations suitable for
"is this unit credibly affecting this zone" — not precise maritime boundaries.

Coordinates derived from publicly-available geographic features (IHO maritime
limits, EEZ approximations, common reporting conventions). For OSE engine
purposes, exact boundaries are less important than internal consistency.

Reviewed: 2026-05.
"""
from __future__ import annotations
from typing import Dict, TypedDict


class ZoneBBox(TypedDict):
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


ZONE_BBOXES: Dict[str, ZoneBBox] = {
    "taiwan_strait": {
        "lat_min": 22.5, "lat_max": 26.5,
        "lon_min": 118.0, "lon_max": 122.0,
    },
    "bashi_channel": {
        "lat_min": 20.5, "lat_max": 22.5,
        "lon_min": 120.0, "lon_max": 122.0,
    },
    "luzon_strait": {
        "lat_min": 19.5, "lat_max": 22.0,
        "lon_min": 120.5, "lon_max": 122.5,
    },
    "miyako_strait": {
        "lat_min": 24.0, "lat_max": 26.5,
        "lon_min": 124.0, "lon_max": 126.5,
    },
    "tsugaru_strait": {
        "lat_min": 41.0, "lat_max": 41.8,
        "lon_min": 139.8, "lon_max": 141.5,
    },
    "east_china_sea": {
        "lat_min": 26.0, "lat_max": 33.0,
        "lon_min": 121.0, "lon_max": 130.0,
    },
    "south_china_sea": {
        "lat_min": 5.0, "lat_max": 23.0,
        "lon_min": 105.0, "lon_max": 121.0,
    },
    "senkaku_islands": {
        "lat_min": 25.5, "lat_max": 26.2,
        "lon_min": 123.0, "lon_max": 124.0,
    },
}


def zone_contains(zone_id: str, lat: float, lon: float) -> bool:
    """Return True iff (lat, lon) falls inside the named zone's bbox.

    Unknown zones return False — callers using legacy zone strings without a
    bbox entry get no spatial derivation (their contested_zones value stays
    at whatever the scenario seeded).
    """
    bbox = ZONE_BBOXES.get(zone_id)
    if bbox is None:
        return False
    return (
        bbox["lat_min"] <= lat <= bbox["lat_max"]
        and bbox["lon_min"] <= lon <= bbox["lon_max"]
    )
