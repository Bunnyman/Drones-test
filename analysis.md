# Drone Frame Geolocation Analysis

## Source Image
- **Timestamp:** 21.03.2026 16:58:44
- **OSD Header:** HDr: Kr3-1003 | F: 1480 MHz | T: 16:58:45
- **Watermark:** FBD44F
- **Given search area:** 25 km radius around 49.17253°N, 37.25877°E

---

## 1. OSD Telemetry Extraction

| Field | Value | Interpretation |
|-------|-------|----------------|
| Date/Time | 21.03.2026 16:58:44 | Late afternoon, spring equinox |
| HDr | Kr3-1003 | Hardware/drone identifier |
| Frequency | 1480 MHz | Analog video downlink (L-band) |
| Watermark | FBD44F | Unit or operator hex ID |
| Top-left indicator | ~68 | Likely battery % or signal strength |
| Top-right values | ~470 / ~2100 | Possibly altitude (m) / distance (m) |
| Bottom-left | ~83.0 / Q 21.0 | Possibly speed (km/h) / battery voltage |
| Center dots | Artificial horizon | Drone is approximately level |
| Right-side triangles | Heading/attitude markers | Standard OSD elements |

---

## 2. Sun Position Analysis (Camera Heading)

**Key inputs:**
- Date: 21 March 2026 (spring equinox, solar declination ≈ 0°)
- Time: 16:58 local
- Location: ~49.17°N, 37.26°E
- Timezone: EET (UTC+2) — DST had not yet started on March 21, 2026

**Calculation:**

```
Solar noon (UTC+2): 11:38 local time
  Standard meridian (UTC+2): 30°E
  Longitude correction: (37.26 - 30.00) × 4 min/° = 29.0 min
  Equation of time (Mar 21): ≈ -7.5 min
  Solar noon = 12:00 - 29.0 + 7.5 = 11:38:30

Hour angle at 16:58: (16:58 - 11:38) = 5h 19.5m = 79.9°

Sun altitude: arcsin(cos(49.17°) × cos(79.9°)) = 6.6°
Sun azimuth: 262° from north (WSW-W)
```

**If UTC+3 (EEST):**
- Solar noon: 12:38, hour angle: 64.9°
- Sun altitude: 16.1°, azimuth: 250° (WSW)

**Result:** Sun azimuth = **250°–262°** (WSW to W), altitude 7°–16° (low on horizon)

**Image confirmation:** The bright sun glare/washout is visible in the upper-center to slight-left of the frame, consistent with the camera pointing approximately toward the sun.

**Camera heading estimate: ~250°–262° (WSW to W)**

---

## 3. Terrain Analysis

### Observed features in the image:
1. **River/stream:** Small-to-medium meandering waterway with natural curves, visible in the middle distance (est. 1–4 km from drone)
2. **Road/track:** Straight linear feature running from the foreground toward the horizon, aligned with camera heading (WSW)
3. **Terrain:** Very flat, open agricultural steppe — no forest, no hills, no significant elevation changes
4. **Horizon:** Faint structures or settlements visible in the far distance
5. **Vegetation:** Minimal — bare/early-spring agricultural fields (consistent with March 21)

### Terrain elimination:
- **NOT the Siverskyi Donets valley** — the Donets valley near Izium has forests, flood plains, and oxbow lakes. The image shows treeless steppe.
- **NOT the Donets right-bank escarpment** — the right bank of the Donets has chalk cliffs and gullies. The image shows completely flat terrain.
- **Consistent with:** The elevated agricultural upland south of the Donets river valley, which is characterized by flat, treeless farmland drained by small streams.

---

## 4. Geographic Context

### Center point identification
The given center (49.1725°N, 37.2588°E) is **~6 km south of Izium** (Ізюм), a city on the Siverskyi Donets River in Kharkiv Oblast, Ukraine.

### Rivers within the 25 km search radius

| River | Type | Distance from center | Bearing | Notes |
|-------|------|---------------------|---------|-------|
| Siverskyi Donets | Major river | 6.2 km | N (001°) | Too large, has forests — eliminated |
| Mokryi Iziumets | Small river | ~0–8 km | S | Flows S→N into Donets at Izium |
| Sukhyi Iziumets | Small river | ~0–8 km | S | Flows S→N into Donets at Izium |
| Bereka River | Medium river (102 km) | 13–20 km | W (270°) | Right-bank tributary of Donets |
| Sukhyi Torets | Medium river (101 km) | 20–25 km | SW | Flows through Barvinkove |

### Key settlements with confirmed coordinates

| Village | Latitude | Longitude | Dist. from center | Bearing |
|---------|----------|-----------|-------------------|---------|
| Izium | 49.2283° | 37.2598° | 6.2 km | N |
| Brazhkivka | 49.0419° | 37.2158° | 14.5 km | S |
| Sulyhivka | 49.0298° | 37.2439° | 15.9 km | SSW |
| Virnopillya | 49.0318° | 37.1258° | 17.5 km | SSW |
| Bereka (ref. point) | 49.1706° | 36.9787° | 20.4 km | W |

