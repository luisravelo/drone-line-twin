"""Rebuild LIB_{A,B}_MOT12/MOT34 as readable 2207-style motor proxies (run once inside Blender).

Motor centres, radius and height come from the existing proxy meshes (derived from the Fusion GA USDZ).
Parts per motor: dark mount base, silver bell with a dark magnet band, dark top cap, silver shaft.
"""
import bmesh
import bpy
import numpy as np
from mathutils import Matrix


def _cyl(bm, c, z0, z1, r, mi, seg=32):
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=z1 - z0,
                                matrix=Matrix.Translation((c[0], c[1], (z0 + z1) / 2)))
    for v in res["verts"]:
        for f in v.link_faces:
            f.material_index = mi
            f.smooth = abs(f.normal.z) < 0.5


def rebuild(name, silver, dark):
    me = bpy.data.objects[name].data
    co = np.array([v.co[:] for v in me.vertices])
    centres = {}
    # cluster by proximity in XY (motors are > 0.1 m apart)
    left = co.copy()
    while len(left):
        c = left[0, :2]
        m = np.hypot(left[:, 0] - c[0], left[:, 1] - c[1]) < 0.04
        grp = left[m]
        centres[len(centres)] = (grp[:, :2].mean(0), np.hypot(*(grp[:, :2] - grp[:, :2].mean(0)).T).max(),
                                 grp[:, 2].min(), grp[:, 2].max())
        left = left[~m]
    bm = bmesh.new()
    for c, R, z0, z1 in centres.values():
        H = z1 - z0
        _cyl(bm, c, z0, z0 + 0.18 * H, 0.95 * R, 1)                 # mount base
        _cyl(bm, c, z0 + 0.18 * H, z0 + 0.82 * H, R, 0)             # bell
        _cyl(bm, c, z0 + 0.40 * H, z0 + 0.58 * H, 1.03 * R, 1)      # magnet band
        _cyl(bm, c, z0 + 0.82 * H, z0 + 0.90 * H, 0.75 * R, 1)      # top cap
        _cyl(bm, c, z0 + 0.90 * H, z1 + 0.25 * H, 0.14 * R, 0, 16)  # shaft
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(silver)
    me.materials.append(dark)
    return len(centres), len(me.polygons)


silver = bpy.data.materials["M_Part_MOT"]
dark = bpy.data.materials["M_Dark"]
for mdl in ("A", "B"):
    for cat in ("MOT12", "MOT34"):
        print(mdl, cat, rebuild(f"LIB_{mdl}_{cat}", silver, dark))
