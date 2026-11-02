"""Optimize generated originals without changing their visual content or alpha."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw

parser = argparse.ArgumentParser()
parser.add_argument('source_directory', type=Path)
parser.add_argument('--contact-sheet', type=Path)
args = parser.parse_args()
target = Path(__file__).resolve().parent.parent / 'static' / 'sectors'
manifest = json.loads((target / 'artwork.json').read_text(encoding='utf-8'))
sheet = Image.new('RGB', (960, 800), '#100827')
draw = ImageDraw.Draw(sheet)
total = 0
for i, asset in enumerate(manifest['assets']):
    original = Image.open(args.source_directory / asset['source_filename']).convert('RGBA')
    bbox = original.getbbox()
    if bbox:
        original = original.crop(bbox)
    original.thumbnail((330, 330), Image.Resampling.LANCZOS)
    icon = Image.new('RGBA', (384, 384))
    icon.alpha_composite(original, ((384-original.width)//2, (384-original.height)//2))
    output = target / asset['output']
    icon.save(output, 'WEBP', quality=86, method=6)
    total += output.stat().st_size
    preview = icon.resize((175, 175), Image.Resampling.LANCZOS)
    x, y = i % 4 * 240 + 32, i // 4 * 200
    sheet.paste(preview, (x, y), preview)
    draw.text((i % 4 * 240 + 22, y + 177), asset['id'], fill='#B9C9E4')
if args.contact_sheet:
    sheet.save(args.contact_sheet)
print(f'Optimized {len(manifest["assets"])} transparent illustrations: {total:,} bytes total.')
