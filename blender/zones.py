"""Floor zones and object colours from a plant colour system (zones pale/transparent, objects opaque).

Zones are claims on floor area: pale, ~55 % alpha, z 0.002-0.004. Objects standing on them are opaque:
lineside presentation = dense forest green, fixed structure = navy, movers (AMRs, forklift) = orange.
Exec'd by actors.py after logistics.py (needs the line, upstream and backstock geometry).
"""


def srgb(h, a=1.0):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (a,)


PAL = {"LOGISTICS": ("#8CC7A8", 0.55), "LINESIDE": ("#2F6B4C", 1.0), "ASSEMBLY": ("#7BAAD4", 0.55),
       "ROUTE": ("#F2C21A", 1.0), "STRUCTURE": ("#0A1449", 1.0), "CIRCULATION": ("#C9C9C4", 1.0),
       "QUALITY": ("#C99A3E", 0.55), "BUFFER": ("#C4A96E", 0.55), "MOVER": ("#D96B10", 1.0)}


def pal_mat(key):
    hx, a = PAL[key]
    m = mat(f"M_Zone_{key}", srgb(hx, a), rough=0.8)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Alpha"].default_value = a
    m.diffuse_color = srgb(hx, a)
    if a < 1.0 and hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    return m


c_zone = coll("Zones", root)


def zone(name, key, x0, x1, y0, y1, z=0.002):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    me.materials.append(pal_mat(key))
    o = bpy.data.objects.new(name, me)
    c_zone.objects.link(o)
    return o


# floor = circulation (concrete); zones on top
bpy.data.materials["M_Floor"].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb("#C9C9C4")
bpy.data.materials["M_Floor"].diffuse_color = srgb("#C9C9C4")
Y_LINE0 = FRONT - 0.55
LINE_X0 = STX[0] - TL / 2 - 0.05
zone("ZONE_ASSEMBLY_Line", "ASSEMBLY", LINE_X0, TL * N + 0.05, Y_LINE0, WALL_Y)
zone("ZONE_ASSEMBLY_Fab", "ASSEMBLY", K2_LOC.x - 1.25, BUF_START, Y_LINE0, WALL_Y)          # print + paint
zone("ZONE_BUFFER_Conveyor", "BUFFER", BUF_START, LINE_X0, Y_LINE0, WALL_Y)
zone("ZONE_BUFFER_Ship", "BUFFER", TL * N + 0.05, TL * N + 1.2, -0.95, WALL_Y)
zone("ZONE_QUALITY_Repair", "QUALITY", TL * N + 0.05, TL * N + 1.2, -2.15, -0.95)
zone("ZONE_LOGISTICS_Backstock", "LOGISTICS", BS_X0 - 0.35, BS_X1 + 0.35, BS_BACK - 0.35, BS_FRONT + 0.55)
# milk-run route (opaque yellow): backstock pick face -> along the line front -> back
x_end = max(b["stop"].x for b in bins) + 0.1
y_run = FRONT - 0.28
zone("ROUTE_Line", "ROUTE", LOG_HOME.x - 0.03, x_end, y_run - 0.03, y_run + 0.03, 0.004)
zone("ROUTE_Link", "ROUTE", LOG_HOME.x - 0.03, LOG_HOME.x + 0.03, LOG_HOME.y, y_run, 0.004)

# lineside presentation strip on each bench (dense forest green, under the totes)
for i in range(N - 1):
    zone(f"LINESIDE_{stations[i]['id']}", "LINESIDE", STX[i] - TL / 2 + 0.02, STX[i] + TL / 2 - 0.02,
         FRONT + 0.005, FRONT + 0.17, TH + 0.003)

# fixed structure -> navy; movers -> orange
navy = pal_mat("STRUCTURE")
for o in list(c_up.objects) + list(c_ga.objects):
    if o.type == "MESH" and (o.name.startswith(("BELT_Rail", "BELT_Leg", "RETURN_", "KUKA_Pedestal", "RACK_Up"))
                             or (o.name.startswith("TRANSFER_") and "_Roll_" not in o.name)):
        o.data.materials.clear()
        o.data.materials.append(navy)
amr = bpy.data.materials["M_AMR"]
amr.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = srgb("#D96B10")
amr.diffuse_color = srgb("#D96B10")
