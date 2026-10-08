# Drone Line Twin — Design Spec (rev 2: GA-style paced line)

**Date:** 2026-10-05, rev 2 2026-10-06 · **Deadline:** interview Thursday 2026-10-08 (Hadrian Automation,
Lead Factory Simulation / Digital Twin Engineer)

## 1. Goal

A lightweight, reproducible Digital Twin + Discrete Event Simulation (DES) of a high-mix 5" FPV drone
**General Assembly (GA)** line, built like a car plant: the frame arrives finished and painted (the "body"),
and GA adds the bought-in parts on a paced skillet line. It demonstrates:
- **DES logic:** paced line, takt, variability, line stops, line balancing.
- **Data pipelines:** YAML in → Pandas event log → KPIs.
- **Systems thinking:** configure-to-order options and colour-matched parts rippling into kitting and quality.

**Interview deliverables**
1. Pre-rendered MP4 of the 3D replay (Blender), the primary demo asset with zero live risk.
2. Static HTML dashboard (Plotly): KPIs, line balance, line stops.
3. Clean Git repo with README.
4. Live backup: `python run.py --scenario baseline`, plus the `consolidated` what-if.

**Non-goals:** live streaming to Blender/Omniverse, real machine connectivity, GUI editors, building-level layout.
Kit-container fleets per SKU, AMRs and goods-to-person are deferred (later phase).

## 2. Carried-over Digital Twin conventions (from a previous plant digital twin)

- **Asset IDs:** one stable `asset_id` per station, buffer and skillet, reused in the DES, 3D, USD and telemetry.
- **Prim paths:** ISA-95 hierarchy, `/World/Mesa/DroneLine/<Area>/<asset_id>`.
- **ISO 23247 split:** geometry ≠ material-flow logic ≠ state feed. `state_feed.json` is the contract that live
  telemetry (OPC UA / MQTT) would fill.
- **Units:** meters, **Z-up everywhere**. The detail budget goes to movers (skillets, drones).

## 3. Product, options and BOM

### 3.1 Models and colours (body = frame, printed and painted upstream)

| Model | Frame source | Colours (exclusive to the model) |
|---|---|---|
| MODEL_A | PA-001-DF7 frame | Stealth Black (BLK), Racing Red (RED) |
| MODEL_B | SpeedyBee Master 5 HD frame | Volt Yellow (YEL), Moon Silver (SLV) |

- **Unpainted body:** white, as it leaves the printer before paint.
- **Single-body files:** `MODEL_A` / `MODEL_B` in Fusion, with fasteners removed and all parts merged into one body.
- **Meshes:** in `cad/mesh/`.

### 3.2 Customer decisions (order configuration; like model variants on an automotive GA line)

| Decision | MODEL_A | MODEL_B |
|---|---|---|
| D1 Colour | BLK / RED | YEL / SLV |
| D2 Propeller | `PN-PROP-5-TRI` / `PN-PROP-5-BI` | same |
| D3 Battery | fixed `PN-BAT-6S` | `PN-BAT-6S` / `PN-BAT-6S-LR` |
| SKUs | 2 × 2 = 4 | 2 × 2 × 2 = 8 |

**12 SKUs**, code `<model>-<colour>-<prop>[-<battery>]`, e.g. `A-BLK-TRI`, `B-SLV-BI-LR`.

- **Colour-matched controller (dependent part):** `PN-ESC-FC-STACK-<colour>` must match the frame colour.
  - It isn't a customer choice, so the SKU count stays 12, but the line carries **4 controller footprints**.
  - Kitting picks it by colour, and final inspection verifies the match.

### 3.3 BOM per drone

