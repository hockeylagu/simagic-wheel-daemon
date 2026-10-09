"""
Adapts the user's authentic Simagic GT Neo image into application icons.
Places the wheel centered on a clean square canvas with optimal padding
for both Windows System Tray and desktop shortcut icon display.
"""

import os
from PIL import Image

src_img_path = r"C:/Users/Samuel/.gemini/antigravity/brain/21cc9cb0-d4cb-4368-9caf-2cb3f5e9afa1/.user_uploaded/media_1791508816274_228647f9.png"
repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
assets_dir = os.path.join(repo_dir, "assets")
os.makedirs(assets_dir, exist_ok=True)

dest_png = os.path.join(assets_dir, "icon.png")
dest_ico = os.path.join(assets_dir, "icon.ico")

# 1. Open source image
wheel = Image.open(src_img_path).convert("RGBA")
w, h = wheel.size

# 2. Determine background color or transparency
# Sample top-left corner
bg_color = wheel.getpixel((0, 0))

# 3. Create a clean square canvas with slight padding so the wheel breathes
side = int(max(w, h) * 1.1)
square = Image.new("RGBA", (side, side), bg_color)

# 4. Paste centered
offset_x = (side - w) // 2
offset_y = (side - h) // 2
square.paste(wheel, (offset_x, offset_y), wheel)

# 5. Save master 512x512 PNG
final_png = square.resize((512, 512), Image.Resampling.LANCZOS)
final_png.save(dest_png, format="PNG")

# 6. Generate multi-resolution ICO for Windows
ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ico_images = [square.resize(s, Image.Resampling.LANCZOS) for s in ico_sizes]
ico_images[0].save(dest_ico, format="ICO", sizes=ico_sizes, append_images=ico_images[1:])

print(f"Successfully processed authentic Simagic GT Neo image:")
print(f"  Source: {src_img_path} ({w}x{h})")
print(f"  Target PNG: {dest_png} (512x512)")
print(f"  Target ICO: {dest_ico} (16 to 256px)")
