# BOM and GA assembly sequence — MODEL_A and MODEL_B (rev 2)

**Fusion sources:** `ROBOTICS / DRONE ASSY LINE` (`MODEL_A_GA`, `MODEL_B_GA`, `Shared_Components`).
Counts were read from those assemblies on 2026-10-06.

## Customer decisions (12 SKUs)

| Decision | MODEL_A | MODEL_B |
|---|---|---|
| D1 Colour | Stealth Black (BLK), Racing Red (RED) | Volt Yellow (YEL), Moon Silver (SLV) |
| D2 Propeller | TRI / BI | TRI / BI |
| D3 Battery | fixed `PN-BAT-6S` | STD `PN-BAT-6S` / LR `PN-BAT-6S-LR` |

| SKU | Frame colour | Prop | Battery | Controller (derived) |
|---|---|---|---|---|
| A-BLK-TRI | BLK | TRI | STD | `PN-ESC-FC-STACK-BLK` |
| A-BLK-BI | BLK | BI | STD | `PN-ESC-FC-STACK-BLK` |
| A-RED-TRI | RED | TRI | STD | `PN-ESC-FC-STACK-RED` |
| A-RED-BI | RED | BI | STD | `PN-ESC-FC-STACK-RED` |
| B-YEL-TRI-STD | YEL | TRI | STD | `PN-ESC-FC-STACK-YEL` |
| B-YEL-TRI-LR | YEL | TRI | LR | `PN-ESC-FC-STACK-YEL` |
| B-YEL-BI-STD | YEL | BI | STD | `PN-ESC-FC-STACK-YEL` |
| B-YEL-BI-LR | YEL | BI | LR | `PN-ESC-FC-STACK-YEL` |
| B-SLV-TRI-STD | SLV | TRI | STD | `PN-ESC-FC-STACK-SLV` |
| B-SLV-TRI-LR | SLV | TRI | LR | `PN-ESC-FC-STACK-SLV` |
| B-SLV-BI-STD | SLV | BI | STD | `PN-ESC-FC-STACK-SLV` |
| B-SLV-BI-LR | SLV | BI | LR | `PN-ESC-FC-STACK-SLV` |

The controller colour isn't a customer choice: it's derived from the frame colour (4 footprints, 12 SKUs).

## BOM per drone

| PN | Description | MODEL_A | MODEL_B |
|---|---|---|---|
| `MODEL_A` / `MODEL_B` | Painted frame (body), printed + painted upstream | 1 | 1 |
| `PN-MOT-2207` | Motor 2207 | 4 | 4 |
| `PN-ESC-FC-STACK-<colour>` | SpeedyBee F405 Mini 20 × 20 stack, colour-matched | 1 | 1 |
| `PN-CAM-FPV` | 19 mm FPV camera | 1 | 1 |
| `PN-ANT-VTX` | Stubby VTX antenna | 2 | 2 |
| `PN-PROP-5-TRI` / `-BI` | Propeller (D2) | 4 | 4 |
| `PN-BAT-6S` / `-LR` | Battery | 1 (STD) | 1 (D3) |
| `PN-STRAP-BAT` | Battery strap | 1 | 1 |
| `PN-HW-M3x12` | M3 × 12 screw | 20 | 20 |
| `PN-HW-M5-PROPNUT` | M5 prop nut | 4 | 4 |

## GA sequence (paced skillet line, takt 360 s = 10 JPH, 80 jobs per 8 h shift)

| Station | Operation | Parts | Torques |
|---|---|---|---|
| ST00 | Load painted frame from PBS onto skillet; kit rides with it | frame | 0 |
| ST10 | Motors | 4 × `PN-MOT-2207`, 16 × M3x12 from under the arms | 16 |
| ST20 | Controller | `PN-ESC-FC-STACK-<colour>`, 4 × M3x12 bottom-up | 4 |
| ST30 | Camera | `PN-CAM-FPV` on the frame pivot holes (nose) | 0 |
| ST40 | Antennas | 2 × `PN-ANT-VTX` on the tail | 0 |
| ST50 | Props | 4 × D2 prop + 4 × `PN-HW-M5-PROPNUT` | 4 |
| ST60 | **Marriage** | battery under the bottom plate + `PN-STRAP-BAT` | 0 |
| ST70 | Final inspection | bench test, visual, controller-colour match | 0 |
| **Total** | | | **24** |

**Fastener groups in Fusion:** `HW_ST10_Motor` (16), `HW_ST20_Stack` (4), `HW_ST50_PropNut` (4).

**Upstream (outside the analysed system, fixed times):**
- Print: 1 aggregated printer, MODEL_A 4.5 min, MODEL_B 5.5 min per frame (about 12/h).
- Paint: 1 booth, 4 min per frame (15/h).
- PBS: buffer, resequenced to the GA order.

**Notes:** MODEL_A has no 20 × 20 controller pattern, so its controller is centred on the arms; MODEL_B uses
its real 20 × 20 holes. Battery models are vendor geometry scaled for proportion.
