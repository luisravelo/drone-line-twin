"""KUKA loader rig: picks painted frames from the PBS top shelf and places them on the AMR at ST00.

Joint origins/axes/limits come from the Fusion design "Kuka Robotic Arm" (asBuiltJoints A1-A6, read
2026-10-07), converted cm -> m. They are in the same model frame as the USDZ export, so the link meshes
(LIB_KUKA_*) and the joints line up. Angles below are deltas from the exported pose.
Exec'd by build_scene.py, which provides bpy, coll helpers and the scene constants.
"""
import math

import numpy as np
from mathutils import Matrix, Quaternion, Vector

KUKA_JOINTS = [  # name, origin (m), axis, limits (deg, absolute), exported value (deg)
    ("A1", (0.0, -0.0652, 0.37531), (0.0, 0.0, -1.0), (-180, 180), -0.85),
    ("A2", (0.27305, -0.19941, 0.63601), (0.099, 0.995, 0.0), (-60, 30), 20.63),
    ("A3", (-0.35992, -0.10977, 0.8693), (0.099, 0.995, 0.0), (-15, 90), -14.48),
    ("A4", (0.13315, -0.04529, 0.88556), (-0.992, 0.099, -0.08), (-360, 360), 156.99),
    ("A5", (0.32074, -0.03193, 0.85731), (0.123, 0.586, -0.801), (-130, 130), 51.9),
    ("A6", (0.47697, 0.03896, 1.02), (0.729, 0.494, 0.474), (-360, 360), -7.1),
]
KUKA_LINKS = ["L1", "L2", "L3", "L4", "L5", "L6"]           # link k moves with joint k
TOOL_DIR = np.array(KUKA_JOINTS[5][2]) / np.linalg.norm(KUKA_JOINTS[5][2])
W_DIR = 0.6   # weight of "tool points down" vs tip position (model metres)
TIP = np.array((0.5285, 0.0735, 1.053)) + 0.03 * TOOL_DIR   # between the finger pads


def _rot(o, ax, deg):
    ax = np.array(ax) / np.linalg.norm(ax)
    th = math.radians(deg)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    R = np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = np.array(o) - R @ np.array(o)
    return T


def kuka_fk(d):
    """Cumulative transforms (model frame) for joint deltas d (deg, 6)."""
    T, out = np.eye(4), []
    for (name, o, ax, lim, v0), di in zip(KUKA_JOINTS, d):
        T = T @ _rot(o, ax, di)
        out.append(T.copy())
    return out


def kuka_ik(target, d0, down=np.array((0, 0, -1.0)), iters=200, limits=True):
    """Damped least squares on A1-A5 for tip position + tool pointing down. Returns (deltas, error m).
    limits=False: the loader repeats one fixed motion, so the Fusion joint limits are not enforced."""
    d = np.array(d0, float)
    lo = np.array([l[0] - v for _, _, _, l, v in KUKA_JOINTS]) if limits else np.full(6, -1e9)
    hi = np.array([l[1] - v for _, _, _, l, v in KUKA_JOINTS]) if limits else np.full(6, 1e9)

    def res(dd):
        T = kuka_fk(dd)[-1]
        p = T[:3, :3] @ TIP + T[:3, 3]
        r = T[:3, :3] @ TOOL_DIR
        return np.r_[p - target, W_DIR * (r - down)]

    for _ in range(iters):
        r = res(d)
        J = np.zeros((6, 5))
        for k in range(5):
            e = np.zeros(6)
            e[k] = 0.05
            J[:, k] = (res(d + e) - r) / 0.05
        step = np.linalg.solve(J.T @ J + 1e-3 * np.eye(5), -J.T @ r)
        d[:5] = np.clip(d[:5] + step, lo[:5], hi[:5])
        if np.linalg.norm(step) < 1e-4:
            break
    T = kuka_fk(d)[-1]
    return d, float(np.linalg.norm(T[:3, :3] @ TIP + T[:3, 3] - target))


def build_kuka(parent_coll, loc, scale, rot_z=0.0, prefix="KUKA"):
    """Per joint: KUKA_Ax (static, rest frame with Z on the joint axis) -> KUKA_Ax_rot (animated Euler Z only,
    so keyframes interpolate the joint angle itself) -> link mesh + next joint."""
    root = bpy.data.objects.new(f"{prefix}_ROOT", None)
    root.location, root.scale, root.rotation_euler.z = loc, (scale,) * 3, rot_z
    parent_coll.objects.link(root)
    base = bpy.data.objects.new(f"{prefix}_BASE", bpy.data.objects["LIB_KUKA_BASE"].data)
    base.parent = root
    parent_coll.objects.link(base)
    rots, prev, prev_rest = [], root, Matrix()
    for (name, o, ax, lim, v0), link in zip(KUKA_JOINTS, KUKA_LINKS):
        q0 = Vector(ax).normalized().to_track_quat("Z", "Y")
        rest = Matrix.Translation(o) @ q0.to_matrix().to_4x4()
        j = bpy.data.objects.new(f"{prefix}_{name}", None)
        j.empty_display_size = 0.08
        j.matrix_basis = rest
        j.parent = prev
        j.matrix_parent_inverse = prev_rest.inverted()
        parent_coll.objects.link(j)
        r = bpy.data.objects.new(f"{prefix}_{name}_rot", None)
        r.empty_display_size = 0.05
        r.parent = j
        parent_coll.objects.link(r)
        m = bpy.data.objects.new(f"{prefix}_{link}", bpy.data.objects[f"LIB_KUKA_{link}"].data)
        m.parent = r
        m.matrix_parent_inverse = rest.inverted()
        parent_coll.objects.link(m)
        r["rest"] = [list(row) for row in rest]
        rots.append(r)
        prev, prev_rest = r, rest
    return root, rots


def pose_kuka(rots, d, frame=None):
    for r, di in zip(rots, d):
        r.rotation_euler.z = math.radians(di)
        if frame is not None:
            r.keyframe_insert("rotation_euler", index=2, frame=frame)
