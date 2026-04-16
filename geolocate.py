#!/usr/bin/env python3
"""
Drone frame geolocation analysis tool.

Computes sun position, camera heading, and candidate locations
for a drone frame captured on 21.03.2026 at 16:58:44.

Search area: 25 km radius around 49.17253°N, 37.25877°E (near Izium, Ukraine)
"""

import math
from dataclasses import dataclass


@dataclass
class GeoPoint:
    name: str
    lat: float
    lon: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two points."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees (0=N, 90=E, 180=S, 270=W)."""
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(dlon))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) / 22.5) % 16]


def sun_position(lat: float, lon: float, dec_deg: float,
                 local_hour: float, utc_offset: int, eot_min: float):
    """
    Compute sun altitude and azimuth.

    Args:
        lat: observer latitude (degrees)
        lon: observer longitude (degrees)
        dec_deg: solar declination (degrees)
        local_hour: local clock time as decimal hours (e.g. 16.97)
        utc_offset: timezone offset in hours (e.g. 2 for UTC+2)
        eot_min: equation of time in minutes (negative = sun behind mean sun)
    """
    std_meridian = utc_offset * 15.0
    solar_noon_min = 720 - eot_min - 4 * (lon - std_meridian)
    solar_noon_h = solar_noon_min / 60

    ha_hours = local_hour - solar_noon_h
    ha = math.radians(ha_hours * 15)

    lat_r = math.radians(lat)
    dec_r = math.radians(dec_deg)

    sin_alt = (math.sin(lat_r) * math.sin(dec_r)
               + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha))
    alt = math.asin(max(-1, min(1, sin_alt)))

    cos_az = (math.sin(dec_r) - math.sin(alt) * math.sin(lat_r)) / (
        math.cos(alt) * math.cos(lat_r))
    cos_az = max(-1, min(1, cos_az))
    az = math.acos(cos_az)
    if ha > 0:
        az = 2 * math.pi - az  # afternoon: sun is in the west

    return math.degrees(alt), math.degrees(az), solar_noon_h


def main():
    # === PARAMETERS ===
    CENTER = GeoPoint("Search center", 49.17252599817238, 37.25876955636144)
    RADIUS_KM = 25.0

    # Frame metadata
    frame_date = "2026-03-21"
    frame_time_decimal = 16 + 58 / 60  # 16:58
    solar_declination = 0.0  # spring equinox
    eot_minutes = -7.5  # equation of time for March 21

    print("=" * 70)
    print("DRONE FRAME GEOLOCATION ANALYSIS")
    print("=" * 70)
    print(f"Frame: {frame_date} {int(frame_time_decimal)}:{int((frame_time_decimal%1)*60):02d}")
    print(f"Center: {CENTER.lat:.5f}°N, {CENTER.lon:.5f}°E")
    print(f"Radius: {RADIUS_KM} km")
    print()

    # === SUN POSITION ===
    print("-" * 70)
    print("SUN POSITION")
    print("-" * 70)
    for tz_name, tz_offset in [("EET (UTC+2)", 2), ("EEST (UTC+3)", 3)]:
        alt, az, noon = sun_position(
            CENTER.lat, CENTER.lon, solar_declination,
            frame_time_decimal, tz_offset, eot_minutes
        )
        print(f"  {tz_name}:")
        print(f"    Solar noon:  {int(noon)}:{int((noon%1)*60):02d}")
        print(f"    Sun altitude: {alt:.1f}°")
        print(f"    Sun azimuth:  {az:.1f}° ({compass(az)})")
    print()
    print("  => Camera heading estimate: 250°-262° (WSW to W)")
    print()

    # === KNOWN LOCATIONS ===
    print("-" * 70)
    print("KNOWN LOCATIONS (distances from center)")
    print("-" * 70)

    locations = [
        GeoPoint("Izium (city)", 49.2283, 37.2598),
        GeoPoint("Brazhkivka", 49.04194, 37.21584),
        GeoPoint("Sulyhivka", 49.029845, 37.24390),
        GeoPoint("Virnopillya", 49.03179, 37.12580),
        GeoPoint("Bereka River (ref)", 49.17064, 36.97872),
    ]

    for loc in locations:
        d = haversine_km(CENTER.lat, CENTER.lon, loc.lat, loc.lon)
        b = bearing_deg(CENTER.lat, CENTER.lon, loc.lat, loc.lon)
        inside = "YES" if d <= RADIUS_KM else "NO"
        print(f"  {loc.name:25s}  {d:5.1f} km  {b:5.1f}° ({compass(b):3s})  in radius: {inside}")
    print()

    # === ROAD-HEADING MATCH ===
    print("-" * 70)
    print("ROAD-HEADING CORRELATION")
    print("-" * 70)
    braz = GeoPoint("Brazhkivka", 49.04194, 37.21584)
    virn = GeoPoint("Virnopillya", 49.03179, 37.12580)
    road_bearing = bearing_deg(braz.lat, braz.lon, virn.lat, virn.lon)
    road_dist = haversine_km(braz.lat, braz.lon, virn.lat, virn.lon)
    print(f"  Road: {braz.name} -> {virn.name}")
    print(f"  Bearing: {road_bearing:.1f}° ({compass(road_bearing)})")
    print(f"  Distance: {road_dist:.1f} km")
    print(f"  Camera heading: 250°-262° (WSW)")
    match_quality = "EXACT MATCH" if 248 <= road_bearing <= 264 else "PARTIAL"
    print(f"  Correlation: *** {match_quality} ***")
    print()

    # === ESTIMATE ===
    print("-" * 70)
    print("LOCATION ESTIMATE")
    print("-" * 70)
    est = GeoPoint("Estimated drone position", 49.05, 37.17)
    est_dist = haversine_km(CENTER.lat, CENTER.lon, est.lat, est.lon)
    est_bear = bearing_deg(CENTER.lat, CENTER.lon, est.lat, est.lon)
    print(f"  Position:  {est.lat:.2f}°N, {est.lon:.2f}°E (±5 km)")
    print(f"  From center: {est_dist:.1f} km at {est_bear:.0f}° ({compass(est_bear)})")
    print(f"  Heading:   ~260° (WSW)")
    print(f"  River:     Bereka tributary or Iziumets tributary")
    print(f"  Road:      Brazhkivka-Virnopillya corridor")
    print()
    print("  Confidence:")
    print("    General area (S of Izium):     HIGH")
    print("    Camera heading (WSW):          HIGH")
    print("    Road corridor match:           HIGH")
    print("    River identification:          MEDIUM")
    print("    Exact coordinates:             LOW (needs satellite imagery)")
    print()

    # === VERIFICATION ===
    print("-" * 70)
    print("NEXT STEPS FOR EXACT GEOLOCATION")
    print("-" * 70)
    print("  1. Open satellite imagery at ~49.05°N, 37.17°E")
    print("  2. Find where the Brazhkivka-Virnopillya road crosses a stream")
    print("  3. Match the meander pattern against the drone frame")
    print("  4. Simulate 3D view from ~100m altitude looking 260° WSW")
    print("  5. Verify horizon features (distant settlements)")


if __name__ == "__main__":
    main()
