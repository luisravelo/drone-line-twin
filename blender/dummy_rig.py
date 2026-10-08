"""Dummy 13 rig: rigid segments on an armature with 2-bone IK on arms and legs (exec'd by build_scene.py).

Dummy 13 is a jointed figure (55 rigid parts), so each part follows one bone: no mesh deformation, cheap to play.
LIB_DUMMY (1.0 m, faces -Y, feet at z=0) is cut once into LIB_DUMMY_SEG_<bone> meshes in its own frame.
make_actor() returns (armature, hand_target_L, hand_target_R): moving the armature moves the body, moving the
hand targets drives shoulder + elbow through IK. Feet have IK targets too (stepping, sitting).
"""
import bmesh

# joint positions in the LIB_DUMMY frame (from the island analysis of the 55 parts)
J = {"pelvis": (0.004, 0.015, 0.50), "waist": (0.004, 0.016, 0.58), "chest": (0.005, 0.016, 0.68),
     "neck": (0.007, 0.015, 0.82), "head": (0.008, 0.015, 0.89), "crown": (0.008, 0.015, 1.0)}
SIDE = {"L": 1.0, "R": -1.0}                      # LIB_DUMMY faces -Y, so its left is +X
for s, k in SIDE.items():
    J[f"shoulder.{s}"] = (k * 0.103, 0.016, 0.765)
    J[f"elbow.{s}"] = (k * 0.123, 0.024, 0.62)
    J[f"wrist.{s}"] = (k * 0.140, 0.012, 0.49)
    J[f"fist.{s}"] = (k * 0.145, 0.007, 0.42)
    J[f"hip.{s}"] = (k * 0.063, 0.017, 0.47)
    J[f"knee.{s}"] = (k * 0.063, 0.015, 0.28)
    J[f"ankle.{s}"] = (k * 0.063, 0.016, 0.045)
    J[f"toe.{s}"] = (k * 0.063, -0.075, 0.015)
BONES = [("pelvis", "pelvis", "waist", None), ("spine", "waist", "chest", "pelvis"), ("chest", "chest", "neck", "spine"),
         ("neck", "neck", "head", "chest"), ("head", "head", "crown", "neck")]
for s in SIDE:
    BONES += [(f"upperarm.{s}", f"shoulder.{s}", f"elbow.{s}", "chest"), (f"forearm.{s}", f"elbow.{s}", f"wrist.{s}", f"upperarm.{s}"),
              (f"hand.{s}", f"wrist.{s}", f"fist.{s}", f"forearm.{s}"), (f"thigh.{s}", f"hip.{s}", f"knee.{s}", "pelvis"),
              (f"shin.{s}", f"knee.{s}", f"ankle.{s}", f"thigh.{s}"), (f"foot.{s}", f"ankle.{s}", f"toe.{s}", f"shin.{s}")]


def seg_of(c):
    """Bone that owns an island, from its centre (LIB frame)."""
    x, z, ax = c[0], c[2], abs(c[0])
    s = "L" if x > 0 else "R"
    if z < 0.06 and ax > 0.02:
        return f"foot.{s}"
    if z < 0.30 and ax < 0.10:
        return f"shin.{s}"
    if z < 0.505 and 0.03 < ax < 0.10:
        return f"thigh.{s}"
    if ax > 0.13 and z < 0.48:
        return f"hand.{s}"
    if ax > 0.11 and z < 0.63:
        return f"forearm.{s}"
    if ax > 0.09 and z < 0.80:
        return f"upperarm.{s}"
    if z < 0.56:
        return "pelvis"
    if z < 0.67:
        return "spine"
    if z < 0.81:
        return "chest"
    if z < 0.88:
        return "neck"
    return "head"


def build_segments():
    if "LIB_DUMMY_SEG_pelvis" in bpy.data.objects:
        return
    src = bpy.data.objects["LIB_DUMMY"].data
    nv = len(src.vertices)
    co = np.empty(nv * 3)
    src.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ne = len(src.edges)
    ed = np.empty(ne * 2, dtype=np.int64)
    src.edges.foreach_get("vertices", ed)
    ed = ed.reshape(-1, 2)
    lab = np.arange(nv)
    a, b = ed[:, 0], ed[:, 1]
    while True:                                   # connected components (label propagation)
        m = np.minimum(lab[a], lab[b])
        old = lab.copy()
        np.minimum.at(lab, a, m)
        np.minimum.at(lab, b, m)
        lab = lab[lab]
        if np.array_equal(lab, old):
            break
    _, inv = np.unique(lab, return_inverse=True)
    cnt = np.bincount(inv)
    cen = np.stack([(np.bincount(inv, weights=co[:, k]) / cnt) for k in range(3)], 1)
    owner = np.array([seg_of(c) for c in cen])[inv]
    for bone, *_ in BONES:
        bm = bmesh.new()
        bm.from_mesh(src)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if owner[v.index] != bone], context="VERTS")
        me = bpy.data.meshes.new(f"LIB_DUMMY_SEG_{bone}_MESH")
        bm.to_mesh(me)
        bm.free()
        for mt in src.materials:
            me.materials.append(mt)
        ob = bpy.data.objects.new(f"LIB_DUMMY_SEG_{bone}", me)
        bpy.data.collections["LIB_ASSETS"].objects.link(ob)


