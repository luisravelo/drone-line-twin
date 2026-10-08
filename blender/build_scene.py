"""Build the mini drone line (layout A) in Blender and animate it from the DES state feed.

Run inside Blender (MCP or Text Editor):  exec(open(r"<repo>/blender/build_scene.py").read())
Needs LIB_TABLE, LIB_AMR, LIB_DUMMY in collection LIB_ASSETS (imported once, Z-up, metres, origin bottom-centre).
Rebuilds collection LINE from scratch each run. Z-up, metres. X = flow direction, wall at +Y.
"""
import json
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

# repo root = parent of the folder holding the .blend (blender/drone_line_twin.blend); override with DRONETWIN_ROOT
ROOT = os.environ.get("DRONETWIN_ROOT") or os.path.dirname(os.path.dirname(bpy.path.abspath(bpy.data.filepath)))
SCENARIO = "growth_6pos"
SPEED = 30.0            # sim seconds per video second (whole shift ~17 min of playback)
FPS = 24
WINDOW_S = 3600.0       # sim seconds shown
AMR_SCALE = 0.3         # miniature AMR on the tabletop (0.27 x 0.20 m)
GAP = 0.35         # service aisle between the line and the wall: AMR return track + KUKA loader
LANE_FWD = -0.06   # forward lane on the tables, near the operator
ROBOT_H = 0.28     # Dummy 13 on the tabletop: big enough to reach the totes and the drone
N_PRINTERS = 2     # growth scenario upstream
COLOURS = {"BLK": (0.02, 0.02, 0.022, 1), "RED": (0.55, 0.015, 0.02, 1),
           "YEL": (0.9, 0.72, 0.0, 1), "SLV": (0.62, 0.63, 0.66, 1)}
ANDON = {"WORKING": (0.0, 1.0, 0.15, 1), "DONE": (1.0, 0.55, 0.0, 1), "STOPPED": (1.0, 0.0, 0.0, 1),
         "EMPTY": (0.05, 0.05, 0.05, 1)}

feed = json.load(open(os.path.join(ROOT, "out", f"state_feed_{SCENARIO}.json")))
meta = feed["meta"]
stations = meta["stations"]
lib = bpy.data.collections["LIB_ASSETS"]


def mesh_dims(name):            # from vertices: object.dimensions goes stale while LIB_ASSETS is excluded
    vs = [v.co for v in bpy.data.objects[name].data.vertices]
    return Vector([max(v[k] for v in vs) - min(v[k] for v in vs) for k in range(3)])


TL, TD, TH = mesh_dims("LIB_TABLE")
LANE_RET = TD / 2 + GAP / 2   # return track in the aisle behind the tables
TABLE_SY = 1.55               # deeper tables: AMR lane | operator zone | material zone (like a car GA line)
FRONT = TD / 2 - TD * TABLE_SY   # front edge of the bench (back edge stays at TD / 2)
AMR_H = mesh_dims("LIB_AMR").z * AMR_SCALE
N = len(stations)
STX = [i * TL + TL / 2 for i in range(N)]


