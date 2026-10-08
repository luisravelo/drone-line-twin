"""Lineside logistics (exec'd by actors.py): mini totes with real parts, min/max inventory, LOG replenishment.

Inventory is driven by the sim: every consuming ELEMENT_START at a station takes one part from its tote.
When a tote reaches its min, it signals. LOG (large Dummy 13) leaves the backstock table as soon as he is free and
there is at least one signal: loads one full tote per signal, walks the stations in line order, swaps the tote
(back to max) and returns. Signals raised during a trip wait for the next trip. Otherwise LOG organises the
backstock (future kit-building station). Stock-outs are counted and printed (the sim does not starve on parts).
"""
import bisect
import heapq

TOTE_SCALE = {"CAM": 0.2, "MOT": 0.27, "STACK": 0.2, "ANT": 0.3, "PROP": 0.45, "PROP_TRI": 0.27, "PROP_BI": 0.27, "BAT": 0.3}   # sized to hold max
LOG_WALK = 0.35            # m per sim s (slowed for 30x playback, like the other walkers)
LOAD_S, DROP_S = 12.0, 14.0
RUN_S, RUN_T0 = 600.0, 120.0     # milk run: leaves the backstock every 10 min (only if a tote signalled)
PART_LIB = {"CAM": ["LIB_PART_CAM"], "MOT": ["LIB_PART_MOT"], "STACK": ["LIB_PART_STACK"], "ANT": ["LIB_PART_ANT"],
            "PROP": ["LIB_PART_PROP_TRI", "LIB_PART_PROP_BI"], "PROP_TRI": ["LIB_PART_PROP_TRI"],
            "PROP_BI": ["LIB_PART_PROP_BI"], "BAT": ["LIB_PART_BAT"]}
TOTE_DIMS = mesh_dims("LIB_TOTE")
M_STACK_MIX = [mat(f"M_Paint_{c}", COLOURS[c], rough=0.35) for c in ("BLK", "RED", "YEL", "SLV")]