def make_actor(name, coll, loc, rot_z, scale):
    """Rigged Dummy 13. Returns (armature, hand_target_L, hand_target_R); feet targets as arm['foot_L'/'foot_R']."""
    build_segments()
    arm_data = bpy.data.armatures.new(name + "_RIG")
    arm = bpy.data.objects.new(name, arm_data)
    arm.location, arm.rotation_euler.z, arm.scale = loc, rot_z, (scale,) * 3
    arm.show_in_front = False
    arm_data.display_type = "STICK"
    coll.objects.link(arm)
    view = bpy.context.view_layer
    prev_active = view.objects.active
    view.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for bone, h, t, parent in BONES:
        e = eb.new(bone)
        e.head, e.tail = J[h], J[t]
        e.roll = 0.0
        if parent:
            e.parent = eb[parent]
            e.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    view.objects.active = prev_active
    for bone, *_ in BONES:                          # rigid parts follow their bone
        seg = bpy.data.objects.new(f"{name}_{bone}", bpy.data.objects[f"LIB_DUMMY_SEG_{bone}"].data)
        coll.objects.link(seg)
        seg.parent, seg.parent_type, seg.parent_bone = arm, "BONE", bone
        b = arm_data.bones[bone]
        seg.matrix_parent_inverse = (b.matrix_local @ Matrix.Translation((0, b.length, 0))).inverted()
    targets = {}
    for s, k in SIDE.items():
        for kind, rest, chain_bone, pole in (("hand", J[f"wrist.{s}"], f"forearm.{s}", (k * 0.25, 0.30, 0.62)),
                                             ("foot", J[f"ankle.{s}"], f"shin.{s}", (k * 0.063, -0.40, 0.30))):
            tg = bpy.data.objects.new(f"{name}_IK_{kind}.{s}", None)
            tg.empty_display_size = 0.03
            tg.parent, tg.location = arm, rest
            coll.objects.link(tg)
            pl = bpy.data.objects.new(f"{name}_POLE_{kind}.{s}", None)
            pl.empty_display_size = 0.02
            pl.parent, pl.location = arm, pole
            coll.objects.link(pl)
            c = arm.pose.bones[chain_bone].constraints.new("IK")
            c.target, c.pole_target, c.chain_count = tg, pl, 2
            c.pole_angle = math.radians(90 if kind == "hand" else -90)   # elbows back, knees forward (measured)
            targets[f"{kind}_{s}"] = tg
    arm["rest_hand_L"], arm["rest_hand_R"] = list(J["wrist.L"]), list(J["wrist.R"])
    return arm, targets["hand_L"], targets["hand_R"]


SHOULDER = {"L": Vector(J["shoulder.L"]), "R": Vector(J["shoulder.R"])}
ARM_REACH = 0.26                                    # shoulder -> wrist when the elbow is slightly bent


def hand_pos(side, x_deg, y_deg):
    """Old shoulder-angle API -> wrist target: X<0 raises the arm forward (-Y), Y abducts."""
    v = Matrix.Rotation(math.radians(x_deg), 3, "X") @ Matrix.Rotation(math.radians(y_deg), 3, "Y") @ Vector((0, 0, -ARM_REACH))
    return SHOULDER[side] + v


def pose_arms(L, R, f, l=(0, 0), r=(0, 0)):
    for tg, side, (x, y) in ((L, "L", l), (R, "R", r)):
        tg.location = hand_pos(side, x, y) if (x, y) != (0, 0) else Vector(J[f"wrist.{side}"])
        tg.keyframe_insert("location", frame=f)


def feet(arm):
    n = arm.name
    return bpy.data.objects[f"{n}_IK_foot.L"], bpy.data.objects[f"{n}_IK_foot.R"]


def sit(arm):
    """Seated pose: thighs horizontal, shins vertical (ankle under the knee). Place the armature so the hips
    (J['hip.L'] z) land on the seat; the knee pole in front makes the knees bend forward."""
    fL, fR = feet(arm)
    thigh = J["hip.L"][2] - J["knee.L"][2]
    for f_, s in ((fL, "L"), (fR, "R")):
        f_.location = (SIDE[s] * 0.07, J["hip.L"][1] - thigh, J["hip.L"][2] - (J["knee.L"][2] - J["ankle.L"][2]))


def step_keys(arm, t0, t1, dist, stride=0.16):
    """Alternate foot lifts while the armature translates between t0 and t1 (sim seconds)."""
    if dist <= 1e-3 or t1 <= t0:
        return
    fL, fR = feet(arm)
    n_steps = max(2, int(dist / (stride * arm.scale[0])))
    keep = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "BEZIER"
    for k in range(n_steps + 1):
        t = t0 + (t1 - t0) * k / n_steps
        for f_, s, phase in ((fL, "L", 0), (fR, "R", 1)):
            up = (k % 2 == phase) and 0 < k < n_steps
            f_.location = (SIDE[s] * 0.063, J["ankle.L"][1], J["ankle.L"][2] + (0.05 if up else 0.0))
            f_.keyframe_insert("location", frame=max(1, fr(t)))
    prefs.keyframe_new_interpolation_type = keep
