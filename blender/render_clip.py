"""Background render: blender -b drone_line_twin.blend -P render_clip.py -- <start> <end> <out.mp4>"""
import sys

import bpy

start, end, out = int(sys.argv[-3]), int(sys.argv[-2]), sys.argv[-1]
exec(bpy.data.texts["hud_handler.py"].as_string(), {"__name__": "hud_handler"})   # HUD text updates per frame
sc = bpy.context.scene
sc.frame_start, sc.frame_end = start, end
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = 16
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1280, 720, 100
im = sc.render.image_settings
if hasattr(im, "media_type"):
    im.media_type = "VIDEO"
im.file_format = "FFMPEG"
sc.render.ffmpeg.format = "MPEG4"
sc.render.ffmpeg.codec = "H264"
sc.render.ffmpeg.constant_rate_factor = "HIGH"
sc.render.filepath = out
bpy.ops.render.render(animation=True)
print("RENDER_DONE", out)
