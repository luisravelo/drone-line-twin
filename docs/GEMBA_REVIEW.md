# Repo gemba walk — 2026-10-08

Walked every tracked and untracked file. Goal: keep what adds value to the demo / the source code a reviewer
would read, flag what can go, and remove waste in the code without changing the simulation logic.

## Waste removed in the code (results byte-identical, verified with SHA-1 of all 20 output files)

| Waste | Fix | Effect |
|---|---|---|
| Every scenario was simulated twice (main run = replication day 1, same seed) | `run_replications(first=report.summary)` reuses the main run | 4 of 84 runs saved |
| 80 replication days ran in series | One shared `ProcessPoolExecutor` for all scenarios (small runs/tests stay in-process) | |
| Lognormal mu/sigma recomputed on every sample (~500 k calls) | `Dist._lognormal` cached once per distribution | |
| **Total** | | `run.py` **41 s -> 10 s**; tests unchanged at ~3 s |

## Adds value (keep)

- `src/dronetwin/*`, `config/*`, `tests/*`, `run.py`: the source code a reviewer reads. Clean module boundaries,
  scenario = YAML, deterministic, 32 tests.
- `blender/*.py`: the 3D twin is fully rebuildable from the state feed (no hand edits in the .blend).
- `cad/mesh/MODEL_A.obj`, `MODEL_B.obj` (used by Blender), `cad/usd/*.usdz` (Omniverse-ready).
- `cad/renders/concept_*.png`, `blender_line_*.png` (README / slides).
- `docs/specs/2026-10-05-drone-line-twin-design.md`, `docs/BOM_and_assembly.md`.

## Candidates to discard (decision for the owner, nothing deleted)

| File(s) | Why | Suggestion |
|---|---|---|
| `cad/mesh/MODEL_A.stl`, `MODEL_B.stl` (12.8 MB in git) | Not referenced anywhere; Blender uses the OBJ | delete |
| `cad/renders/ModelA_Linked*.png`, `ModelB_Linked*.png` | Previous drone designs (replaced by MODEL_A/B GA) | delete or move to an archive folder |
| `docs/plans/2026-10-05-des-core-and-exports.md` (93 KB) | Superseded plan (CNC/AM cells, AGV marriage) | move to `docs/archive/` |
| Push upstream path in `paced_line.py` (`_upstream`, `booths`, `paint_booths`) | All 4 scenarios run pull now | either delete, or keep and add a **push vs pull** scenario (good A/B story: WIP and lead time) |
| `blender/render_clip.py` | Renders were dropped in favour of viewport playback | keep only if a video backup is wanted |
| `blender/drone_line_twin.blend` (126 MB), `cad/*.step`, `cad/dummy_assembled.blend` (~85 MB) | Large binaries; regenerable or vendor sources | keep out of git (now in `.gitignore`); use Git LFS or Drive if they must be shared |

## Gaps (not waste, but missing value)

- `docs/specs/...design.md` predates the pull flow, the conveyors and the logistics layer: update §3-4.
- No push-vs-pull or kitting comparison yet: the event log already has element-level timing to quantify the
  non-value-added walking that a travelling kit would remove.
- The HTML viewer's live tab is 2D blocks; the 3D layout (transfers, totes, warehouse) lives only in Blender.
