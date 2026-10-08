"""Upstream WIP (print -> KUKA2 -> conveyor through paint -> buffer) and the live process-block bar (exec'd by build_scene.py).

WIP frames come from a pool per model; each unit is assigned the first pool object free over its upstream life
(print start -> KUKA pick). Print: the frame grows in Z on top of a printer. Paint: it sits on a jig in front of
the booth and blends from white to its colour. PBS: it waits in a free shelf slot, then moves to the pick spot.
"""
POOL = 16
BELT_V = PITCH / 16.0              # buffer conveyor speed (m per sim s) = sim buffer_index_s
white = (0.92, 0.92, 0.90, 1)
BOOTH_IN, BOOTH_OUT = paint_x - PAINT_W / 2, paint_x + PAINT_W / 2
life = []                          # every timestamp comes from the sim event log (pull mode)
for serial, u in units.items():
    if all(k in u for k in ("print", "transfer", "belt_in", "paint", "pbs_in", "pick")) and u["pick"] >= W0 and u["print"] <= W1:
        life.append((serial, u["model"][-1], u.get("printer", 0), u["print"], u["transfer"], u["belt_in"],
                     u["paint"], u["pbs_in"], u["pick"]))
life.sort(key=lambda r: r[3])


def belt(x):
    return Vector((x, BELT_Y, BELT_TOP))


# accumulating buffer conveyor: constant belt speed, frames stop behind the one ahead; head = KUKA1 pick spot
tracks, state, queue = {}, {}, []


def x_at(u, t):
    t0, x0, x1, t1 = state[u]
    return x1 if t >= t1 or t1 <= t0 else x0 + (x1 - x0) * (t - t0) / (t1 - t0)


evs = sorted([(r[7], 0, r[0]) for r in life] + [(r[8], 1, r[0]) for r in life])
for t, kind, u in evs:
    if kind == 0:
        queue.append(u)
        state[u] = (t, BOOTH_OUT, BOOTH_OUT, t)
        tracks[u] = [(t, BOOTH_OUT)]
    elif u in queue:
        queue.remove(u)
    for idx, q in enumerate(queue):
        tgt = HEAD_X - min(idx, N_BUF - 1) * PITCH
        if abs(state[q][2] - tgt) > 1e-6:
            xc = x_at(q, t)
            while tracks[q] and tracks[q][-1][0] > t:
                tracks[q].pop()
            tracks[q].append((t, xc))
            ta = t + abs(tgt - xc) / BELT_V
            tracks[q].append((ta, tgt))
            state[q] = (t, xc, tgt, ta)

prefs.keyframe_new_interpolation_type = "LINEAR"
pool = {}
for mdl in ("A", "B"):
    for k in range(POOL):
        o = inst(f"WIP_{mdl}_{k:02d}", c_up, f"LIB_MODEL_{mdl}", PRINTER_TOP[0])
        m = mat(f"M_WIP_{mdl}_{k:02d}", white, rough=0.4)
        paint(o, m)
        pool[(mdl, k)] = {"obj": o, "mat": m, "free": -1e12}


def key_col(m, f, rgba):
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Base Color"].keyframe_insert("default_value", frame=f)
    m.diffuse_color = rgba
    m.keyframe_insert("diffuse_color", frame=f)


def key_vis(objs, f, on):
    prefs.keyframe_new_interpolation_type = "CONSTANT"
    for o in objs:
        o.hide_viewport = o.hide_render = not on
        o.keyframe_insert("hide_viewport", frame=max(1, f))
        o.keyframe_insert("hide_render", frame=max(1, f))
    prefs.keyframe_new_interpolation_type = "LINEAR"


for p in pool.values():
    key_vis([p["obj"]], 1, False)

# KUKA2 payload (raw white print), rigid to its flange, frozen at the printer-0 pick pose
k2_rest6 = Matrix(k2_joints[5]["rest"])
k2_root_m = Matrix.Translation(K2_LOC) @ Matrix.Scale(K2_SCALE, 4)
k2_T6 = Matrix(kuka_fk(K2_POSES["p0"])[-1].tolist())
k2_pay = {}
for mdl in ("A", "B"):
    o = inst(f"KUKA2_PAYLOAD_{mdl}", c_up, f"LIB_MODEL_{mdl}", (0, 0, 0))
    paint(o, mat("M_Paint_WHITE", white, rough=0.4))
    o.parent = k2_joints[5]
    o.matrix_parent_inverse = k2_rest6.inverted()
    o.matrix_basis = k2_T6.inverted() @ k2_root_m.inverted() @ Matrix.Translation(PRINTER_TOP[0])
    k2_pay[mdl] = o
