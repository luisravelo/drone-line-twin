"""Dummy 13 actors with articulated arms (exec'd by build_scene.py after the line is animated).

- Station operators (small, on the tabletop): each ELEMENT_START from the sim = one pick-from-bin / place-on-drone
  arm cycle; arms rest when the station is DONE or EMPTY.
- INSPECTOR (large, floor, ST50): works the final-inspection elements, then at every unit exit carries the finished
  drone to the ship cart and leaves a packed box there.
- REPLENISHER (large, floor): milk run every MILK_RUN_S sim seconds, stops at each assembly station with a tote.
Arms: LIB_DUMMY_ARM_L/R (pivot at the shoulder, custom prop "pivot"), body LIB_DUMMY_BODY. LIB_DUMMY faces -Y;
arm rotation X < 0 raises the arm forward, Y abducts (left arm outward = negative).
"""
BIG = 1.6                # large Dummy 13 height (m)
MILK_RUN_S = 1200.0
WALK = 0.15             # m per sim s: slowed so walking reads at 30x playback
DWELL = 40.0            # sim s at each station
D = math.radians
M_BIN = mat("M_Bin", (0.10, 0.35, 0.75, 1), rough=0.6)
# Lineside totes: (station, part, consuming element, side of the AMR, max, min). Each element start = 1 part.
BINS = [("ST00", "CAM", "install_camera", -1, 8, 4), ("ST10", "MOT", "place_motor", -1, 16, 8),
        ("ST20", "MOT", "place_motor", -1, 16, 8), ("ST30", "STACK", "place_controller", -1, 8, 4),
        ("ST30", "ANT", "install_antenna", 1, 16, 8), ("ST40", "PROP_TRI", "place_prop", -1.6, 24, 12), ("ST40", "PROP_BI", "place_prop", -0.45, 16, 8),
        ("ST40", "BAT", "place_battery", 1, 8, 4)]   # min covers one milk-run interval of consumption
TOTE_DX, OP_HOME_Y = 0.20, -0.27     # totes sit in the material zone at the front edge; operator between AMR and totes


def key_loc(o, f):
    keep = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "LINEAR"
    o.keyframe_insert("location", frame=f)
    prefs.keyframe_new_interpolation_type = keep


# rigged Dummy 13: make_actor / pose_arms / sit / step_keys
exec(open(os.path.join(ROOT, "blender", "dummy_rig.py"), encoding="utf-8").read())


def station_elements(sid):
    """[(t_start, t_end, element)] for ELEMENT_STARTs at a station, ended by the next start or DONE/EMPTY."""
    out, cur = [], None
    for t, lab, serial, pn in feed["stations"][sid]:
        if lab == "ELEMENT_START":
            if cur:
                out.append((cur[0], t, cur[1]))
            cur = (t, pn)
        elif lab in ("DONE", "EMPTY") and cur:
            out.append((cur[0], t, cur[1]))
            cur = None
    return out


