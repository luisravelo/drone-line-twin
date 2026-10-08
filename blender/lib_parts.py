"""One-time library prep for lineside logistics (run inside Blender).

- LIB_TOTE: the 24" plastic tote body only (no gridfinity slots) from Fusion (cad/usd/TOTE.usdz), metres, Z-up, origin bottom-centre.
- LIB_PART_*: one loose part per type, cut from the GA category meshes (cluster nearest the first vertex),
  origin bottom-centre: MOT, CAM, ANT, STACK, PROP_TRI, PROP_BI, BAT.
"""
import os

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

# repo root = parent of the folder holding the .blend (blender/drone_line_twin.blend); override with DRONETWIN_ROOT
ROOT = os.environ.get("DRONETWIN_ROOT") or os.path.dirname(os.path.dirname(bpy.path.abspath(bpy.data.filepath)))
lib = bpy.data.collections["LIB_ASSETS"]


def put(name, me):
    ob = bpy.data.objects.get(name) or bpy.data.objects.new(name, me)
    ob.data = me
    if ob.name not in lib.objects:
        lib.objects.link(ob)
    return ob


def recentre(me):
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mn, mx = co.min(0), co.max(0)
    co -= np.array([(mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, mn[2]])
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    return (mx - mn).round(4)


# --- tote ---------------------------------------------------------------------------------------------
if "LIB_TOTE" not in bpy.data.objects:
    before = set(bpy.data.objects)
    bpy.ops.wm.usd_import(filepath=os.path.join(ROOT, "cad", "usd", "TOTE.usdz"))
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    bm = bmesh.new()
    for o in new:
        if o.type == "MESH":
            m = o.data.copy()
            m.transform(o.matrix_world)
            bm.from_mesh(m)
            bpy.data.meshes.remove(m)
    me = bpy.data.meshes.new("LIB_TOTE_MESH")
    bm.to_mesh(me)
    bm.free()
    for o in new:
        bpy.data.objects.remove(o)
    tm = bpy.data.materials.get("M_Tote") or bpy.data.materials.new("M_Tote")
    tm.use_nodes = True
    tm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.08, 0.30, 0.70, 1)
    tm.diffuse_color = (0.08, 0.30, 0.70, 1)
    me.materials.append(tm)
    print("tote", recentre(me), len(me.polygons))
    put("LIB_TOTE", me)


# --- one loose part per type ------------------------------------------------------------------------------
def cut_one(src, name, radius=0.03):
    s = bpy.data.objects[src].data
    bm = bmesh.new()
    bm.from_mesh(s)
    co = np.array([v.co[:] for v in bm.verts])
    c = co[np.argmax(co[:, 0] + co[:, 1])][:2]           # a cluster at one corner of the drone
    keep = np.hypot(co[:, 0] - c[0], co[:, 1] - c[1]) < radius
    bmesh.ops.delete(bm, geom=[v for v, k in zip(bm.verts, keep) if not k], context="VERTS")
    me = bpy.data.meshes.get(name + "_MESH") or bpy.data.meshes.new(name + "_MESH")
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    for m in s.materials:
        me.materials.append(m)
    print(name, recentre(me), len(me.polygons))
    put(name, me)


cut_one("LIB_A_MOT12", "LIB_PART_MOT")
# single props (LIB_PART_PROP_TRI / _BI) are built by lib_props.py
cut_one("LIB_A_ANT", "LIB_PART_ANT", 0.04)
for src, name in (("LIB_A_CAM", "LIB_PART_CAM"), ("LIB_A_STACK", "LIB_PART_STACK"), ("LIB_A_BAT", "LIB_PART_BAT")):
    me = bpy.data.objects[src].data.copy()
    me.name = name + "_MESH"
    print(name, recentre(me), len(me.polygons))
    put(name, me)


# --- AMR wheels: replace the imported wheel islands with clean black cylinders (24 segments, 2 wheels) -----------
def amr_wheels_clean():
    me = bpy.data.objects["LIB_AMR"].data
    nv = len(me.vertices)
    co = np.empty(nv * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ed = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ed)
    ed = ed.reshape(-1, 2)
    lab = np.arange(nv)
    a, b = ed[:, 0], ed[:, 1]
    while True:
        m = np.minimum(lab[a], lab[b])
        old = lab.copy()
        np.minimum.at(lab, a, m)
        np.minimum.at(lab, b, m)
        lab = lab[lab]
        if np.array_equal(lab, old):
            break
    wheel_v, wheels = np.zeros(nv, bool), {}
    for k in np.unique(lab):
        sel = lab == k
        p = co[sel]
        lo, hi = p.min(0), p.max(0)
        c, d = (lo + hi) / 2, hi - lo
        if 0.26 <= abs(c[0]) <= 0.34 and abs(c[1]) < 0.02 and d[1] <= 0.235 and d[2] <= 0.215 and c[2] <= 0.13:
            wheel_v |= sel
            w = wheels.setdefault(np.sign(c[0]), [lo.copy(), hi.copy()])
            w[0], w[1] = np.minimum(w[0], lo), np.maximum(w[1], hi)
    blk = bpy.data.materials.get("M_Wheel") or bpy.data.materials.new("M_Wheel")
    blk.use_nodes = True
    blk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.015, 0.015, 0.015, 1)
    blk.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.7
    blk.diffuse_color = (0.015, 0.015, 0.015, 1)
    if blk.name not in [m_.name for m_ in me.materials if m_]:
        me.materials.append(blk)
    idx = [m_.name for m_ in me.materials].index(blk.name)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if wheel_v[v.index]], context="VERTS")
    for sgn, (lo, hi) in wheels.items():
        c = (lo + hi) / 2
        r = max(hi[1] - lo[1], hi[2] - lo[2]) / 2
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=r, radius2=r, depth=hi[0] - lo[0],
                                    matrix=Matrix.Translation(c.tolist()) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
        for v in res["verts"]:
            for f in v.link_faces:
                f.material_index = idx
                f.smooth = abs(f.normal.x) < 0.5
    bm.to_mesh(me)
    bm.free()
    return len(wheels), sum(1 for p_ in me.polygons if p_.material_index == idx)


print("AMR wheels (count, faces):", amr_wheels_clean())