| PN | Description | Qty | Station |
|---|---|---|---|
| `MODEL_A` / `MODEL_B` | Painted frame (body) | 1 | loaded from PBS |
| `PN-MOT-2207` | Motor 2207 | 4 | ST10 |
| `PN-HW-M3x12` | M3 × 12 screw (motor) | 16 | ST10 |
| `PN-ESC-FC-STACK-<colour>` | SpeedyBee F405 Mini 20 × 20 stack | 1 | ST20 |
| `PN-HW-M3x12` | M3 × 12 screw (controller) | 4 | ST20 |
| `PN-CAM-FPV` | 19 mm FPV camera, on the frame pivot holes | 1 | ST30 |
| `PN-ANT-VTX` | Stubby VTX antenna, tail mount | 2 | ST40 |
| `PN-PROP-5-TRI` / `-BI` | Propeller (D2) | 4 | ST50 |
| `PN-HW-M5-PROPNUT` | M5 prop nut | 4 | ST50 |
| `PN-BAT-6S` / `-LR` | Battery (D3; MODEL_A fixed STD) | 1 | ST60 |
| `PN-STRAP-BAT` | Battery strap | 1 | ST60 |

- **Torque rundowns per drone:** 24 (16 motor + 4 controller + 4 prop nut), the same for both models.
- **Camera and antennas:** placements with no fasteners.
- **Reference assemblies:** `MODEL_A_GA` / `MODEL_B_GA` in Fusion, with fastener groups `HW_ST10_Motor`,
  `HW_ST20_Stack` and `HW_ST50_PropNut`.

## 4. System and line flow

```
OUTSIDE THE ANALYSED SYSTEM (fixed times)                 ANALYSED SYSTEM: GA paced line
3D print farm ──► Paint booths ──► PBS (painted body storage) ──► ST00 Load frame on skillet
 (white body)     (colour per order)   sequenced to GA order          ↓ index every takt
                                                                   ST10 Motors   (4 motors, 16 torques)
Order release (12 SKUs) ──► Kitting (kit per serial,               ST20 Controller (colour-matched, 4 torques)
                            colour-matched controller) ──► kit     ST30 Camera
                            rides on the skillet                   ST40 Antennas (2)
                                                                   ST50 Props (4 props, 4 prop-nut torques)
                                                                   ST60 MARRIAGE (battery + strap)
                                                                   ST70 Final inspection ──► Ship
                                                                        │ NOK (colour mismatch, torque NOK)
                                                                        └► Off-line repair ──► Ship
Skillets: fixed fleet of 10 (8 positions on the line + 2 on the return conveyor).
```

### 4.1 Upstream (fixed times, not analysed)

| Step | Time | Capacity |
|---|---|---|
| Print MODEL_A | 4.5 min per frame | 1 printer (aggregated print farm) |
| Print MODEL_B | 5.5 min per frame | same printer |
| Paint | 4 min per frame | 1 paint booth |
| PBS | buffer, capacity 40 | resequences to the GA order |

Upstream is one aggregated printer and one paint booth with fixed times per frame (free to tune): about 12 frames/h
from print at a 50/50 mix, 15/h from paint, vs 10 JPH demand. It keeps PBS ahead of GA; the model only checks that GA is never starved of bodies
(reported as a KPI).

### 4.2 GA line logic: paced, fixed takt
- **Indexing:** all skillets index together every takt, with a fixed 6 s index time.
- **Line stop:** a station that hasn't finished its work content when takt ends stops the line until it finishes.
  The stop time is attributed to that station (the andon pull).
