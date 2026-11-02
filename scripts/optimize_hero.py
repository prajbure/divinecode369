"""Encode generated hero originals as responsive WebP assets, preserving alpha."""
import json
from pathlib import Path
import sys
from PIL import Image

folder = Path(__file__).resolve().parent.parent / "static" / "hero"
manifest = json.loads((folder / "artwork.json").read_text(encoding="utf-8"))
for asset in manifest["assets"]:
    original = Image.open(Path(sys.argv[1]) / asset["source"]).convert("RGBA")
    bounds = original.getbbox()
    if bounds:
        original = original.crop(bounds)
    for size, suffix in [(960, ""), (480, "-small")]:
        resized = original.copy()
        resized.thumbnail((size, int(size * .9)), Image.Resampling.LANCZOS)
        target = folder / asset["output"].replace(".webp", suffix + ".webp")
        resized.save(target, "WEBP", quality=85, method=6)
        print(f"{target.name}: {resized.width}x{resized.height}, {target.stat().st_size:,} bytes")