---

## 5. Road-Heading Correlation

### Critical finding: Brazhkivka → Virnopillya road

The bearing from Brazhkivka (49.042°N, 37.216°E) to Virnopillya (49.032°N, 37.126°E) is:

**260.3° — distance 6.7 km**

This is a **near-exact match** for the camera heading of 250°–262° (WSW).

This road:
- Runs WSW across flat agricultural terrain (matching the image)
- Connects two villages in the Izium Raion area
- Is a minor road/track (matching the straight, narrow feature in the image)
- Crosses terrain that likely has small streams or tributaries draining the upland

---

## 6. River Identification

### Primary hypothesis: Bereka River tributary or local stream

The river visible in the image is most likely:

1. **A section of the Bereka River** — The Bereka (102 km long) flows from SW to NE toward its confluence with the Donets upstream of Izium. Its course passes through the agricultural upland south/southwest of Izium, potentially crossing the Brazhkivka-Virnopillya corridor.

2. **A tributary of the Mokryi/Sukhyi Iziumets** — These rivers flow S→N through the area directly south of Izium. Their headwater tributaries extend into the area near Brazhkivka/Sulyhivka.

3. **A local unnamed stream (балка)** — Small streams and ravines draining the upland are common in this steppe landscape.

### River characteristics matching the image:
- Small-to-medium size (clearly visible but not a major river)
- Natural meanders (not channelized)
- Flows through treeless agricultural terrain
- Crosses or runs near a straight road

---

## 7. Location Estimate

### Best estimate

The drone is most likely in the area south of Izium, looking WSW along or near the Brazhkivka-Virnopillya road corridor:

**Estimated position: ~49.05°N, 37.17°E (±5 km)**

| Parameter | Value | Confidence |
|-----------|-------|------------|
| General area | South of Izium, between Brazhkivka and the center point | HIGH |
| Camera heading | 250°–262° (WSW) | HIGH |
| River identification | Bereka tributary or Iziumets tributary | MEDIUM |
| Road identification | Brazhkivka–Virnopillya road or similar WSW track | MEDIUM |
| Exact position | ~49.05°N, 37.17°E | LOW (needs satellite meander-matching) |

### Distance from center: ~14 km (within 25 km radius)

---

## 8. Verification Steps (requires satellite imagery)

To confirm this location precisely, one would need to:

1. **Open satellite imagery** (Google Earth, Maxar, etc.) at the estimated coordinates
2. **Trace the Brazhkivka-Virnopillya road** and identify where it crosses a meandering stream
3. **Match the meander pattern** of the stream visible in the drone frame against the satellite view
4. **Simulate the drone's perspective** using 3D view from ~100 m altitude, looking WSW (260°)
5. **Verify the horizon** — check if distant settlements match what's faintly visible in the image

### Alternative candidate areas (if primary hypothesis fails):
- Along the Mokryi Iziumets, ~5–8 km south of Izium (near Kamenka village)
- Along a Bereka River section ~15 km west of center
- Along the Sukhyi Torets near Dovhenke (~20 km south of center)

---

## 9. Methodology Summary

```
Step 1: Extract OSD telemetry → date, time, frequency, identifiers
Step 2: Sun position calculation → camera heading (250°–262° WSW)
Step 3: Terrain analysis → flat, treeless agricultural steppe (right-bank Donets upland)
Step 4: River inventory → Bereka, Iziumets, Sukhyi Torets within 25 km
Step 5: Road-heading correlation → Brazhkivka-Virnopillya road at 260.3° = exact match
Step 6: Cross-reference → drone position estimate ~49.05°N, 37.17°E
Step 7: Verification needed → satellite meander matching for precise location
```

---

## Sources

- [Oskil River — Wikipedia](https://en.wikipedia.org/wiki/Oskil_(river))
- [Donets River — Wikipedia](https://en.wikipedia.org/wiki/Donets)
- [Izium — Wikipedia](https://en.wikipedia.org/wiki/Izium)
- [Bereka River — Encyclopedia of Ukraine](https://www.encyclopediaofukraine.com/display.asp?linkpath=pages%5CB%5CE%5CBerekaRiver.htm)
- [Sukhyi Torets — Wikipedia](https://en.wikipedia.org/wiki/Sukhyi_Torets)
- [Battle of Dovhenke — Wikipedia](https://en.wikipedia.org/wiki/Battle_of_Dovhenke)
- [Brazhkivka — Wikipedia](https://en.wikipedia.org/wiki/Brazhkivka)
- [Sulyhivka — Mapcarta](https://mapcarta.com/13730090)
- [Virnopillya — Mapcarta](https://mapcarta.com/13725282)