key_vis(k2_pay.values(), 1, False)
for j in k2_joints:
    j.animation_data_clear()
prefs.keyframe_new_interpolation_type = "BEZIER"
pose_kuka(k2_joints, K2_POSES["home"], 1)
prefs.keyframe_new_interpolation_type = "LINEAR"

k2_last = -1e12
for serial, mdl, pr, tp, tx, tbi, tpa, tb, tk in life:
    slot = next((p for (m_, k), p in sorted(pool.items(), key=lambda kv: kv[0][1]) if m_ == mdl and p["free"] <= tp), None)
    if slot is None:
        continue
    slot["free"] = tk + 1
    o, m = slot["obj"], slot["mat"]
    pr = min(pr, len(PRINTER_TOP) - 1)
    col = COLOURS[units[serial]["colour"]]
    key_vis([o], fr(tp), True)          # printing
    key_vis([o], fr(tx), False)         # in KUKA2's gripper
    key_vis([o], fr(tbi), True)         # on the paint conveyor
    key_vis([o], fr(tk), False)         # taken by KUKA1
    keys = [(tp, PRINTER_TOP[pr], 0.05), (tx - 1, PRINTER_TOP[pr], 1.0), (tbi, ENTRY, 1.0),
            (tpa, belt(BOOTH_IN), 1.0)] + [(t, belt(x), 1.0) for t, x in tracks.get(serial, [])]
    last = None
    for t, loc, sz in keys:
        if t > tk:
            break
        o.location, o.scale = loc, (1, 1, sz)
        o.keyframe_insert("location", frame=max(1, fr(t)))
        o.keyframe_insert("scale", index=2, frame=max(1, fr(t)))
        last = (loc, sz)
    if last:                                   # hold at the buffer head until KUKA1 picks it (no drift to the next life)
        o.location, o.scale = last[0], (1, 1, last[1])
        o.keyframe_insert("location", frame=max(1, fr(tk)))
        o.keyframe_insert("scale", index=2, frame=max(1, fr(tk)))
    prefs.keyframe_new_interpolation_type = "CONSTANT"
    key_col(m, max(1, fr(tp)), white)
    key_col(m, max(1, fr((tpa + tb) / 2)), col)        # colour changes inside the booth
    prefs.keyframe_new_interpolation_type = "LINEAR"
    # KUKA2: printer -> conveyor entry, driven by the sim TRANSFER (grab) and BELT_IN (release) events
    key_vis([k2_pay[mdl]], fr(tx), True)
    key_vis([k2_pay[mdl]], fr(tbi), False)
    prefs.keyframe_new_interpolation_type = "BEZIER"
    for t, nm in ((tx - 12, "home"), (tx - 5, f"p{pr}_up"), (tx, f"p{pr}"), (tx + 4, f"p{pr}_up"),
                  (tbi - 4, "entry_up"), (tbi, "entry"), (tbi + 4, "entry_up"), (tbi + 12, "home")):
        if t > k2_last:
            pose_kuka(k2_joints, K2_POSES[nm], max(1, fr(t)))
    k2_last = tbi + 12
    prefs.keyframe_new_interpolation_type = "LINEAR"

from bpy_extras import anim_utils
for p_ in pool.values():
    ad = p_["obj"].animation_data
    if ad and ad.action:
        for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
            if fc.data_path in ("location", "scale"):
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"

