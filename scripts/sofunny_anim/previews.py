from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


def checker(size: tuple[int, int], block: int = 16) -> Image.Image:
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    width, height = size
    for y in range(0, height, block):
        for x in range(0, width, block):
            if ((x // block) + (y // block)) % 2 == 0:
                draw.rectangle((x, y, min(width - 1, x + block - 1), min(height - 1, y + block - 1)), fill=(226, 226, 226, 255))
    return image


def make_global_palette(frames: list[Image.Image]) -> list[int]:
    palette_colors: list[tuple[int, int, int]] = [(0, 255, 0)]
    seen = {palette_colors[0]}
    counts: dict[tuple[int, int, int], int] = {}
    for frame in frames:
        for count, color in frame.convert("RGBA").getcolors(maxcolors=1000000) or []:
            r, g, b, a = color
            if a:
                rgb = (r, g, b)
                counts[rgb] = counts.get(rgb, 0) + count
    for rgb, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        if rgb in seen:
            continue
        palette_colors.append(rgb)
        seen.add(rgb)
        if len(palette_colors) == 256:
            break
    data: list[int] = []
    for rgb in palette_colors:
        data.extend(rgb)
    data.extend([0, 0, 0] * (256 - len(palette_colors)))
    return data


def save_transparent_gif(frames: list[Image.Image], path: str | Path, duration: int) -> None:
    rgba_frames = [frame.convert("RGBA") for frame in frames]
    palette = make_global_palette(rgba_frames)
    colors = [tuple(palette[i : i + 3]) for i in range(0, 768, 3)]
    color_to_index = {rgb: i for i, rgb in enumerate(colors)}
    nearest_cache: dict[tuple[int, int, int], int] = {}

    def nearest_index(rgb: tuple[int, int, int]) -> int:
        if rgb not in nearest_cache:
            nearest_cache[rgb] = min(range(1, 256), key=lambda i: sum((rgb[c] - colors[i][c]) ** 2 for c in range(3)))
        return nearest_cache[rgb]

    paletted = []
    for frame in rgba_frames:
        out = Image.new("P", frame.size, 0)
        out.putpalette(palette)
        src = frame.load()
        dst = out.load()
        for y in range(frame.height):
            for x in range(frame.width):
                r, g, b, a = src[x, y]
                dst[x, y] = 0 if a == 0 else color_to_index.get((r, g, b), nearest_index((r, g, b)))
        paletted.append(out)
    paletted[0].save(path, save_all=True, append_images=paletted[1:], duration=duration, loop=0, disposal=2, transparency=0, optimize=False, dither=Image.Dither.NONE)


def save_checker_gif(frames: list[Image.Image], path: str | Path, duration: int) -> None:
    out_frames = []
    for frame in frames:
        bg = checker(frame.size, 24)
        bg.alpha_composite(frame.convert("RGBA"))
        out_frames.append(bg.convert("RGB").quantize(colors=128, dither=Image.Dither.NONE))
    out_frames[0].save(path, save_all=True, append_images=out_frames[1:], duration=duration, loop=0, disposal=2, optimize=False)


def save_contact_sheet(frames: list[Image.Image], path: str | Path, cell_size: int = 192) -> None:
    columns = min(6, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGBA", (columns * cell_size, rows * cell_size), (245, 245, 245, 255))
    for i, frame in enumerate(frames):
        cell = checker((cell_size, cell_size), 16)
        cell.alpha_composite(frame.convert("RGBA").resize((cell_size, cell_size), Image.Resampling.LANCZOS))
        draw = ImageDraw.Draw(cell)
        draw.rectangle((0, 0, cell_size - 1, cell_size - 1), outline=(180, 180, 180, 255), width=1)
        draw.text((6, 6), f"{i:02d}", fill=(20, 20, 20, 255))
        sheet.alpha_composite(cell, ((i % columns) * cell_size, (i // columns) * cell_size))
    sheet.save(path)


def save_transparent_sheet(frames: list[Image.Image], path: str | Path) -> None:
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    sheet = Image.new("RGBA", (width * len(frames), height), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        sheet.alpha_composite(frame.convert("RGBA"), (i * width, 0))
    sheet.save(path)

def save_webp(frames: list[Image.Image], path: str | Path, duration: int) -> None:
    rgba = [frame.convert("RGBA") for frame in frames]
    rgba[0].save(path, save_all=True, append_images=rgba[1:], duration=duration, loop=0, lossless=True, exact=True, method=6)

