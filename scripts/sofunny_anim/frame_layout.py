from __future__ import annotations

from pathlib import Path

from PIL import Image


def split_horizontal_sheet(image: Image.Image, frames: int) -> list[Image.Image]:
    if frames <= 0:
        raise ValueError("frames must be positive")
    width, height = image.size
    return [
        image.crop((round(i * width / frames), 0, round((i + 1) * width / frames), height)).convert("RGBA")
        for i in range(frames)
    ]


def split_grid_sheet(image: Image.Image, rows: int, columns: int, *, allow_uneven: bool = False) -> list[Image.Image]:
    if rows <= 0 or columns <= 0:
        raise ValueError("rows and columns must be positive")
    width, height = image.size
    if not allow_uneven and (width % columns != 0 or height % rows != 0):
        raise ValueError("input dimensions are not divisible by rows/columns")
    frames = []
    for row in range(rows):
        for col in range(columns):
            if allow_uneven:
                box = (
                    round(col * width / columns),
                    round(row * height / rows),
                    round((col + 1) * width / columns),
                    round((row + 1) * height / rows),
                )
            else:
                cell_w = width // columns
                cell_h = height // rows
                box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
            frames.append(image.crop(box).convert("RGBA"))
    return frames


def write_sequence(frames: list[Image.Image], out_dir: str | Path) -> list[Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, frame in enumerate(frames):
        path = target / f"{index:03d}.png"
        frame.save(path)
        paths.append(path)
    return paths


def read_sequence(frame_dir: str | Path) -> list[Image.Image]:
    paths = sorted(Path(frame_dir).expanduser().glob("*.png"))
    if not paths:
        raise ValueError(f"no PNG frames in {frame_dir}")
    return [Image.open(path).convert("RGBA") for path in paths]
