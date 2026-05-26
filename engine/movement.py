"""Movement resolver — spatial mechanics for the Unit layer.

Pure functions: no state, no side effects beyond mutating the Unit instance
passed to ``move_unit_toward``. All distance computations use the haversine
formula over a spherical-Earth approximation (radius 6371 km) — accurate to
within ~0.5% for the Indo-Pacific theater, which is more than precise enough
for the per-turn granularity OSE operates at.

Phase B contract: actions carrying ``unit_ids`` invoke ``move_unit_toward`` per
turn. Units transition standby → transit → on_station as they approach a
destination within range. Out-of-range destinations fail validation upstream
in ``BaseAction.is_valid``; this module trusts its inputs.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional, Tuple

from world.state import Unit


EARTH_RADIUS_KM = 6371.0
ARRIVAL_THRESHOLD_KM = 25.0  # If a unit is within this distance of its destination,
                              # it is considered on-station rather than in-transit.


def compute_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points using haversine."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def move_unit_toward(
    unit: Unit,
    destination_lat: float,
    destination_lon: float,
    max_range_km: Optional[float] = None,
) -> Unit:
    """Mutate ``unit`` to advance toward (destination_lat, destination_lon).

    If the unit reaches within ``ARRIVAL_THRESHOLD_KM`` of the destination,
    state becomes ``on_station`` and destination fields clear. Otherwise the
    unit advances at most ``max_range_km`` (or ``unit.range_km_per_turn`` if
    ``max_range_km`` is None) along the great-circle bearing.

    Returns the same unit instance for chaining. Pure-spherical model — does
    not account for terrain, sea-state, fuel, ROE, or detection.
    """
    if max_range_km is None:
        max_range_km = unit.range_km_per_turn

    distance = compute_distance_km(unit.lat, unit.lon, destination_lat, destination_lon)

    # Arrival check
    if distance <= ARRIVAL_THRESHOLD_KM:
        unit.lat = destination_lat
        unit.lon = destination_lon
        unit.state = "on_station"
        unit.destination_lat = None
        unit.destination_lon = None
        return unit

    # If the unit can cover the full remaining distance in this turn, snap to destination
    if max_range_km > 0 and max_range_km >= distance:
        unit.lat = destination_lat
        unit.lon = destination_lon
        unit.state = "on_station"
        unit.destination_lat = None
        unit.destination_lon = None
        return unit

    # Partial transit: interpolate along the great-circle bearing
    if max_range_km <= 0:
        # Immobile unit; record intent but stay put
        unit.destination_lat = destination_lat
        unit.destination_lon = destination_lon
        return unit

    fraction = max_range_km / distance
    new_lat, new_lon = _interpolate_along_great_circle(
        unit.lat, unit.lon, destination_lat, destination_lon, fraction
    )
    unit.lat = round(new_lat, 4)
    unit.lon = round(new_lon, 4)
    unit.state = "transit"
    unit.destination_lat = destination_lat
    unit.destination_lon = destination_lon
    return unit


def _interpolate_along_great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float,
) -> Tuple[float, float]:
    """Spherical linear interpolation (slerp) between two lat/lon points.

    ``fraction`` in [0, 1]: 0 returns origin, 1 returns destination.
    Standard slerp on the unit sphere; accurate for any pair of points on Earth.
    """
    phi1 = math.radians(lat1)
    lambda1 = math.radians(lon1)
    phi2 = math.radians(lat2)
    lambda2 = math.radians(lon2)

    # Convert to Cartesian on the unit sphere
    x1 = math.cos(phi1) * math.cos(lambda1)
    y1 = math.cos(phi1) * math.sin(lambda1)
    z1 = math.sin(phi1)
    x2 = math.cos(phi2) * math.cos(lambda2)
    y2 = math.cos(phi2) * math.sin(lambda2)
    z2 = math.sin(phi2)

    # Angular distance between the two points
    dot = max(-1.0, min(1.0, x1 * x2 + y1 * y2 + z1 * z2))
    omega = math.acos(dot)

    if omega < 1e-9:
        # Points coincide; nothing to interpolate
        return lat1, lon1

    sin_omega = math.sin(omega)
    a = math.sin((1 - fraction) * omega) / sin_omega
    b = math.sin(fraction * omega) / sin_omega

    x = a * x1 + b * x2
    y = a * y1 + b * y2
    z = a * z1 + b * z2

    new_phi = math.atan2(z, math.sqrt(x * x + y * y))
    new_lambda = math.atan2(y, x)
    return math.degrees(new_phi), math.degrees(new_lambda)


def units_within_radius(
    units: Iterable[Unit],
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> List[Unit]:
    """Return all units within ``radius_km`` of the given center point."""
    return [
        u for u in units
        if compute_distance_km(u.lat, u.lon, center_lat, center_lon) <= radius_km
    ]


def unit_can_reach(
    unit: Unit,
    destination_lat: float,
    destination_lon: float,
    turns: int = 1,
) -> bool:
    """True iff ``unit`` can reach the destination within ``turns`` turns at
    its current ``range_km_per_turn``. Immobile units (range=0) return True
    only if they are already at the destination."""
    distance = compute_distance_km(unit.lat, unit.lon, destination_lat, destination_lon)
    if unit.range_km_per_turn <= 0:
        return distance <= ARRIVAL_THRESHOLD_KM
    return distance <= unit.range_km_per_turn * turns
