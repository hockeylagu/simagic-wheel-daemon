"""
Adapts the Simagic GT Neo thin-border icon into application icons.
Generates master 512x512 PNG and multi-resolution Windows ICO (16 to 256px).
"""

import os
from PIL import Image

src_img_path = r"C:/Users/Samuel/.gemini/antigravity/brain/21cc9cb0-d4cb-4368-9caf-2cb3f5e9afa1/wheel_thin_border_1791509563052.jpg"
repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
assets_dir = os.path.join(repo_dir, "assets")
os.makedirs(assets_dir, exist_ok=True)

dest_png = os.path.join(assets_dir, "icon.png")
dest_ico = os.path.join(assets_dir, "icon.ico")

# 1. Open source square image
img = Image.open(src_img_path).convert("RGBA")
w, h = img.size

# 2. Save master 512x512 PNG
final_png = img.resize((512, 512), Image.Resampling.LANCZOS)
final_png.save(dest_png, format="PNG")

# 3. Generate multi-resolution ICO for Windows
ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ico_images = [img.resize(s, Image.Resampling.LANCZOS) for s in ico_sizes]
ico_images[0].save(dest_ico, format="ICO", sizes=ico_sizes, append_images=ico_images[1:])

print("Successfully processed thin-bordered Simagic GT Neo icon:")
print(f"  Source: {src_img_path} ({w}x{h})")
print(f"  Target PNG: {dest_png} (512x512)")
print(f"  Target ICO: {dest_ico} (16 to 256px)")