# --- live process-block bar (camera space, bottom of the frame) ------------------------------------------
cam = bpy.data.objects.get("CAM_Main")
if cam:
    names = ["PRINT", "PAINT", "PBS"] + [s["id"] for s in stations] + ["SHIP"]
    w, gap, y0 = 0.135, 0.018, -0.43
    x_start = -(len(names) * (w + gap) - gap) / 2
    panel_m = mat("M_HUD_Panel", (0.03, 0.03, 0.035, 1), emit=1.0)
    upm = mat("M_Block_Upstream", (0.35, 0.55, 0.85, 1), emit=0.4)
    shipm = mat("M_Block_Ship", (0.70, 0.70, 0.72, 1), emit=1.0)
    ui_txt = mat("M_UI_Text", (0.02, 0.02, 0.025, 1))
    for k, nm in enumerate(names):
        x = x_start + k * (w + gap) + w / 2
        me = bpy.data.meshes.new(f"UI_BLOCK_{nm}")
        me.from_pydata([(-w / 2, -0.035, 0), (w / 2, -0.035, 0), (w / 2, 0.035, 0), (-w / 2, 0.035, 0)], [], [(0, 1, 2, 3)])
        me.materials.append(andon_mats[nm] if nm in andon_mats else (upm if k < 3 else shipm))
        blk = bpy.data.objects.new(f"UI_BLOCK_{nm}", me)
        blk.parent, blk.location = cam, (x, y0, -1.001)
        root.objects.link(blk)
        for sub, dy, size in (("NAME", 0.012, 0.018), ("VAL", -0.022, 0.016)):
            t = label(f"UI_{sub}_{nm}", root, {"PBS": "BUFFER"}.get(nm, nm) if sub == "NAME" else "", (x, y0 + dy, -1.0), size, ui_txt)
            t.parent = cam
    if "HUD_Stop" in bpy.data.objects:
        bpy.data.objects["HUD_Stop"].location.y = -0.33
    # data for the handler: upstream counts and the unit at each station over time
    st_unit = {s["id"]: [] for s in stations}
    for s in stations:
        for t, lab, serial, pn in feed["stations"][s["id"]]:
            if lab in ("WORKING", "EMPTY"):
                st_unit[s["id"]].append([t, units[serial]["sku"] if serial in units else ""])
    up = {"print": sorted([u["print"], u.get("transfer", u.get("paint"))] for u in units.values() if "print" in u and "paint" in u),
          "paint": sorted([u["paint"], u["pbs_in"]] for u in units.values() if "paint" in u and "pbs_in" in u),
          "pbs": feed["pbs_count"], "st_unit": st_unit, "blocks": names}
    tb = bpy.data.texts.get("ui_data.json") or bpy.data.texts.new("ui_data.json")
    tb.from_string(json.dumps(up))
    code = """import bpy, bisect, json
_UI = {}
def _ui(scene, *_):
    if "d" not in _UI:
        _UI["d"] = json.loads(bpy.data.texts["ui_data.json"].as_string())
        _UI["h"] = json.loads(bpy.data.texts["hud_data.json"].as_string())
    d, h = _UI["d"], _UI["h"]
    t = h["W0"] + (scene.frame_current - 1) / h["FPS"] * h["SPEED"]
    ob = bpy.data.objects
    def busy(iv):
        return sum(1 for a, b in iv if a <= t < b)
    pbs = d["pbs"]
    i = bisect.bisect_right([r[0] for r in pbs], t) - 1
    vals = {"PRINT": "%d printing" % busy(d["print"]), "PAINT": "%d painting" % busy(d["paint"]),
            "PBS": "%d stored" % (pbs[i][1] if i >= 0 else 0),
            "SHIP": "%d shipped" % bisect.bisect_right(h["ships"], t)}
    for sid, ch in d["st_unit"].items():
        j = bisect.bisect_right([r[0] for r in ch], t) - 1
        vals[sid] = ch[j][1] if j >= 0 else ""
    for nm in d["blocks"]:
        o = ob.get("UI_VAL_" + nm)
        if o and o.data.body != vals.get(nm, ""):
            o.data.body = vals.get(nm, "")
for f in [f for f in bpy.app.handlers.frame_change_post if getattr(f, "__name__", "") == "_ui"]:
    bpy.app.handlers.frame_change_post.remove(f)
bpy.app.handlers.frame_change_post.append(_ui)
"""
    hb = bpy.data.texts.get("ui_handler.py") or bpy.data.texts.new("ui_handler.py")
    hb.from_string(code)
    hb.use_module = True
    exec(compile(code, "ui_handler.py", "exec"), {"__name__": "ui_handler"})
