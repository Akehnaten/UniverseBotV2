# pip install Pillow
from pathlib import Path
from PIL import Image

for f in Path("src").rglob("*.png"):
    if f.stat().st_size > 9 * 1024 * 1024:  # > 9MB
        img = Image.open(f)
        # Redimensionar si es necesario (máx 4000px en el lado más largo)
        img.thumbnail((4000, 4000), Image.LANCZOS)
        img.save(f, "PNG", optimize=True)
        print(f"✅ Comprimida: {f.name} → {f.stat().st_size / 1024 / 1024:.1f}MB")