- **Output:** line output = 1 drone per completed takt cycle; actual cycle = max(takt, slowest station's work + index).
- **Demand-driven takt:** one 8 h shift, 80 jobs/day → takt = 28 800 s / 80 = **360 s (10 JPH)**.
  Takt comes from demand, not from line capacity; the demand distribution can be varied later.
- **Baseline:** 8 positions (ST00–ST70) at 360 s takt. Every station is under takt (ST10 at 51 %), so the KPI story is
  balance loss: idle operators, not line stops.
- **What-if `consolidated`:** minimum stations for the same takt. ST00 Load (25 s) | ST10 Motors + Controller (267 s,
  74 %) | ST20 Camera + Antennas + Props + Marriage (180 s, 50 %) | ST70 Final inspection (110 s). That's 3 work stations
  instead of 7; the trade-off is that ST10's slow tail now causes some line stops.

### 4.4 Growth scenario (demand-driven rebalance)
- **Demand:** 180 drones per 8 h shift, so takt = 160 s (22.5 JPH). Upstream: 2 printers, 2 paint booths.
- **Minimum positions vs takt** (contiguous blocks in assembly order):

  | Positions | Feasible takt |
  |---|---|
  | 8 | ≥ 190 s |
  | 6 | ≥ 146 s |
  | 5 | ≥ 175 s |

  So 6 positions is the minimum for any takt from 146 s to 175 s.
- **`growth_6pos`, balanced to a realistic pace (≤ ~85 % station load):** ST00 load + camera 65 s (42 %) ·
  ST10 motors 1–2 92 s · ST20 motors 3–4 92 s · ST30 controller + antennas 123 s (80 %, heaviest) ·
  ST40 props + marriage 100 s · ST50 inspection 110 s.
  - Precedence: the camera mounts on the frame pivots with no dependency, and its connector is plugged
    with the controller. Antennas follow the controller (VTX on the stack).
  - Result (20 days): 179.9 / 180 per day, 98 % takt attainment, about 21 s of line stops per day (ST30).
  - The first cut at 140 s (91 %) stopped 16 % of cycles.
- **`growth_8pos`:** today's line at the new takt. ST10 (184 s) overruns every cycle.
- **Warm-up:** 30–60 min (fill every position plus the first print/paint), not a full shift.

### 4.3 Work elements and time distributions (seconds)
`LogN(mean, sd)` for manual work, `Norm(mean, sd)` floored at 0.5 × mean for scripted or automated work.

| Element | Distribution | Used at |
|---|---|---|
| Load frame on skillet | Norm(25, 3) | ST00 |
| Place motor (incl. lead routing) | LogN(18, 4) | ST10 × 4 |
| M3 torque rundown (MES-connected DC tool) | LogN(7, 1.5) | ST10 × 16, ST20 × 4 |
| Torque NOK → re-hit | 1.5 % per rundown, + LogN(15, 5) | ST10, ST20, ST50 |
| Place controller + plug motor leads | LogN(55, 10) | ST20 |
| Install camera on pivot + connect + set tilt | LogN(40, 8) | ST30 |
| Install antenna + route coax | LogN(20, 5) | ST40 × 2 |
| Place prop | LogN(6, 1.5) | ST50 × 4 |
| M5 prop-nut torque | LogN(9, 2) | ST50 × 4 |
| Place battery | LogN(15, 3) | ST60 |
| Strap battery (marriage) | LogN(25, 6) | ST60 |
| Final inspection (bench test + visual) | Norm(90, 10) + LogN(20, 5) | ST70 |
| Off-line repair (wrong-colour controller swap) | LogN(300, 60) | repair bay |

| Station | Mean work content (s) | Share of 360 s takt |
|---|---|---|
| ST10 | 184 | 51 % (heaviest) |
| ST70 | 110 | 31 % |
| ST20 | 83 | 23 % |
| ST50 | 60 | 17 % |
| ST30, ST40, ST60 | 40 each | 11 % |
| ST00 | 25 | 7 % |

**Quality injection:** a kitting pick error on the controller colour at 0.5 % per kit is detected at ST70,
which sends the drone off-line to repair. This demonstrates why colour-matched parts are a kitting risk.

**Order mix (baseline):**
- Model: A 50 % / B 50 %.
- Colour: 50 / 50 within each model.
- Prop: TRI 60 % / BI 40 %.
- MODEL_B battery: STD 70 % / LR 30 %.

## 5. Architecture

```
drone-line-twin/
├─ config/  bom.yaml · skus.yaml · stations.yaml (work elements) · layout.yaml · scenarios/{baseline,consolidated}.yaml
├─ src/dronetwin/
│  ├─ distributions.py  # Norm / LogN / Tria / Exp, one seeded stream per asset
│  ├─ catalog.py        # BOM, SKUs (valid combinations only), colour-match rule, work elements
│  ├─ engine.py         # event log, tracked queues
│  ├─ paced_line.py     # skillet fleet, takt index, line-stop attribution, off-line repair
│  ├─ upstream.py       # fixed-time print/paint → PBS (outside the analysed boundary)
│  ├─ metrics.py        # JPH, takt attainment, line stops, balance chart, NOK, mix in/out
│  ├─ telemetry.py      # terminal status
│  └─ export/  dashboard.py · state_feed.py · usd.py
├─ blender/replay.py    # state_feed → keyframes (Z-up)
├─ cad/                 # STEP sources, mesh/ exports, renders/
└─ run.py · tests/
```

## 6. Data contracts

**Event log** (single source of truth) → `out/events.csv`:
`t, asset_id, prim_path, event, state, pn, serial, sku, x, y, queue_len`

`event ∈ {RELEASE, PBS_IN, LOAD, INDEX, ELEMENT_START, ELEMENT_END, TORQUE_OK, TORQUE_NOK, LINE_STOP,
LINE_RESUME, INSPECT_OK, INSPECT_NOK, REPAIR, SHIP, STATE}`

**KPIs:**
- output: JPH by model / SKU, jobs per day vs the 80-job demand
- balance loss: 1 − Σ work / (stations × takt), and operator utilization
- takt attainment: % of cycles finished within takt
- line-stop time by station
- line balance: mean work content per station vs takt
- torque: NOK rate per station
- quality: colour-mismatch detections
- mix: SKU mix in vs out
- PBS starvation: should be 0

**Bottleneck:** the station with the largest share of line-stop time, cross-checked with work content / takt.

**`state_feed.json` / USD:** as in rev 1, keyed by `asset_id` + `prim_path`. Skillets carry the serial and SKU,
so the replay paints each drone in its order colour.

## 7. 3D scene and video

- **Assets:**
  - `MODEL_A` / `MODEL_B` meshes (white).
  - Colour = order colour from the feed.
  - GA parts appear station by station, taken from the `*_GA` references.
- **Scene:** a straight paced line of 8 positions (ST00–ST70), a skillet return conveyor, the PBS rack, and
  the print farm and paint booth as context. Operators come later (`cad/dummy_assembled.blend`).
- **Video:**
  1. Bodies arrive white, then painted.
  2. Skillets index along the line, with parts added at each station.
  3. A line stop at ST10 (andon), shown with state colours.
  4. A colour-mismatch catch at ST70.
  5. Time-lapse with KPIs.

## 8. Testing / verification

- **Reproducibility:** same seed gives an identical event log.
- **Throughput:** shipped ≤ completed takt cycles; actual cycle ≥ takt + index.
- **Line stops:** total line-stop time equals the sum of the per-station overrun attributions.
- **Mix:** SKU mix out matches mix in (excluding WIP).
- **Colour match:** every shipped unit has a controller matching its frame colour; mismatches only before ST70 NOK.
- **What-if:** `consolidated` uses 3 work stations instead of 7 and still meets 10 JPH ± line-stop losses.

## 9. Schedule

| Day | Work |
|---|---|
| Tue 10-06 | 3D models complete (done); spec/BOM rev 2; config + paced-line engine + tests |
| Wed 10-07 | Metrics, dashboard, state feed; Blender line scene + replay; render; README; rehearsal |

## 10. Risks

- Fusion MCP 15 s client timeout: long calls report a timeout but complete; always verify before the next call.
- Render time: EEVEE at 1080p; render the detail and time-lapse segments separately.
- Dependencies: `simpy`, `pandas`, `pyyaml`, `plotly`, `numpy`; `usd-core` optional.