def slots(part, n, scale):
    """Positions inside a tote (tote frame, origin bottom-centre) for n parts, filled in layers."""
    W, D = TOTE_DIMS.x * scale * 0.82, TOTE_DIMS.y * scale * 0.80
    pd = mesh_dims(PART_LIB[part][0])
    if part == "BAT":                                  # batteries stand upright: long axis vertical
        pd = Vector((pd.x, pd.z, pd.y))
    nx, ny = max(1, int(W // (pd.x * 1.1))), max(1, int(D // (pd.y * 1.1)))
    out = []
    for k in range(n):
        layer, r = divmod(k, nx * ny)
        i, j = r % nx, r // nx
        out.append(Vector(((i - (nx - 1) / 2) * W / nx, (j - (ny - 1) / 2) * D / ny, TOTE_DIMS.z * scale * 0.35 + layer * (0.0035 if part.startswith("PROP") else pd.z * 0.9))))   # props nest
    return out


def make_tote(name, coll, loc, part, n, scale, rot_z=0.0, colour=None, libs=None, seq=False):
    t = inst(name, coll, "LIB_TOTE", loc, rot_z=rot_z, scale=scale)
    objs = []
    for k, p in enumerate(slots(part, n, scale)):
        lib_name = (libs or PART_LIB[part])[k % len(libs or PART_LIB[part])]
        o = inst(f"{name}_P{k:02d}", coll, lib_name, (0, 0, 0))
        o.parent = t
        o.location = p / scale
        o.scale = (1 / scale,) * 3
        if part == "BAT":
            o.rotation_euler.x = math.pi / 2
            o.location.z += mesh_dims(lib_name).y / 2 / scale
        if part == "STACK":
            if colour:
                paint(o, mat(f"M_Paint_{colour}", COLOURS[colour], metal=0.6 if colour == "SLV" else 0.0, rough=0.35))
            elif seq:
                paint(o, mat(f"M_SEQ_{name}_{k:02d}", COLOURS["BLK"], rough=0.35))   # keyed to the sequence
            else:
                paint(o, M_STACK_MIX[k % 4])
        objs.append(o)
    return t, objs


# --- lineside totes ------------------------------------------------------------------------------------
st_index = {s["id"]: i for i, s in enumerate(stations)}
bins = []
for sid, part, el, side, mx, mn in BINS:
    i = st_index[sid]
    loc = (STX[i] + side * TOTE_DX, FRONT + TOTE_DIMS.y * TOTE_SCALE[part] / 2 + 0.012, TH)   # material zone
    t, parts = make_tote(f"TOTE_{sid}_{part}", c_ga, loc, part, mx, TOTE_SCALE[part], seq=(part == "STACK"))
    bins.append({"sid": sid, "part": part, "el": el, "max": mx, "min": mn, "qty": mx, "parts": parts,
                 "stop": Vector((loc[0], FRONT - 0.28, 0)), "keys": [(0.0, mx)]})

# consumption events from the sim
heap = []
for b_i, b in enumerate(bins):
    for t, lab, serial, pn in feed["stations"][b["sid"]]:
        if lab == "ELEMENT_START" and pn == b["el"] and (not b["part"].startswith("PROP_")
                                                          or units.get(serial, {}).get("prop") == b["part"][5:]):
            heapq.heappush(heap, (t, 1, b_i))

# --- backstock table + LOG ---------------------------------------------------------------------------------
# --- backstock: mini warehouse on four benches (rack + forklift aisle + pick face by PN + sequencing) ----------
N_BS = 4
BS = Vector((0.15 + N_BS * TL / 2, -2.85, 0))
BS_SY = 1.6
for k_ in range(N_BS):
    b_ = inst(f"BACKSTOCK_{k_}", c_ga, "LIB_TABLE", (BS.x + (k_ - (N_BS - 1) / 2) * TL, BS.y, 0))
    b_.scale = (1.0, BS_SY, 1.0)
    box(f"BACKSTOCK_{k_}_Top", c_ga, (TL, TD * BS_SY, 0.012), (b_.location.x, BS.y, TH - 0.010), M_TOP)
BS_FRONT, BS_BACK = BS.y + TD * BS_SY / 2, BS.y - TD * BS_SY / 2
BS_X0, BS_X1 = BS.x - N_BS * TL / 2, BS.x + N_BS * TL / 2
label("BACKSTOCK_Label", c_ga, "BACKSTOCK / SEQUENCING", (BS.x, BS_BACK - 0.15, 0.004), 0.08, M["text"])
M_UPRIGHT = mat("M_RackUpright", (0.08, 0.25, 0.65, 1), metal=0.4, rough=0.5)
M_BEAM = mat("M_RackBeam", (0.95, 0.40, 0.05, 1), metal=0.3, rough=0.5)
M_PALLET = mat("M_Pallet", (0.62, 0.45, 0.25, 1), rough=0.9)
M_FORK = mat("M_Forklift", (0.69, 0.15, 0.005, 1), metal=0.2, rough=0.5)   # movers: #D96B10
# one bay per part number (high runners get two); key -> (label, tote part, colour, part mesh)
SKUS_BS = [("MOT", "PN-MOT-2207", "MOT", None, None), ("MOT", "PN-MOT-2207", "MOT", None, None),
           ("PROP_TRI", "PN-PROP-5-TRI", "PROP", None, "LIB_PART_PROP_TRI"),
           ("PROP_BI", "PN-PROP-5-BI", "PROP", None, "LIB_PART_PROP_BI"),
           ("CAM", "PN-CAM-FPV", "CAM", None, None), ("ANT", "PN-ANT-VTX", "ANT", None, None),
           ("BAT", "PN-BAT-6S", "BAT", None, None), ("BAT", "PN-BAT-6S", "BAT", None, None),
           ("STACK_BLK", "PN-ESC-FC-STACK-BLK", "STACK", "BLK", None), ("STACK_RED", "PN-ESC-FC-STACK-RED", "STACK", "RED", None),
           ("STACK_YEL", "PN-ESC-FC-STACK-YEL", "STACK", "YEL", None), ("STACK_SLV", "PN-ESC-FC-STACK-SLV", "STACK", "SLV", None)]
N_BAYS, N_LVL = len(SKUS_BS), 4

# pallet rack along the back: N_BAYS bays x N_LVL levels (level 0 on the bench = pick level)
RACK_X0, BAY_W, RACK_Y, RACK_D, LVL_H = BS_X0 + 0.25, 0.21, BS_BACK + 0.11, 0.16, 0.17
for b in range(N_BAYS + 1):
    for side in (-1, 1):
        box(f"RACK_Up_{b}_{side}", c_ga, (0.012, 0.012, N_LVL * LVL_H + 0.02), (RACK_X0 + b * BAY_W, RACK_Y + side * RACK_D / 2, TH), M_UPRIGHT)
for lv in range(1, N_LVL):
    for side in (-1, 1):
        box(f"RACK_Beam_{lv}_{side}", c_ga, (N_BAYS * BAY_W, 0.010, 0.014), (RACK_X0 + N_BAYS * BAY_W / 2, RACK_Y + side * RACK_D / 2, TH + lv * LVL_H - 0.014), M_BEAM)
rack_pal = {}
for b, (key, pn, part, col, lib_) in enumerate(SKUS_BS):
    for lv in range(N_LVL):
        x, z = RACK_X0 + (b + 0.5) * BAY_W, TH + lv * LVL_H
        pal = box(f"RACK_Pallet_{b}_{lv}", c_ga, (0.13, 0.11, 0.012), (x, RACK_Y, z), M_PALLET)
        t_, _ = make_tote(f"RACK_TOTE_{b}_{lv}", c_ga, (x, RACK_Y, z + 0.012), part, 6, 0.2 if part != "BAT" else 0.3,
                          colour=col, libs=[lib_] if lib_ else None)
        rack_pal[(b, lv)] = [pal, t_] + list(t_.children)
    label(f"RACK_PN_{b}", c_ga, pn, (RACK_X0 + (b + 0.5) * BAY_W, RACK_Y - RACK_D / 2 - 0.004, TH + N_LVL * LVL_H - 0.01), 0.010, M["text"], rot_x=math.pi / 2)

# pick face along the front, one lane per part number (labelled)
for k_, (key, pn, part, col, lib_) in enumerate(SKUS_BS):
    if k_ in (1, 7):                          # second bays of high runners share the lane
        continue
    x = RACK_X0 + (k_ + 0.5) * BAY_W
    make_tote(f"PICK_TOTE_{k_}", c_ga, (x, BS_FRONT - 0.07, TH), part, 6 if part != "PROP" else 12, 0.2 if part != "BAT" else 0.3,
              colour=col, libs=[lib_] if lib_ else None)
    label(f"PICK_PN_{k_}", c_ga, pn, (x, BS_FRONT - 0.004, TH + 0.045), 0.009, M["text"], rot_x=math.pi / 2)

# sequencing cell (after the rack end, totes on the rack line so the forklift can drop full ones)
seq_src, seq_parts = {}, {}
for k_, col in enumerate(("BLK", "RED", "YEL", "SLV")):
    x = RACK_X0 + N_BAYS * BAY_W + 0.16 + k_ * 0.15
    t_, objs = make_tote(f"SEQ_SRC_{col}", c_ga, (x, RACK_Y, TH), "STACK", 6, 0.2, colour=col)
    seq_src[col], seq_parts[col] = Vector((x, RACK_Y, TH)), objs
    label(f"SEQ_PN_{col}", c_ga, f"STACK-{col}", (x, RACK_Y + 0.05, TH + 0.002), 0.010, M["text"])
SEQ_X = sum(v.x for v in seq_src.values()) / 4
SEQ_OUT = Vector((SEQ_X, BS_FRONT - 0.09, TH))
make_tote("SEQ_OUT", c_ga, SEQ_OUT, "STACK", 8, 0.2)
label("SEQ_OUT_Label", c_ga, "SEQ > ST30", (SEQ_OUT.x, SEQ_OUT.y - 0.05, TH + 0.002), 0.011, M["text"])

LOG_HOME = Vector((BS_X0 + 1.0, BS_FRONT + 0.32, 0))    # in front of the pick face
log, gL, gR = make_actor("LOG", c_op, LOG_HOME, 0.0, BIG)          # faces -Y: towards the backstock table
BIG_TOTE = inst("LOG_BIG_TOTE", c_op, "LIB_TOTE", (0, -0.33, 0.47), scale=0.62 / BIG)   # milk-run tote
BIG_TOTE.parent = log
carried = []
for c_k in range(len(BINS)):                                            # small full bins inside the big tote
    cx = (c_k % 3 - 1) * TOTE_DIMS.x * 0.205        # 3 x 3 grid of small bins in the big tote
    cy = (c_k // 3 - 1) * TOTE_DIMS.y * 0.205
    ct = inst(f"LOG_CARRY_{c_k}", c_op, "LIB_TOTE", (0, 0, 0), scale=0.2 / 0.62)
    ct.parent = BIG_TOTE
    ct.location = (cx / 0.62, cy / 0.62, TOTE_DIMS.z * 0.35)
    carried.append(ct)

# event-driven replenishment: milk-run departures on a fixed clock
for k_ in range(int((W1 - RUN_T0) // RUN_S) + 1):
    heapq.heappush(heap, (RUN_T0 + k_ * RUN_S, 5, None))
log_free, pending, trips, stockouts = 0.0, [], [], 0
while heap:
    t, kind, data = heapq.heappop(heap)
    if kind == 1:                                     # consumption
        b = bins[data]
        if b["qty"] <= 0:
            stockouts += 1
        b["qty"] = max(0, b["qty"] - 1)
        b["keys"].append((t, b["qty"]))
        if b["qty"] <= b["min"] and data not in pending and not b.get("ordered"):
            pending.append(data)
            b["ordered"] = True
            b["sig_t"] = t
    elif kind == 2:                                   # tote swapped: back to max
        b = bins[data]
        b["qty"] = b["max"]
        b["keys"].append((t, b["qty"]))
        b["ordered"] = False
    elif kind == 3:                                   # LOG back at the backstock
        log_free = t
    if kind == 5 and pending and log_free <= t:
        route = sorted(pending, key=lambda i_: bins[i_]["stop"].x)        # fixed route order, swap empties only
        pending = []
        t0 = max(t, log_free)
        path, tt, pos = [(t0, LOG_HOME, "load")], t0 + LOAD_S, LOG_HOME
        for n_, i_ in enumerate(route):
            dest = bins[i_]["stop"]
            tt += (dest - pos).length / LOG_WALK
            path.append((tt, dest, f"drop{n_}"))
            heapq.heappush(heap, (tt + DROP_S * 0.6, 2, i_))
            tt += DROP_S
            path.append((tt, dest, "leave"))
            pos = dest
        tt += (LOG_HOME - pos).length / LOG_WALK
        path.append((tt, LOG_HOME, "home"))
        heapq.heappush(heap, (tt, 3, None))
        log_free = 1e18                               # busy until the kind-3 event
        trips.append((t0, len(route), path))
print(f"LOG trips {len(trips)}, stock-outs {stockouts}")

# --- keys: tote contents --------------------------------------------------------------------------------
prefs.keyframe_new_interpolation_type = "CONSTANT"
for b in bins:
    for o in b["parts"]:
        o.hide_viewport = o.hide_render = False
        o.keyframe_insert("hide_viewport", frame=1)
        o.keyframe_insert("hide_render", frame=1)
    prev = b["max"]
    for t, q in b["keys"]:
        if t > W1 or q == prev:
            prev = q
            continue
        for kk, o in enumerate(b["parts"]):
            if (kk < q) != (kk < prev):
                o.hide_viewport = o.hide_render = not (kk < q)
                o.keyframe_insert("hide_viewport", frame=max(1, fr(t)))
                o.keyframe_insert("hide_render", frame=max(1, fr(t)))
        prev = q

# --- keys: LOG walking, carrying, organising -------------------------------------------------------------
for o in carried + [BIG_TOTE]:
    o.hide_viewport = o.hide_render = True
    o.keyframe_insert("hide_viewport", frame=1)
    o.keyframe_insert("hide_render", frame=1)
prefs.keyframe_new_interpolation_type = "BEZIER"
log.location = LOG_HOME
key_loc(log, 1)
prefs.keyframe_new_interpolation_type = "CONSTANT"
log.rotation_euler.z = 0.0
log.keyframe_insert("rotation_euler", index=2, frame=1)
prefs.keyframe_new_interpolation_type = "BEZIER"
busy = []
for t0, n_tot, path in trips:
    if t0 > W1:
        break
    busy.append((t0, path[-1][0]))
    prefs.keyframe_new_interpolation_type = "CONSTANT"
    for c_k, o in enumerate(carried):
        on = c_k < n_tot
        o.hide_viewport = o.hide_render = not on
        o.keyframe_insert("hide_viewport", frame=max(1, fr(t0 + LOAD_S)))
        o.keyframe_insert("hide_render", frame=max(1, fr(t0 + LOAD_S)))
    for f_, on in ((max(1, fr(t0 + LOAD_S)), True), (max(1, fr(path[-1][0])), False)):
        BIG_TOTE.hide_viewport = BIG_TOTE.hide_render = not on
        BIG_TOTE.keyframe_insert("hide_viewport", frame=f_)
        BIG_TOTE.keyframe_insert("hide_render", frame=f_)
    prefs.keyframe_new_interpolation_type = "BEZIER"
    prev_pos, prev_t = LOG_HOME, t0
    for tt, pos, what in path:
        step_keys(log, prev_t, tt, (pos - prev_pos).length)
        log.location = pos
        key_loc(log, max(1, fr(tt)))
        heading = 0.0 if what in ("load", "home") else (math.pi if what.startswith("drop") or what == "leave" else 0.0)
        if what.startswith("drop"):
            n_ = int(what[4:])
            heading = math.pi                                   # face the tote on the line
            pose_arms(gL, gR, max(1, fr(tt + 2)), (-60, 0), (-60, 0))
            pose_arms(gL, gR, max(1, fr(tt + DROP_S - 2)), (-35, 0), (-35, 0))
            o = carried[n_tot - 1 - n_]
            o.hide_viewport = o.hide_render = True
            o.keyframe_insert("hide_viewport", frame=max(1, fr(tt + DROP_S * 0.6)))
            o.keyframe_insert("hide_render", frame=max(1, fr(tt + DROP_S * 0.6)))
        elif what == "load":
            pose_arms(gL, gR, max(1, fr(tt + 2)), (-60, 0), (-60, 0))
            pose_arms(gL, gR, max(1, fr(tt + LOAD_S)), (-35, 0), (-35, 0))
        prefs.keyframe_new_interpolation_type = "CONSTANT"
        if (pos - prev_pos).length > 1e-6:
            log.rotation_euler.z = math.pi / 2 if pos.x >= prev_pos.x else -math.pi / 2
            log.keyframe_insert("rotation_euler", index=2, frame=max(1, fr(prev_t + 0.5)))
        log.rotation_euler.z = heading
        log.keyframe_insert("rotation_euler", index=2, frame=max(1, fr(tt)))
        prefs.keyframe_new_interpolation_type = "BEZIER"
        prev_pos, prev_t = pos, tt
    pose_arms(gL, gR, max(1, fr(path[-1][0] + 1)))

# organising the backstock while idle: slow alternate reaches over the table
ORG_S = 24.0
t, k = W0 + 5, 0
bi = 0
while t < W1:
    while bi < len(busy) and busy[bi][1] < t:
        bi += 1
    if bi < len(busy) and busy[bi][0] <= t + ORG_S:
        t = busy[bi][1] + 3
        continue
    lp, rp = ((-55, -10), (-25, 0)) if k % 2 == 0 else ((-25, 0), (-55, 10))
    pose_arms(gL, gR, max(1, fr(t)), lp, rp)
    t += ORG_S / 2
    k += 1

# --- mini forklift: lowers a reserve pallet (level 2) to the pick level (level 0) every FL_CYCLE ----------------
FL_CYCLE, FL_V = 360.0, 0.05
FL_Y = RACK_Y + RACK_D / 2 + 0.24                  # parked in the aisle, forks towards the rack (-Y)
FL_HOME = Vector((RACK_X0 + 0.07, FL_Y, TH))
fl = bpy.data.objects.new("FORKLIFT", None)
fl.location = FL_HOME
c_ga.objects.link(fl)
fl_parts = [box("FL_Body", c_ga, (0.13, 0.20, 0.08), (0, 0.02, 0.02), M_FORK),
            box("FL_Counterweight", c_ga, (0.13, 0.05, 0.10), (0, 0.11, 0.02), M["dark"]),
            box("FL_Roof", c_ga, (0.13, 0.17, 0.008), (0, 0.04, 0.31), M["dark"]),
            box("FL_Seat", c_ga, (0.07, 0.06, 0.02), (0, 0.06, 0.10), M["dark"]),
            box("FL_SeatBack", c_ga, (0.07, 0.012, 0.06), (0, 0.092, 0.10), M["dark"]),
            box("FL_Column", c_ga, (0.012, 0.012, 0.07), (0, -0.035, 0.10), M["dark"])]
wheel_ = cyl("FL_Steer", c_ga, 0.02, 0.006, (0, -0.03, 0.17), M["dark"], 16)
wheel_.rotation_euler.x = 0.9
fl_parts.append(wheel_)
for sx in (-0.06, 0.06):
    for sy in (-0.03, 0.11):
        fl_parts.append(box(f"FL_Guard_{sx}_{sy}", c_ga, (0.008, 0.008, 0.21), (sx, sy, 0.10), M["dark"]))
    fl_parts.append(box(f"FL_Mast_{sx}", c_ga, (0.010, 0.012, N_LVL * LVL_H + 0.06), (sx * 0.8, -0.085, 0.01), M["dark"]))
    for sy in (-0.05, 0.08):
        w = cyl(f"FL_Wheel_{sx}_{sy}", c_ga, 0.022, 0.018, (0, 0, 0), M["dark"], 16)
        w.rotation_euler.y = math.pi / 2
        w.location = (sx + (0.009 if sx > 0 else -0.027), sy, 0.022)
        fl_parts.append(w)
for o in fl_parts:
    o.parent = fl
forks = bpy.data.objects.new("FL_Forks", None)
forks.parent, forks.location = fl, (0, -0.10, 0.012)
c_ga.objects.link(forks)
for sx in (-0.035, 0.035):
    f_ = box(f"FL_Tine_{sx}", c_ga, (0.014, 0.13, 0.006), (sx, -0.06, 0), M["dark"])
    f_.parent = forks
box("FL_Carriage", c_ga, (0.12, 0.01, 0.06), (0, 0.004, 0), M["dark"]).parent = forks
fork_pal = box("FL_Pallet", c_ga, (0.13, 0.11, 0.012), (0, -0.06, 0.006), M_PALLET)
fork_pal.parent = forks
fork_tote = inst("FL_Tote", c_ga, "LIB_TOTE", (0, -0.06, 0.018), scale=0.2)
fork_tote.parent = forks
# seated driver facing the forks: hips at seat height (rigged Dummy 13)
drvA, aL, aR = make_actor("OP_FORKLIFT", c_op, (0, 0.06, 0.12 - 0.47 * ROBOT_H), 0.0, ROBOT_H)
drvA.parent = fl
sit(drvA)                                          # seated: hips on the seat, knees bent forward
pose_arms(aL, aR, 1, (-60, 0), (-60, 0))           # hands on the steering wheel


def vis_k(objs, f, on):
    prefs.keyframe_new_interpolation_type = "CONSTANT"
    for o in objs:
        o.hide_viewport = o.hide_render = not on
        o.keyframe_insert("hide_viewport", frame=max(1, f))
        o.keyframe_insert("hide_render", frame=max(1, f))


# Forklift job queue. LOWER(b): reserve pallet (top level) -> pick level of bay b, every FL_CYCLE (part bays).
# SEQ(col): when a colour tote in the sequencing cell reaches its min, bring a pallet from that colour's bay to
# the cell (priority over LOWER). The sequencing consumption comes from the sim (one controller per unit).
SEQ_LEAD = 1500.0                                               # sequenced ~ 9 takts ahead of ST30
SEQ_MAX, SEQ_MIN = 6, 2
COLS = ("BLK", "RED", "YEL", "SLV")
st30 = [(t, serial) for t, lab, serial, pn in feed["stations"]["ST30"] if lab == "ELEMENT_START" and pn == "place_controller"]
seq_ev = sorted((t - SEQ_LEAD, serial) for t, serial in st30 if serial in units and W0 <= t - SEQ_LEAD <= W1)
part_bays = [b for b, sk in enumerate(SKUS_BS) if sk[2] != "STACK"]
colour_bay = {sk[3]: b for b, sk in enumerate(SKUS_BS) if sk[2] == "STACK"}


def job_keys(kind, b, t, col=None):
    """Forklift path for one job; returns (list of (t, pos, fork_z), pick time, drop time, end time)."""
    bx = RACK_X0 + (b + 0.5) * BAY_W
    lv_from = (N_LVL - 1) if kind == "LOWER" else 1
    dest_x = bx if kind == "LOWER" else seq_src[col].x
    z_up = lv_from * LVL_H
    d1 = abs(bx - FL_HOME.x) / FL_V
    d2 = abs(dest_x - bx) / FL_V
    d3 = abs(FL_HOME.x - dest_x) / FL_V
    k = [(t, FL_HOME, 0.012), (t + d1, Vector((bx, FL_Y, TH)), 0.012),
         (t + d1 + 6, Vector((bx, FL_Y, TH)), z_up + 0.004), (t + d1 + 10, Vector((bx, FL_Y - 0.09, TH)), z_up + 0.004),
         (t + d1 + 13, Vector((bx, FL_Y - 0.09, TH)), z_up + 0.03), (t + d1 + 17, Vector((bx, FL_Y, TH)), z_up + 0.03),
         (t + d1 + 25, Vector((bx, FL_Y, TH)), 0.03), (t + d1 + 25 + d2, Vector((dest_x, FL_Y, TH)), 0.03),
         (t + d1 + 29 + d2, Vector((dest_x, FL_Y - 0.09, TH)), 0.03), (t + d1 + 32 + d2, Vector((dest_x, FL_Y - 0.09, TH)), 0.012),
         (t + d1 + 36 + d2, Vector((dest_x, FL_Y, TH)), 0.012), (t + d1 + 36 + d2 + d3, FL_HOME, 0.012)]
    return k, t + d1 + 13, t + d1 + 32 + d2, k[-1][0]


heap = [(W0 + 200 + i * FL_CYCLE, 2, part_bays[i % len(part_bays)]) for i in range(int((W1 - W0 - 200) // FL_CYCLE) + 1)]
heap += [(ts, 1, serial) for ts, serial in seq_ev]
heapq.heapify(heap)
seq_qty = {c: SEQ_MAX for c in COLS}
seq_keys = {c: [(0.0, SEQ_MAX)] for c in COLS}
seq_ordered, queue, fl_free, jobs = set(), [], W0, []
while heap:
    t, kind, data = heapq.heappop(heap)
    if kind == 1:                                     # one controller sequenced
        c = units[data]["colour"]
        seq_qty[c] = max(0, seq_qty[c] - 1)
        seq_keys[c].append((t, seq_qty[c]))
        if seq_qty[c] <= SEQ_MIN and c not in seq_ordered:
            seq_ordered.add(c)
            queue.insert(0, ("SEQ", colour_bay[c], c))
    elif kind == 2:
        queue.append(("LOWER", data, None))
    elif kind == 3:                                   # pallet delivered to the sequencing cell
        seq_qty[data] = SEQ_MAX
        seq_keys[data].append((t, SEQ_MAX))
        seq_ordered.discard(data)
    elif kind == 4:
        fl_free = t
    if queue and fl_free <= t:
        jk, jb, jc = queue.pop(0)
        keys_, t_pick, t_drop, t_end = job_keys(jk, jb, t, jc)
        jobs.append((jk, jb, jc, keys_, t_pick, t_drop))
        if jk == "SEQ":
            heapq.heappush(heap, (t_drop, 3, jc))
        heapq.heappush(heap, (t_end, 4, None))
        fl_free = 1e18
print(f"forklift jobs: {sum(j[0] == 'LOWER' for j in jobs)} lower, {sum(j[0] == 'SEQ' for j in jobs)} to sequencing")

vis_k([fork_pal, fork_tote], 1, False)
for objs in rack_pal.values():
    vis_k(objs, 1, True)
prefs.keyframe_new_interpolation_type = "LINEAR"
fl.keyframe_insert("location", frame=1)
forks.keyframe_insert("location", index=2, frame=1)
for jk, b, col, keys_, t_pick, t_drop in jobs:
    if keys_[0][0] > W1:
        break
    prefs.keyframe_new_interpolation_type = "LINEAR"
    for tt, p, fz in keys_:
        fl.location = p
        fl.keyframe_insert("location", frame=max(1, fr(tt)))
        forks.location.z = fz
        forks.keyframe_insert("location", index=2, frame=max(1, fr(tt)))
    lv = (N_LVL - 1) if jk == "LOWER" else 1
    if jk == "LOWER":
        vis_k(rack_pal[(b, 0)], fr(keys_[0][0]), False)          # pick pallet emptied into the pick face
        vis_k(rack_pal[(b, 0)], fr(t_drop), True)                # replaced by the lowered pallet
    vis_k(rack_pal[(b, lv)], fr(t_pick), False)                  # pallet taken from the rack
    vis_k([fork_pal, fork_tote], fr(t_pick), True)
    vis_k([fork_pal, fork_tote], fr(t_drop), False)
    vis_k(rack_pal[(b, lv)], fr(t_pick + FL_CYCLE * 2), True)    # receiving refills the rack later

# sequencing-cell totes show their stock (full tote swapped in by the forklift)
prefs.keyframe_new_interpolation_type = "CONSTANT"
for c in COLS:
    parts_ = seq_parts[c]
    prev = SEQ_MAX
    for t, q in seq_keys[c]:
        if t > W1:
            break
        for kk, o in enumerate(parts_):
            if t == 0.0 or (kk < q) != (kk < prev):
                o.hide_viewport = o.hide_render = not (kk < q)
                o.keyframe_insert("hide_viewport", frame=max(1, fr(t)))
                o.keyframe_insert("hide_render", frame=max(1, fr(t)))
        prev = q

# --- sequencing operator: walks to the colour tote, picks the unit's controller, places it in the sequence tote ---
SEQ_HOME = Vector((sum(v.x for v in seq_src.values()) / 4, FL_Y + 0.14, TH))
seqB, sL, sR = make_actor("OP_SEQUENCER", c_op, SEQ_HOME, 0.0, ROBOT_H)
prefs.keyframe_new_interpolation_type = "LINEAR"
seqB.keyframe_insert("location", frame=1)
for ts, serial in seq_ev:
    src = seq_src[units[serial]["colour"]]
    for tt, p, rz, arm in ((ts, SEQ_HOME, 0.0, 0), (ts + 5, Vector((src.x, src.y + 0.13, TH)), 0.0, -55),
                           (ts + 8, Vector((src.x, src.y + 0.13, TH)), 0.0, -30),
                           (ts + 14, Vector((SEQ_OUT.x, SEQ_OUT.y - 0.12, TH)), math.pi, -55),
                           (ts + 17, Vector((SEQ_OUT.x, SEQ_OUT.y - 0.12, TH)), math.pi, 0), (ts + 22, SEQ_HOME, 0.0, 0)):
        seqB.location = p
        key_loc(seqB, max(1, fr(tt)))
        seqB.rotation_euler.z = rz
        seqB.keyframe_insert("rotation_euler", index=2, frame=max(1, fr(tt)))
        pose_arms(sL, sR, max(1, fr(tt)), (arm, 0), (arm, 0))

# --- ST30 tote is sequenced: slot k always shows the colour of the k-th next unit to reach ST30 ----------------
st30_order = [s_ for t_, s_ in sorted(st30)]
st30_t = [t_ for t_, s_ in sorted(st30)]
stack_bin = next(b for b in bins if b["part"] == "STACK")
prefs.keyframe_new_interpolation_type = "CONSTANT"
for t, q in [(0.0, stack_bin["max"])] + stack_bin["keys"]:
    if t > W1:
        break
    n = bisect.bisect_right(st30_t, t)
    for k_, o in enumerate(stack_bin["parts"]):
        if n + k_ >= len(st30_order) or st30_order[n + k_] not in units:
            continue
        m = o.material_slots[0].material
        rgba = COLOURS[units[st30_order[n + k_]]["colour"]]
        b_ = m.node_tree.nodes["Principled BSDF"]
        b_.inputs["Base Color"].default_value = rgba
        b_.inputs["Base Color"].keyframe_insert("default_value", frame=max(1, fr(t)))
        m.diffuse_color = rgba
        m.keyframe_insert("diffuse_color", frame=max(1, fr(t)))
prefs.keyframe_new_interpolation_type = "BEZIER"