# --- helpers -----------------------------------------------------------------------------------
def coll(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def mat(name, rgba, metal=0.0, rough=0.5, emit=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = rgba
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = rgba
        b.inputs["Emission Strength"].default_value = emit
    return m


def box(name, c, size, loc, m, rot_z=0.0):
    me = bpy.data.meshes.new(name)
    sx, sy, sz = (s / 2 for s in size)
    v = [(-sx, -sy, 0), (sx, -sy, 0), (sx, sy, 0), (-sx, sy, 0),
         (-sx, -sy, 2 * sz), (sx, -sy, 2 * sz), (sx, sy, 2 * sz), (-sx, sy, 2 * sz)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(v, [], f)
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler.z = rot_z
    c.objects.link(o)
    return o


def cyl(name, c, r, h, loc, m, seg=24):
    me = bpy.data.meshes.new(name)
    v = [(r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg), z) for z in (0, h) for k in range(seg)]
    f = [tuple(range(seg))[::-1], tuple(range(seg, 2 * seg))]
    f += [(k, (k + 1) % seg, seg + (k + 1) % seg, seg + k) for k in range(seg)]
    me.from_pydata(v, [], f)
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    o.location = loc
    c.objects.link(o)
    return o


def inst(name, c, lib_name, loc, rot_z=0.0, scale=1.0):
    o = bpy.data.objects.new(name, bpy.data.objects[lib_name].data)
    o.location, o.rotation_euler.z, o.scale = loc, rot_z, (scale,) * 3
    c.objects.link(o)
    return o


def label(name, c, text, loc, size=0.07, m=None, rot_x=0.0):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body, cu.size, cu.align_x = text, size, "CENTER"
    o = bpy.data.objects.new(name, cu)
    o.location, o.rotation_euler.x = loc, rot_x
    if m:
        cu.materials.append(m)
    c.objects.link(o)
    return o


def drone_lib(model):
    """Import cad/mesh/MODEL_x.obj once as LIB_MODEL_x (cm -> m, Z-up, origin bottom-centre, 1 material slot)."""
    name = f"LIB_{model}"
    if name in bpy.data.objects:
        return bpy.data.objects[name]
    import bmesh
    from mathutils import Matrix
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=os.path.join(ROOT, "cad", "mesh", f"{model}.obj"), up_axis="Z", forward_axis="Y")
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    bm = bmesh.new()
    for o in new:
        if o.type == "MESH":
            me = o.data.copy()
            me.transform(Matrix.Scale(0.01, 4) @ o.matrix_world)
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
    zmin = min(v.co.z for v in bm.verts)
    for v in bm.verts:
        v.co.z -= zmin
    me = bpy.data.meshes.new(name + "_MESH")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.material_index = 0
    me.materials.append(mat("M_Paint_WHITE", (0.92, 0.92, 0.9, 1), rough=0.4))
    ob = bpy.data.objects.new(name, me)
    lib.objects.link(ob)
    for o in new:
        bpy.data.objects.remove(o)
    return ob


def paint(o, m):
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = m


# --- reset -------------------------------------------------------------------------------------
old = bpy.data.collections.get("LINE")
if old:
    for o in list(old.all_objects):
        bpy.data.objects.remove(o)
    for c in list(old.children_recursive):
        bpy.data.collections.remove(c)
    bpy.data.collections.remove(old)
root = coll("LINE", bpy.context.scene.collection)
c_shop, c_up, c_ga, c_sk, c_op, c_an = (coll(n, root) for n in ("Shop", "Upstream", "GA", "Skillets", "Operators", "Andon"))
bpy.context.view_layer.layer_collection.children["LIB_ASSETS"].exclude = True

M_TOP = None
M = {
    "floor": mat("M_Floor", (0.42, 0.42, 0.41, 1), rough=0.8),
    "wall": mat("M_Wall", (0.78, 0.78, 0.76, 1), rough=0.9),
    "steel": mat("M_Steel", (0.55, 0.56, 0.58, 1), metal=0.9, rough=0.35),
    "alu": mat("M_Alu", (0.75, 0.76, 0.78, 1), metal=1.0, rough=0.3),
    "dark": mat("M_Dark", (0.06, 0.06, 0.07, 1), rough=0.5),
    "white": mat("M_White", (0.9, 0.9, 0.88, 1), rough=0.4),
    "yellow": mat("M_Lane", (0.95, 0.75, 0.05, 1), rough=0.6),
    "glass": mat("M_Glass", (0.6, 0.75, 0.85, 1), rough=0.05),
    "amr": mat("M_AMR", (0.12, 0.13, 0.15, 1), metal=0.3, rough=0.4),
    "text": mat("M_Text", (0.05, 0.05, 0.05, 1)),
    "robot": mat("M_Robot", (0.92, 0.92, 0.9, 1), rough=0.35),
    "joint": mat("M_RobotJoint", (0.18, 0.18, 0.2, 1), rough=0.5),
}
bpy.data.objects["LIB_TABLE"].data.materials[0] = M["steel"]
M_TOP = mat("M_PolishedConcrete", (0.50, 0.50, 0.48, 1), rough=0.12)   # smooth bench tops
amr_me = bpy.data.objects["LIB_AMR"].data
amr_me.materials[0] = M["amr"]
dm = bpy.data.objects["LIB_DUMMY"].data
dm.materials[0], dm.materials[1] = M["joint"], M["robot"]

# --- shop --------------------------------------------------------------------------------------
x0, x1 = -6.6, TL * N + 2.2
box("Floor", c_shop, (x1 - x0, 7.0, 0.01), ((x0 + x1) / 2, -2.6, -0.01), M["floor"])
WALL_Y = TD / 2 + GAP                          # wall face
box("Wall_Back", c_shop, (x1 - x0, 0.12, 2.6), ((x0 + x1) / 2, WALL_Y + 0.06, 0), M["wall"])
box("Wall_Left", c_shop, (0.12, 7.0, 2.6), (x0 - 0.06, -2.6 + 0.07, 0), M["wall"])
# floor zones and route markings: zones.py (plant colour system)

# --- upstream: printers -> KUKA2 -> conveyor through the paint booth -> buffer (N_BUF frames) -> KUKA1 ----
PBS_W, PBS_D, PAINT_W, PAINT_D = 0.9, 0.5, 1.1, 0.75
BELT_TOP, BELT_W, PITCH, N_BUF = 0.87, 0.30, 0.32, 10
pbs_x, pbs_y = -PBS_W / 2, TD / 2 - PBS_D / 2
HEAD_X, BELT_Y = pbs_x + PBS_W / 2 - 0.2, pbs_y          # buffer head = KUKA1 pick spot
BUF_START = HEAD_X - (N_BUF - 1) * PITCH - PITCH / 2
paint_x, paint_y = BUF_START - PAINT_W / 2, TD / 2 - PAINT_D / 2
ENTRY_X = paint_x - PAINT_W / 2 - 0.30                  # KUKA2 drops raw prints here
BELT_X0, BELT_X1 = ENTRY_X - 0.20, HEAD_X + 0.17
M_BELT = mat("M_Belt", (0.05, 0.05, 0.055, 1), rough=0.8)
box("BELT", c_up, (BELT_X1 - BELT_X0, BELT_W, 0.03), ((BELT_X0 + BELT_X1) / 2, BELT_Y, BELT_TOP - 0.03), M_BELT)
for side in (-1, 1):
    box(f"BELT_Rail_{side}", c_up, (BELT_X1 - BELT_X0, 0.02, 0.05), ((BELT_X0 + BELT_X1) / 2, BELT_Y + side * (BELT_W / 2 + 0.01), BELT_TOP - 0.04), M["steel"])
n_legs = int((BELT_X1 - BELT_X0) / 0.9) + 1
for k in range(n_legs + 1):
    lx = BELT_X0 + 0.05 + k * (BELT_X1 - BELT_X0 - 0.1) / n_legs
    for side in (-1, 1):
        box(f"BELT_Leg_{k}_{side}", c_up, (0.04, 0.04, BELT_TOP - 0.04), (lx, BELT_Y + side * (BELT_W / 2 + 0.01), 0), M["steel"])
box("PAINT01", c_up, (PAINT_W, PAINT_D, 1.9), (paint_x, paint_y, 0), M["white"])
box("PAINT01_Window", c_up, (0.5, 0.01, 0.4), (paint_x, paint_y - PAINT_D / 2 - 0.005, 1.25), M["glass"])
for side in (-1, 1):                                    # tunnel openings where the belt goes through
    box(f"PAINT01_Tunnel_{side}", c_up, (0.012, BELT_W + 0.08, 0.16), (paint_x + side * (PAINT_W / 2 + 0.006), BELT_Y, BELT_TOP - 0.05), M["dark"])
label("PAINT01_Label", c_up, "PAINT", (paint_x, paint_y - PAINT_D / 2 - 0.12, 0.003), 0.09, M["text"])
label("BUFFER_Label", c_up, f"BUFFER ({N_BUF})", ((BUF_START + HEAD_X) / 2, BELT_Y - BELT_W / 2 - 0.25, 0.003), 0.09, M["text"])
K2_SCALE, K2_LOC = 0.6, Vector((ENTRY_X - 0.55, LANE_RET, TH))
PRINTER_TOP = []
if "LIB_PRINTER" in bpy.data.objects:
    PR = mesh_dims("LIB_PRINTER")
    stand_h = 0.55
    for k in range(N_PRINTERS):
        px = K2_LOC.x - 0.05 - k * (PR.x + 0.10)
        py = TD / 2 - max(PR.y, 0.6) / 2
        box(f"PRINTER{k + 1:02d}_Stand", c_up, (PR.x + 0.05, max(PR.y, 0.6), stand_h), (px, py, 0), M["dark"])
        inst(f"PRINTER{k + 1:02d}", c_up, "LIB_PRINTER", (px, py, stand_h))
        PRINTER_TOP.append(Vector((px, py, stand_h + PR.z + 0.002)))
    label("PRINTER_Label", c_up, "3D PRINT", (K2_LOC.x - 0.35, -0.55, 0.003), 0.09, M["text"])
ENTRY = Vector((ENTRY_X, BELT_Y, BELT_TOP))

# --- GA: butted T-slot tables, andon, operators -------------------------------------------------
andon_mats = {}
for i, s in enumerate(stations):
    tb_ = inst(s["id"], c_ga, "LIB_TABLE", (STX[i], TD / 2 - TD * TABLE_SY / 2, 0))
    tb_.scale = (1.0, TABLE_SY, 1.0)
    box(f"{s['id']}_Top", c_ga, (TL, TD * TABLE_SY, 0.012), (STX[i], TD / 2 - TD * TABLE_SY / 2, TH - 0.010), M_TOP)   # polished concrete
    label(f"{s['id']}_Label", c_ga, f"{s['id']}  {s['name'].replace('_', ' ')}", (STX[i], FRONT - 0.15, 0.003), 0.06, M["text"])
    ax, ay = STX[i] + TL / 2 - 0.08, TD / 2 - 0.03    # back edge of the table
    cyl(f"{s['id']}_AndonPole", c_an, 0.012, 0.22, (ax, ay, TH), M["steel"])
    am = mat(f"M_Andon_{s['id']}", ANDON["EMPTY"], emit=6.0)
    andon_mats[s["id"]] = am
    cyl(f"{s['id']}_AndonLight", c_an, 0.03, 0.08, (ax, ay, TH + 0.22), am)
box("SHIP01_Cart", c_ga, (0.7, 0.5, 0.75), (TL * N + 0.6, 0, 0), M["steel"])
label("SHIP01_Label", c_ga, "SHIP", (TL * N + 0.6, -0.4, 0.003), 0.09, M["text"])
rpr = inst("RPR01", c_ga, "LIB_TABLE", (TL * N + 0.6, -1.5, 0), rot_z=math.pi / 2)
box("RPR01_Top", c_ga, (TD, TL, 0.012), (TL * N + 0.6, -1.5, TH - 0.010), M_TOP)
label("RPR01_Label", c_ga, "REPAIR", (TL * N + 0.6, -2.15, 0.003), 0.09, M["text"])

# return track in the aisle: steel plate at table height on legs
RT_X0 = STX[0] - 0.2
box("RETURN_Track", c_ga, (TL * N - RT_X0, GAP - 0.06, 0.02), ((RT_X0 + TL * N) / 2, LANE_RET, TH - 0.02), M["steel"])
for k in range(N + 1):
    box(f"RETURN_Leg_{k}", c_ga, (0.04, 0.04, TH - 0.02), (min(RT_X0 + 0.05 + k * TL, TL * N - 0.05), LANE_RET, 0), M["steel"])

# AMR transfers (roller bridges) at the first and last station, like line-to-line transfers in car assembly
M_ROLL = mat("M_Roller", (0.62, 0.63, 0.66, 1), metal=0.8, rough=0.3)
for i in (0, N - 1):
    y0_, y1_ = LANE_FWD + 0.05, LANE_RET + 0.12
    box(f"TRANSFER_{stations[i]['id']}_Frame", c_ga, (0.27, y1_ - y0_, 0.006), (STX[i], (y0_ + y1_) / 2, TH), M["dark"])
    for side in (-1, 1):
        box(f"TRANSFER_{stations[i]['id']}_Rail_{side}", c_ga, (0.012, y1_ - y0_, 0.02), (STX[i] + side * 0.14, (y0_ + y1_) / 2, TH), M["steel"])
    for k in range(int((y1_ - y0_) / 0.04)):
        r = cyl(f"TRANSFER_{stations[i]['id']}_Roll_{k}", c_ga, 0.006, 0.26, (0, 0, 0), M_ROLL, 12)
        r.rotation_euler.y = math.pi / 2
        r.location = (STX[i] - 0.13, y0_ + 0.02 + k * 0.04, TH + 0.012)

# --- KUKA loader in the aisle, on a pedestal below table height (shoulder near the work), limits off
exec(open(os.path.join(ROOT, "blender", "kuka_rig.py"), encoding="utf-8").read())
K_SCALE, K_LOC = 0.45, Vector((STX[0] - 0.3, LANE_RET, TH - 0.15))
box("KUKA_Pedestal", c_ga, (0.24, 0.24, K_LOC.z), (K_LOC.x, K_LOC.y, 0), M["dark"])
k_root, k_joints = build_kuka(c_ga, K_LOC, K_SCALE)
FRAME_H = 0.035
RAISE = 0.025   # standoffs on the fixture: the battery hangs under the bottom plate
PICK = Vector((pbs_x + PBS_W / 2 - 0.2, pbs_y, 0.85 + 0.02 + FRAME_H + 0.005))
PLACE = Vector((STX[0], LANE_FWD, TH + mesh_dims("LIB_AMR").z * AMR_SCALE + 0.012 + RAISE + FRAME_H + 0.005))
UP = Vector((0, 0, 0.12))
K_POSES = {}
SEEDS = {"pick": (132, 100, -79, 126, -30, 90), "place": (54, 99, -74, 125, -25, 90)}   # A6 +90: fingers across the frame   # from an offline multi-start search
for nm, tgt, seed in [("pick_up", PICK + UP, "pick"), ("pick", PICK, "pick"), ("place_up", PLACE + UP, "place"),
                      ("place", PLACE, "place"), ("home", (PICK + PLACE) / 2 + Vector((0, 0.1, 0.2)), None)]:
    st = np.array(SEEDS[seed], float) if seed else (K_POSES["pick_up"] + K_POSES["place_up"]) / 2
    best = kuka_ik(np.array((tgt - K_LOC) / K_SCALE), st, limits=False)
    K_POSES[nm] = best[0]
    print(f"KUKA {nm}: err {best[1] * K_SCALE * 1000:.1f} mm")

# --- KUKA2 (printer -> conveyor entry), same rig, seeds from an offline search with a consistent wrist
k2_root, k2_joints = build_kuka(c_up, K2_LOC, K2_SCALE, prefix="KUKA2")
K2_SEEDS = {"p0": (94, 69, -22, 127, -4, 90), "p1": (142, 110, -80, 127, -20, 90), "entry": (32, 112, -54, 126, 8, 90)}
K2_POSES = {}
for nm, tgt, seed in [(f"p{k}_up", PRINTER_TOP[k] + Vector((0, 0, FRAME_H + 0.005)) + UP, f"p{k}") for k in range(len(PRINTER_TOP))] + \
                     [(f"p{k}", PRINTER_TOP[k] + Vector((0, 0, FRAME_H + 0.005)), f"p{k}") for k in range(len(PRINTER_TOP))] + \
                     [("entry_up", ENTRY + Vector((0, 0, FRAME_H + 0.005)) + UP, "entry"), ("entry", ENTRY + Vector((0, 0, FRAME_H + 0.005)), "entry")]:
    d, e = kuka_ik(np.array((tgt - K2_LOC) / K2_SCALE), np.array(K2_SEEDS[seed], float), limits=False)
    K2_POSES[nm] = d
    print(f"KUKA2 {nm}: err {e * K2_SCALE * 1000:.1f} mm")
K2_POSES["home"] = (K2_POSES["p0_up"] + K2_POSES["entry_up"]) / 2


def align_yaw(poses, ref, names):
    """Turn A6 so the payload (rigid to the flange, frozen at the `ref` pose) has zero yaw at each pose."""
    T_ref = kuka_fk(poses[ref])[-1]
    for nm in names:
        best = None
        for trial in range(3):
            d = poses[nm].copy()
            R_ = (kuka_fk(d)[-1] @ np.linalg.inv(T_ref))[:3, :3]
            yaw = math.degrees(math.atan2(R_[1, 0], R_[0, 0]))
            if best is None or abs(yaw) < abs(best[1]):
                best = (d, yaw)
            for sgn in (1, -1):
                d2 = d.copy()
                d2[5] += sgn * yaw
                R2 = (kuka_fk(d2)[-1] @ np.linalg.inv(T_ref))[:3, :3]
                y2 = math.degrees(math.atan2(R2[1, 0], R2[0, 0]))
                if abs(y2) < abs(best[1]):
                    best = (d2, y2)
            poses[nm] = best[0]
        print(f"yaw {nm}: {best[1]:.2f} deg")


align_yaw(K_POSES, "pick", ["pick_up", "place_up", "place", "home"])
align_yaw(K2_POSES, "p0", ["p0_up", "p1", "p1_up", "entry_up", "entry", "home"])

# --- skillets: mini AMR + fixture + drone (A and B variants, one shown at a time) -----------------
lib_a, lib_b = drone_lib("MODEL_A"), drone_lib("MODEL_B")
sk_objs, sk_parts = {}, {}
M_CLAMP = mat("M_Clamp", (0.85, 0.08, 0.06, 1), rough=0.5)
PART_CATS = ["CAM", "MOT12", "MOT34", "STACK", "ANT", "PROP_TRI", "PROP_BI", "BAT"]   # PROP_* from lib_props.py
STEP_PARTS = {("ST00", "install_camera"): "CAM", ("ST10", "place_motor"): "MOT12", ("ST20", "place_motor"): "MOT34",
              ("ST30", "place_controller"): "STACK", ("ST30", "install_antenna"): "ANT", ("ST40", "place_prop"): "PROP",
              ("ST40", "place_battery"): "BAT"}
PART_COL = {"CAM": (0.04, 0.04, 0.05, 1), "MOT12": (0.72, 0.73, 0.76, 1), "MOT34": (0.72, 0.73, 0.76, 1),
            "ANT": (0.75, 0.08, 0.06, 1), "BAT": (0.10, 0.16, 0.30, 1)}
for mdl in ("A", "B"):
    for cat, col in PART_COL.items():
        me = bpy.data.objects[f"LIB_{mdl}_{cat}"].data
        if cat.startswith("MOT") and len(me.materials) == 2:
            continue                      # detailed motor proxy (lib_motors.py) keeps silver + dark slots
        me.materials.clear()
        me.materials.append(mat(f"M_Part_{cat[:3]}", col, metal=0.8 if cat.startswith("MOT") else 0.0, rough=0.4))
    me = bpy.data.objects[f"LIB_{mdl}_STACK"].data
    if not me.materials:
        me.materials.append(mat("M_Paint_WHITE", (0.92, 0.92, 0.9, 1), rough=0.4))
for sid in meta["skillets"]:
    e = bpy.data.objects.new(sid, None)
    e.empty_display_size = 0.1
    c_sk.objects.link(e)
    a = inst(f"{sid}_AMR", c_sk, "LIB_AMR", (0, 0, 0), rot_z=math.pi / 2, scale=AMR_SCALE)
    p = box(f"{sid}_Fixture", c_sk, (0.26, 0.19, 0.012), (0, 0, AMR_H), M["alu"])
    dmat = mat(f"M_Drone_{sid}", COLOURS["BLK"], rough=0.35)
    dz = AMR_H + 0.012 + RAISE
    da = inst(f"{sid}_MODEL_A", c_sk, lib_a.name, (0, 0, dz))
    db = inst(f"{sid}_MODEL_B", c_sk, lib_b.name, (0, 0, dz))
    paint(da, dmat)
    paint(db, dmat)
    kids = [a, p, da, db]
    for sx in (-0.05, 0.05):
        for sy in (-0.05, 0.05):
            kids.append(cyl(f"{sid}_Standoff_{sx}_{sy}", c_sk, 0.006, RAISE, (sx, sy, AMR_H + 0.012), M["dark"]))
    parts = {}
    for mdl in ("A", "B"):
        for cat in PART_CATS:
            o = inst(f"{sid}_{mdl}_{cat}", c_sk, f"LIB_{mdl}_{cat}", (0, 0, dz))
            if cat == "STACK":
                paint(o, dmat)          # controller stack colour always matches the frame
            parts[(mdl, cat)] = o
            kids.append(o)
    for side in (-1, 1):
        kids.append(box(f"{sid}_ClampPost_{side}", c_sk, (0.014, 0.014, RAISE + 0.034), (0, side * 0.075, AMR_H + 0.012), M["dark"]))
        kids.append(box(f"{sid}_ClampArm_{side}", c_sk, (0.016, 0.045, 0.006), (0, side * 0.055, dz + 0.034), M["dark"]))
        kids.append(box(f"{sid}_ClampHandle_{side}", c_sk, (0.010, 0.010, 0.03), (0, side * 0.085, dz + 0.034), M_CLAMP))
        for px in (-0.03, 0.03):
            kids.append(cyl(f"{sid}_Pin_{side}_{px}", c_sk, 0.0035, RAISE + 0.012, (px, side * 0.03, AMR_H + 0.012), M["steel"], 12))
    for child in kids:
        child.parent = e
    sk_objs[sid] = (e, da, db, dmat)
    sk_parts[sid] = parts

# --- animation from the state feed ----------------------------------------------------------------
sc = bpy.context.scene
sc.render.fps = FPS
idx_s = meta["index_s"]
stops = feed["line_stops"]
longest = max(stops, key=lambda r: r[1] - r[0]) if stops else [0, 0, ""]
W0 = 0.0                                        # start with the sim clock (shift start)
W1 = meta["window_s"][1]


def fr(t):
    return 1 + (t - W0) / SPEED * FPS


sc.frame_start, sc.frame_end = 1, int(fr(W1))
units = feed["units"]
K1_PLACE_S = 18.0                                   # fixed KUKA1 cycle: grab -> placed on the fixture
release, load_win = {}, []                          # ST00: KUKA places the frame during the load element
_ls = {}
for t, lab, serial, pn in feed["stations"][stations[0]["id"]]:
    if lab == "ELEMENT_START" and pn == "load_frame":
        _ls[serial] = t
    elif lab == "ELEMENT_START" and serial in _ls and serial not in release:
        ls = _ls[serial]
        g = units.get(serial, {}).get("pick", ls)      # sim PICK: AMR is at ST00 and the frame at the buffer head
        release[serial] = g + K1_PLACE_S
        load_win.append((ls, t, serial, g))


def sk_pos(x, y, serial, queue_slot):
    if y is not None and abs(y) < 1e-6:          # on the line: station by sim x
        i = int(round(x / (stations[1]["x"] - stations[0]["x"]))) if N > 1 else 0
        return Vector((STX[i], LANE_FWD, TH))
    return Vector((STX[0] + queue_slot * 0.32, LANE_RET, TH))


free_at = {}
for ks in feed["skillets"].values():
    for t, x, y, _ in ks:
        if y is not None and abs(y) > 1e-6:
            free_at.setdefault(t, []).append(x)
for t in free_at:
    free_at[t].sort(reverse=True)          # sim: highest x = next to load -> slot 0 next to ST00

prefs = bpy.context.preferences.edit
prefs.keyframe_new_interpolation_type = "LINEAR"
for sid, keys in feed["skillets"].items():
    e, da, db, dmat = sk_objs[sid]
    e.animation_data_clear()
    prev = None
    prev_t = None
    for t, x, y, serial in keys:
        if t > W1:
            break
        # queue slot = rank among free skillets moved at the same instant, by sim x (descending = next to load)
        slot = free_at[t].index(x) if (y is not None and abs(y) > 1e-6) else 0
        pos = sk_pos(x, y, serial, slot)
        if prev is None or t < W0:
            prev, prev_t = pos, t
            continue
        if (pos - prev).length > 1e-6:
            e.location = prev
            e.keyframe_insert("location", frame=fr(t - idx_s))
            if abs(prev.y - pos.y) > 1e-6:       # lane change at the end of the line or at load
                mid = Vector((prev.x, pos.y, TH)) if pos.y > prev.y else Vector((pos.x, prev.y, TH))
                e.location = mid
                e.keyframe_insert("location", frame=fr(t - idx_s / 2))
            e.location = pos
            e.keyframe_insert("location", frame=fr(t))
        prev, prev_t = pos, t
    if e.animation_data is None:
        e.location = prev if prev is not None else Vector((STX[0], LANE_RET, TH))
        e.keyframe_insert("location", frame=1)

prefs.keyframe_new_interpolation_type = "CONSTANT"
for sid, keys in feed["skillets"].items():
    e, da, db, dmat = sk_objs[sid]
    for o in (da, db):
        o.animation_data_clear()
    dmat.node_tree.animation_data_clear()
    dmat.animation_data_clear()
    def show(f, model, colour):
        for o, m in ((da, "A"), (db, "B")):
            o.hide_viewport = o.hide_render = model != m
            o.keyframe_insert("hide_viewport", frame=f)
            o.keyframe_insert("hide_render", frame=f)
        if colour:
            b = dmat.node_tree.nodes["Principled BSDF"]
            b.inputs["Base Color"].default_value = COLOURS[colour]
            b.inputs["Metallic"].default_value = 0.6 if colour == "SLV" else 0.0
            b.inputs["Base Color"].keyframe_insert("default_value", frame=f)
            b.inputs["Metallic"].keyframe_insert("default_value", frame=f)
            dmat.diffuse_color = COLOURS[colour]
            dmat.keyframe_insert("diffuse_color", frame=f)

    state, keyed = (None, None), False
    for t, x, y, serial in keys:
        on_line = y is not None and abs(y) < 1e-6
        u = units.get(serial) if on_line else None
        new = (u["model"], u["colour"]) if u else (None, None)
        f = fr(t) if on_line else fr(t - idx_s)
        if on_line and serial in release and abs(x) < 1e-6:
            f = fr(release[serial])                        # appears when the KUKA lets go
        if t > W1:
            break
        if t < W0:
            state = new
            continue
        if not keyed:
            show(1, *state)
            keyed = True
        if new != state:
            show(max(1, f), *new)
            state = new
    if not keyed:
        show(1, *state)

# --- parts appear when the station starts that element (data-driven), cleared when the unit leaves the line
appear = {}
for sid_st in [s["id"] for s in stations]:
    for t, lab, serial, pn in feed["stations"][sid_st]:
        cat = STEP_PARTS.get((sid_st, pn)) if lab == "ELEMENT_START" else None
        if cat == "PROP":
            cat = "PROP_" + units.get(serial, {}).get("prop", "TRI")
        if cat and (serial, cat) not in appear:
            appear[(serial, cat)] = t
for sid, keys in feed["skillets"].items():
    parts = sk_parts[sid]
    for o in parts.values():
        o.animation_data_clear()
    spans, cur, t_in = [], None, None                 # (serial, t_on_line, t_off_line)
    for t, x, y, serial in keys:
        on_line = y is not None and abs(y) < 1e-6
        if on_line and serial != cur:
            if cur is not None:
                spans.append((cur, t_in, t - idx_s))
            cur, t_in = serial, t
        elif not on_line and cur is not None:
            spans.append((cur, t_in, t - idx_s))
            cur = None
    if cur is not None:
        spans.append((cur, t_in, 1e12))
    vis = {k: [] for k in parts}                      # per object: list of (t_on, t_off)
    for serial, a, b in spans:
        mdl = units[serial]["model"][-1]
        for cat in PART_CATS:
            ta = appear.get((serial, cat))
            if ta is not None and ta < b:
                vis[(mdl, cat)].append((ta, b))
    for k, o in parts.items():
        on0 = any(a <= W0 < b for a, b in vis[k])
        o.hide_viewport = o.hide_render = not on0
        o.keyframe_insert("hide_viewport", frame=1)
        o.keyframe_insert("hide_render", frame=1)
        for a, b in vis[k]:
            for t, v in ((a, True), (b, False)):
                if W0 < t <= W1:
                    o.hide_viewport = o.hide_render = not v
                    o.keyframe_insert("hide_viewport", frame=fr(t))
                    o.keyframe_insert("hide_render", frame=fr(t))

for sid_st, am in andon_mats.items():
    b = am.node_tree.nodes["Principled BSDF"]
    am.node_tree.animation_data_clear()
    am.animation_data_clear()
    cur = "EMPTY"
    for t, lab, serial, pn in feed["stations"][sid_st]:
        new = {"WORKING": "WORKING", "DONE": "DONE", "EMPTY": "EMPTY", "LINE_STOP": "STOPPED"}.get(lab)
        if new is None or t > W1:
            continue
        if t < W0:
            cur = new
            continue
        b.inputs["Emission Color"].default_value = ANDON[new]
        b.inputs["Base Color"].default_value = ANDON[new]
        b.inputs["Emission Color"].keyframe_insert("default_value", frame=fr(t))
        b.inputs["Base Color"].keyframe_insert("default_value", frame=fr(t))
        am.diffuse_color = ANDON[new]
        am.keyframe_insert("diffuse_color", frame=fr(t))
    b.inputs["Emission Color"].default_value = ANDON[cur]
    b.inputs["Base Color"].default_value = ANDON[cur]
    b.inputs["Emission Color"].keyframe_insert("default_value", frame=1)
    b.inputs["Base Color"].keyframe_insert("default_value", frame=1)
    am.diffuse_color = ANDON[cur]
    am.keyframe_insert("diffuse_color", frame=1)
prefs.keyframe_new_interpolation_type = "BEZIER"

sc["window_s"] = [W0, W1]
sc["speed"] = SPEED
print(f"window {W0:.0f}-{W1:.0f} s, frames {sc.frame_end}, longest stop {longest}")

# --- KUKA keyframes: one fixed motion per load (pre-pick during the cycle, place when the AMR is at ST00)
for j in k_joints:
    j.animation_data_clear()
prefs.keyframe_new_interpolation_type = "BEZIER"
pose_kuka(k_joints, K_POSES["home"], 1)
pm = mat("M_Drone_KUKA", COLOURS["BLK"], rough=0.35)
root_m = Matrix.Translation(K_LOC) @ Matrix.Scale(K_SCALE, 4)
T6 = Matrix(kuka_fk(K_POSES["pick"])[-1].tolist())
j6 = k_joints[5]
rest6 = Matrix(j6["rest"])
payload = {}
for mdl in ("A", "B"):
    o = inst(f"KUKA_PAYLOAD_{mdl}", c_ga, f"LIB_MODEL_{mdl}", (0, 0, 0))
    paint(o, pm)
    o.parent = j6
    o.matrix_parent_inverse = rest6.inverted()
    o.matrix_basis = T6.inverted() @ root_m.inverted() @ Matrix.Translation(PICK - Vector((0, 0, FRAME_H + 0.005)))
    payload[mdl] = o


def carry(f, model, colour):
    for mdl, o in payload.items():
        o.hide_viewport = o.hide_render = model != mdl
        o.keyframe_insert("hide_viewport", frame=f)
        o.keyframe_insert("hide_render", frame=f)
    if colour:
        b = pm.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = COLOURS[colour]
        b.inputs["Base Color"].keyframe_insert("default_value", frame=f)
        pm.diffuse_color = COLOURS[colour]
        pm.keyframe_insert("diffuse_color", frame=f)


carry(1, None, None)
last_home = -1e9
for ls, lc, serial, g in load_win:
    if ls + 60 < W0 or ls - 60 > W1:
        continue
    u = units[serial]
    rel = release[serial]
    back = rel + 6
    seq = [(g - 14, "home"), (g - 7, "pick_up"), (g, "pick"), (g + 5, "pick_up"), (g + 12, "place_up"),
           (rel, "place"), (back, "place_up"), (back + 8, "home")]
    for t, nm in seq:
        if t <= last_home:
            continue
        pose_kuka(k_joints, K_POSES[nm], fr(t))
    last_home = back + 8
    prefs.keyframe_new_interpolation_type = "CONSTANT"
    carry(fr(g), u["model"][-1], u["colour"])
    carry(fr(rel), None, None)
    prefs.keyframe_new_interpolation_type = "BEZIER"

# --- HUD: camera-parented text, refreshed by a frame-change handler (registered text module) -----------
cam = bpy.data.objects.get("CAM_Main")
if cam:
    hud_m = mat("M_HUD", (1, 1, 1, 1), emit=2.0)
    stop_m = mat("M_HUD_Stop", (1, 0.05, 0.05, 1), emit=4.0)
    for name, txt, loc, size, m in [("HUD_Clock", "", (-0.70, 0.37, -1), 0.032, hud_m),
                                    ("HUD_KPI", "", (-0.70, 0.32, -1), 0.026, hud_m),
                                    ("HUD_Stop", "", (0.0, -0.36, -1), 0.04, stop_m)]:
        o = label(name, root, txt, loc, size, m)
        o.data.align_x = "LEFT" if name != "HUD_Stop" else "CENTER"
        o.parent = cam
    ships = sorted(u["ship"] for u in units.values() if "ship" in u)
    hud = {"W0": W0, "FPS": FPS, "SPEED": SPEED, "start_clock": meta.get("shift_start_clock") or "06:00",
           "t0": W0, "ships": ships, "stops": stops, "takt": meta["takt_s"],
           "names": {s["id"]: s["name"].replace("_", " ") for s in stations}}
    tb = bpy.data.texts.get("hud_data.json") or bpy.data.texts.new("hud_data.json")
    tb.from_string(json.dumps(hud))
    code = '''import bpy, bisect, json
def _hud(scene, *_):
    d = json.loads(bpy.data.texts["hud_data.json"].as_string())
    t = d["W0"] + (scene.frame_current - 1) / d["FPS"] * d["SPEED"]
    h, m = map(int, d["start_clock"].split(":"))
    clock = h * 3600 + m * 60 + t
    n = bisect.bisect_right(d["ships"], t) - bisect.bisect_right(d["ships"], d["t0"])
    hrs = max((t - d["t0"]) / 3600, 1e-6)
    stop = next((r for r in d["stops"] if r[0] <= t < r[1]), None)
    ob = bpy.data.objects
    if "HUD_Clock" in ob:
        ob["HUD_Clock"].data.body = "%02d:%02d:%02d   takt %d s   x%d" % (clock // 3600 % 24, clock // 60 % 60, clock % 60, d["takt"], d["SPEED"])
        ob["HUD_KPI"].data.body = "Shipped %d   |   %.1f JPH (target %.1f)" % (n, n / hrs, 3600 / d["takt"])
        ob["HUD_Stop"].data.body = ("LINE STOP  %s %s  %ds" % (stop[2], d["names"].get(stop[2], ""), t - stop[0])) if stop else ""
for f in [f for f in bpy.app.handlers.frame_change_post if getattr(f, "__name__", "") == "_hud"]:
    bpy.app.handlers.frame_change_post.remove(f)
bpy.app.handlers.frame_change_post.append(_hud)
'''
    hb = bpy.data.texts.get("hud_handler.py") or bpy.data.texts.new("hud_handler.py")
    hb.from_string(code)
    hb.use_module = True
    exec(compile(code, "hud_handler.py", "exec"), {"__name__": "hud_handler"})


# --- actors: operators with arms, inspector/packer, replenisher
exec(open(os.path.join(ROOT, "blender", "actors.py"), encoding="utf-8").read())
exec(open(os.path.join(ROOT, "blender", "upstream_ui.py"), encoding="utf-8").read())

# --- viewport playback: Solid shading shows material colours (diffuse_color mirrors Base Color)
for m in bpy.data.materials:
    if m.use_nodes and m.node_tree and "Principled BSDF" in m.node_tree.nodes and not (m.animation_data and m.animation_data.action):
        m.diffuse_color = m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value
sc.sync_mode = "FRAME_DROP"          # play in real time, skip frames if the viewport lags
sc.frame_current = 1