def work_arms(L, R, sid, reach=80, pick=(25, 35), rest_after=4.0, body=None):
    """Arm keys driven by the station's element starts. Part elements: the operator steps to the tote, picks,
    steps back and places on the drone (walk + reach = the non-value-added share); other elements: in place."""
    els = [e for e in station_elements(sid) if e[1] > W0 - 30 and e[0] < W1]
    side_of = {el: side for st, part, el, side, mx, mn in BINS if st == sid}
    pose_arms(L, R, 1)
    home = body.location.copy() if body else None
    if body:
        key_loc(body, 1)
    for k, (a, b, el) in enumerate(els):
        d = max(b - a, 1.0)
        side = side_of.get(el)
        if body is not None and side is not None:
            tw = min(0.22 * d, 5.0)
            at_tote = Vector((home.x + side * TOTE_DX, FRONT + 0.20, home.z))     # walk to the material zone
            for tt, loc in ((a, home), (a + tw, at_tote), (a + tw + 2, at_tote), (a + 2 * tw + 2, home)):
                body.location = loc
                key_loc(body, max(1, fr(tt)))
                body.rotation_euler.z = 0.0 if loc is at_tote else math.pi      # face the tote, then the drone
                body.keyframe_insert("rotation_euler", index=2, frame=max(1, fr(tt)))
            pose_arms(L, R, max(1, fr(a + tw)), (-40, 0), (-40, 0))           # reach into the tote
            pose_arms(L, R, max(1, fr(a + tw + 2)), (-30, 0), (-30, 0))
            pose_arms(L, R, max(1, fr(a + 2 * tw + 2)), (-reach, 0), (-reach, 0))
            pose_arms(L, R, max(1, fr(a + 0.85 * d)), (-reach + 8, -5), (-reach + 8, 5))
            continue
        lp, rp = ((-pick[0], -pick[1]), (-reach + 20, 0)) if k % 2 == 0 else ((-reach + 20, 0), (-pick[0], pick[1]))
        pose_arms(L, R, max(1, fr(a)), lp, rp)
        pose_arms(L, R, max(1, fr(a + 0.35 * d)), (-reach, 0), (-reach, 0))
        pose_arms(L, R, max(1, fr(a + 0.75 * d)), (-reach + 8, -5), (-reach + 8, 5))
        nxt = els[k + 1][0] if k + 1 < len(els) else None
        if nxt is None or nxt - b > 2 * rest_after:
            pose_arms(L, R, max(1, fr(b + rest_after)))


# --- station operators: small Dummy 13 on the tabletop (ST50 is the large inspector) ----------------------
for o in [o for o in c_op.objects]:
    bpy.data.objects.remove(o)
prefs.keyframe_new_interpolation_type = "BEZIER"
for i, s in enumerate(stations[:-1]):
    body, L, R = make_actor(f"OP_{s['id']}", c_op, (STX[i], OP_HOME_Y, TH), math.pi, ROBOT_H)
    work_arms(L, R, s["id"], reach=62, body=body)

# --- INSPECTOR: final inspection at ST50 + packaging to the ship cart -------------------------------------
last = stations[-1]["id"]
P0 = Vector((STX[-1], FRONT - 0.25, 0))
CART = Vector((TL * N + 0.6, 0, 0))
P1 = Vector((CART.x, -0.62, 0))
RPR_TOP = (TL * N + 0.6, -1.5, TH)               # repair table (RPR01) top
PR = Vector((TL * N + 0.6 - 0.62, -1.5, 0))      # inspector stands beside the repair table
insp, iL, iR = make_actor("INSPECTOR", c_op, P0, math.pi, BIG)
work_arms(iL, iR, last, reach=55, pick=(20, 25))

carry_mat = mat("M_Drone_CARRY", COLOURS["BLK"], rough=0.35)
carry, carry_prop = {}, {}
for mdl in ("A", "B"):
    objs = [inst(f"CARRY_{mdl}_FRAME", c_op, f"LIB_MODEL_{mdl}", (0, -0.36, 0.52))]
    objs += [inst(f"CARRY_{mdl}_{cat}", c_op, f"LIB_{mdl}_{cat}", (0, -0.36, 0.52)) for cat in PART_CATS if not cat.startswith("PROP")]
    for pt in ("TRI", "BI"):
        po = inst(f"CARRY_{mdl}_PROP_{pt}", c_op, f"LIB_{mdl}_PROP_{pt}", (0, -0.36, 0.52))
        po.parent, po.scale, po.rotation_euler.z = insp, (1 / BIG,) * 3, math.pi / 2
        carry_prop[(mdl, pt)] = po
    for o in objs:
        o.parent = insp
        o.scale = (1 / BIG,) * 3
        o.rotation_euler.z = math.pi / 2
    paint(objs[0], carry_mat)
    paint(objs[1 + PART_CATS.index("STACK")], carry_mat)
    carry[mdl] = objs

BOX_SLOTS = [(CART.x + (i - 0.5) * 0.33, (j - 0.5) * 0.24, 0.75 + L * 0.08) for L in range(4) for j in range(2) for i in range(2)]
M_BOX = mat("M_Cardboard", (0.55, 0.40, 0.22, 1), rough=0.9)


