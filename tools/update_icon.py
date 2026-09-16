"""
TaskHub - Icon Updater

Usage: drag a square PNG (512x512 or larger) onto update_icon.bat, or run:
    python tools/update_icon.py path/to/icon.png

Regenerates every icon the application ships:
  src/web/icon.ico              EXE, taskbar and tray icon
  src/web/taskhub-icon-192.png  PWA icon
  src/web/taskhub-icon-512.png  PWA icon and the logo inside the UI
A non-square source is padded onto a transparent square instead of stretched.
After this, run build.bat to rebuild the EXE.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(PROJECT_ROOT, 'src', 'web')

print('=== TaskHub Icon Updater ===')

# Only an explicitly given file is accepted. Falling back to "the first PNG
# lying around" used to pick up the app's own icon and rebuild from it.
if len(sys.argv) < 2:
    print('ERROR: Pass a PNG path, or drag a PNG onto update_icon.bat.')
    input('Press Enter to exit...')
    sys.exit(1)

png_path = sys.argv[1]
if not os.path.exists(png_path):
    print('ERROR: File not found: %s' % png_path)
    input('Press Enter to exit...')
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print('ERROR: Pillow is not installed. Run: pip install pillow')
    input('Press Enter to exit...')
    sys.exit(1)

img = Image.open(png_path).convert('RGBA')
w, h = img.size
if w != h:
    side = max(w, h)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    img = canvas
    print(f'Note: source was {w}x{h} (not square) - padded to {side}x{side}.')
if img.size[0] < 512:
    print(f'Warning: source is {img.size[0]}px; 512px or larger looks sharper.')

for size in (192, 512):
    img.resize((size, size), Image.LANCZOS).save(
        os.path.join(WEB_DIR, 'taskhub-icon-%d.png' % size), optimize=True)

sizes = [16, 24, 32, 48, 64, 128, 256]
frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]
frames[-1].save(os.path.join(WEB_DIR, 'icon.ico'), format='ICO',
                sizes=[(s, s) for s in sizes], append_images=frames[:-1])

print(f'[OK] Icons in src/web updated from {png_path}.')
print('Now run build.bat to rebuild the EXE with the new icon!')
input('Press Enter to exit...')
