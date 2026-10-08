"""Build LIB_{A,B}_PROP_TRI / PROP_BI: 5" props seated on each motor cap (run once inside Blender).

Motor centres and cap height come from the motor proxies (lib_motors.py). TRI = 3 blades, BI = 2 blades,
each with a hub and a dark prop nut; colours differ so the option reads at a glance.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

R_TIP, HUB_R, HUB_H, NUT_R, NUT_H = 0.062, 0.009, 0.007, 0.0055, 0.006


def motor_tops(name):
    co = np.array([v.co[:] for v in bpy.data.objects[name].data.vertices])
    out, left = [], co.copy()
    while len(left):
        c = left[0, :2]
        m = np.hypot(left[:, 0] - c[0], left[:, 1] - c[1]) < 0.04
        g = left[m]
        zmin, zmax = g[:, 2].min(), g[:, 2].max()
        out.append((g[:, :2].mean(0), zmin + 0.9 * (zmax - zmin) / 1.25))
        left = left[~m]
    return out


def blade(bm, c, z, ang, mi):
    # tapered, slightly pitched blade from the hub to the tip
    L = R_TIP - HUB_R
    verts = []
    for r, w in ((HUB_R * 0.8, 0.016), (HUB_R + 0.55 * L, 0.014), (R_TIP, 0.006)):
        verts.append([(r, -w / 2, -0.0012), (r, w / 2, 0.0012)])
    vs = []
    for (a, b) in verts:
        for (x, y, dz) in (a, b):
            for t in (-0.001, 0.001):
                vs.append(bm.verts.new((x, y, dz + t)))
    # 3 sections x 4 verts: build quads between sections
    for k in range(2):
        s0, s1 = vs[4 * k:4 * k + 4], vs[4 * k + 4:4 * k + 8]
        for (i, j) in ((0, 2), (2, 3), (3, 1), (1, 0)):
            f = bm.faces.new((s0[i], s0[j], s1[j], s1[i]))
            f.material_index = mi
    for s in (vs[0:4], vs[8:12]):
        f = bm.faces.new((s[0], s[2], s[3], s[1]))
        f.material_index = mi
    M = Matrix.Translation((c[0], c[1], z + HUB_H / 2)) @ Matrix.Rotation(ang, 4, "Z")
    bmesh.ops.transform(bm, matrix=M, verts=vs)


def cylinder(bm, c, z0, h, r, mi, seg=20):
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=h,
                                matrix=Matrix.Translation((c[0], c[1], z0 + h / 2)))
    for v in res["verts"]:
        for f in v.link_faces:
            f.material_index = mi


def build(mdl, ptype, blades, mat_blade, mat_dark):
    bm = bmesh.new()
    for cat in ("MOT12", "MOT34"):
        for k, (c, ztop) in enumerate(motor_tops(f"LIB_{mdl}_{cat}")):
            cylinder(bm, c, ztop, HUB_H, HUB_R, 0)
            cylinder(bm, c, ztop + HUB_H, NUT_H, NUT_R, 1, 6)
            for b in range(blades):
                blade(bm, c, ztop, 2 * math.pi * b / blades + 0.4 * k, 0)
    bm.normal_update()
    name = f"LIB_{mdl}_PROP_{ptype}"
    me = bpy.data.meshes.get(name + "_MESH") or bpy.data.meshes.new(name + "_MESH")
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(mat_blade)
    me.materials.append(mat_dark)
    ob = bpy.data.objects.get(name) or bpy.data.objects.new(name, me)
    ob.data = me
    if ob.name not in bpy.data.collections["LIB_ASSETS"].objects:
        bpy.data.collections["LIB_ASSETS"].objects.link(ob)
    return len(me.polygons)


def pmat(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = rgba
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35
    m.diffuse_color = rgba
    return m


TRI = pmat("M_Prop_TRI", (0.95, 0.42, 0.04, 1))     # orange tri-blade
BI = pmat("M_Prop_BI", (0.05, 0.45, 0.95, 1))       # blue bi-blade
DARK = bpy.data.materials["M_Dark"]
for mdl in ("A", "B"):
    print(mdl, build(mdl, "TRI", 3, TRI, DARK), build(mdl, "BI", 2, BI, DARK))

# single loose props for totes (origin at the hub bottom)
for pt, nb, m in (("TRI", 3, TRI), ("BI", 2, BI)):
    bm = bmesh.new()
    cylinder(bm, (0, 0), 0, HUB_H, HUB_R, 0)
    cylinder(bm, (0, 0), HUB_H, NUT_H, NUT_R, 1, 6)
    for b in range(nb):
        blade(bm, (0, 0), 0, 2 * math.pi * b / nb, 0)
    name = f"LIB_PART_PROP_{pt}"
    me = bpy.data.meshes.get(name + "_MESH") or bpy.data.meshes.new(name + "_MESH")
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(m)
    me.materials.append(DARK)
    ob = bpy.data.objects.get(name) or bpy.data.objects.new(name, me)
    ob.data = me
    if ob.name not in bpy.data.collections["LIB_ASSETS"].objects:
        bpy.data.collections["LIB_ASSETS"].objects.link(ob)