def vis(objs, f, on):
    for o in objs:
        o.hide_viewport = o.hide_render = not on
        o.keyframe_insert("hide_viewport", frame=f)
        o.keyframe_insert("hide_render", frame=f)


prefs.keyframe_new_interpolation_type = "CONSTANT"
for objs in carry.values():
    vis(objs, 1, False)
vis(carry_prop.values(), 1, False)
shipped = sorted((u["ship"], s_) for s_, u in units.items() if "ship" in u and W0 < u["ship"] <= W1)
walk_keys = []
for k, (t, serial) in enumerate(shipped):
    u = units[serial]
    mdl, col = u["model"][-1], u["colour"]
    slot = BOX_SLOTS[k % len(BOX_SLOTS)]
    bx = box(f"SHIP_BOX_{k:02d}", c_ga, (0.31, 0.22, 0.075), slot, M_BOX)
    lb = box(f"SHIP_LABEL_{k:02d}", c_ga, (0.10, 0.06, 0.004), (slot[0], slot[1], slot[2] + 0.075),
             mat(f"M_Paint_{col}", COLOURS[col], rough=0.35))
    repaired = "repair" in u
    t_box = t if repaired else t + 12
    vis([bx, lb], 1, False)
    vis([bx, lb], fr(t_box), True)
    if k + len(BOX_SLOTS) < len(shipped):
        vis([bx, lb], fr(shipped[k + len(BOX_SLOTS)][0]), False)
    t_c = u["repair"] if repaired else t        # rejects leave ST50 for the repair table
    if repaired and not (W0 < t_c <= W1):
        continue
    vis(carry[mdl] + [carry_prop[(mdl, u.get("prop", "TRI"))]], fr(t_c - idx_s), True)
    vis(carry[mdl] + [carry_prop[(mdl, u.get("prop", "TRI"))]], fr(t_c + 12), False)
    b = carry_mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = COLOURS[col]
    b.inputs["Base Color"].keyframe_insert("default_value", frame=fr(t_c - idx_s))
    carry_mat.diffuse_color = COLOURS[col]
    carry_mat.keyframe_insert("diffuse_color", frame=fr(t_c - idx_s))
    walk_keys.append((t_c, PR if repaired else P1))
    if repaired:                                 # the reject waits on the repair table until it ships
        rep_objs = [inst(f"RPR_{k:02d}_FRAME", c_ga, f"LIB_MODEL_{mdl}", RPR_TOP)]
        rep_objs += [inst(f"RPR_{k:02d}_{cat}", c_ga, f"LIB_{mdl}_{cat}", RPR_TOP) for cat in PART_CATS
                     if not cat.startswith("PROP") or cat == "PROP_" + u.get("prop", "TRI")]
        pm_ = mat(f"M_Paint_{col}", COLOURS[col], rough=0.35)
        paint(rep_objs[0], pm_)
        paint(rep_objs[1 + PART_CATS.index("STACK")], pm_)
        vis(rep_objs, 1, False)
        vis(rep_objs, fr(t_c + 12), True)
        vis(rep_objs, fr(t), False)

prefs.keyframe_new_interpolation_type = "LINEAR"
insp.location = P0
insp.keyframe_insert("location", frame=1)
walk_keys.sort(key=lambda r: r[0])
for t, dest in walk_keys:                 # grab at index start, walk to cart (or repair table), place, walk back
    for tt, p, arm in ((t - idx_s, P0, -55), (t + 6, dest, -50), (t + 12, dest, -65), (t + 24, P0, 0)):
        insp.location = p
        insp.keyframe_insert("location", frame=fr(tt))
        pose_arms(iL, iR, fr(tt), (arm, 0), (arm, 0))
    step_keys(insp, t - idx_s, t + 6, (dest - P0).length)
    step_keys(insp, t + 12, t + 24, (dest - P0).length)

# --- lineside logistics: totes, min/max inventory, LOG replenishment from the backstock
exec(open(os.path.join(ROOT, "blender", "logistics.py"), encoding="utf-8").read())
exec(open(os.path.join(ROOT, "blender", "zones.py"), encoding="utf-8").read())
