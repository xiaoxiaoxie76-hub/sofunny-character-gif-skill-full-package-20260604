from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image


def load_rgba(path: str | Path) -> Image.Image:
    return Image.open(Path(path).expanduser()).convert("RGBA")


def parse_canvas(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2:
        raise ValueError("canvas must use WIDTHxHEIGHT, e.g. 384x384")
    width, height = int(parts[0]), int(parts[1])
    if width <= 0 or height <= 0:
        raise ValueError("canvas width and height must be positive")
    return width, height


def is_checker_bg_pixel(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    if a == 0:
        return True
    hi = max(r, g, b)
    lo = min(r, g, b)
    if hi >= 225 and (hi - lo) <= 30:
        return True
    # Some providers draw grey grid/cell borders around checker backgrounds.
    # Treat only edge-connected neutral greys as removable background so internal
    # white shirt, muzzle, teeth, and highlights are preserved by character outlines.
    return hi >= 150 and (hi - lo) <= 35


def remove_edge_connected_checker(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pix = rgba.load()
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    def add_if_bg(x: int, y: int) -> None:
        if (x, y) in visited:
            return
        if is_checker_bg_pixel(pix[x, y]):
            visited.add((x, y))
            queue.append((x, y))

    for x in range(width):
        add_if_bg(x, 0)
        add_if_bg(x, height - 1)
    for y in range(height):
        add_if_bg(0, y)
        add_if_bg(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                add_if_bg(nx, ny)

    for x, y in visited:
        r, g, b, _ = pix[x, y]
        pix[x, y] = (r, g, b, 0)
    return rgba


def remove_background(image: Image.Image, mode: str) -> Image.Image:
    rgba = image.convert("RGBA")
    if mode == "transparent":
        return rgba
    if mode == "green":
        pix = rgba.load()
        for y in range(rgba.height):
            for x in range(rgba.width):
                r, g, b, a = pix[x, y]
                if a >= 250 and r <= 8 and g >= 247 and b <= 8:
                    pix[x, y] = (r, g, b, 0)
        return rgba
    if mode == "checker":
        # If the provider sheet already has a real transparent background, do
        # not flood-fill near-white pixels. White costume interiors can be
        # edge-connected through transparent regions after sheet extraction.
        alpha = rgba.getchannel("A")
        width, height = rgba.size
        edge_alpha = []
        for x in range(width):
            edge_alpha.append(alpha.getpixel((x, 0)))
            edge_alpha.append(alpha.getpixel((x, height - 1)))
        for y in range(height):
            edge_alpha.append(alpha.getpixel((0, y)))
            edge_alpha.append(alpha.getpixel((width - 1, y)))
        if edge_alpha and sum(value == 0 for value in edge_alpha) / len(edge_alpha) > 0.25:
            return rgba
        return remove_edge_connected_checker(rgba)
    raise ValueError(f"unsupported background mode: {mode}")


def remove_small_alpha_components(image: Image.Image, min_largest_ratio: float = 0.01) -> tuple[Image.Image, dict]:
    """Remove small detached alpha islands while preserving the main character and large shadows."""
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    pix = alpha.load()
    width, height = alpha.size
    visited: set[tuple[int, int]] = set()
    components: list[list[tuple[int, int]]] = []

    for y in range(height):
        for x in range(width):
            if pix[x, y] == 0 or (x, y) in visited:
                continue
            visited.add((x, y))
            queue: deque[tuple[int, int]] = deque([(x, y)])
            component: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                component.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and pix[nx, ny] > 0 and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
            components.append(component)

    if not components:
        return rgba, {
            "status": "fail",
            "largest_component_area": 0,
            "removed_components": 0,
            "removed_alpha_area": 0,
        }

    largest = max(len(component) for component in components)
    min_area = max(1, round(largest * min_largest_ratio))
    removed_components = 0
    removed_alpha_area = 0
    out_pix = rgba.load()
    for component in components:
        if len(component) >= min_area:
            continue
        removed_components += 1
        removed_alpha_area += len(component)
        for x, y in component:
            r, g, b, _ = out_pix[x, y]
            out_pix[x, y] = (r, g, b, 0)

    return rgba, {
        "status": "pass",
        "largest_component_area": largest,
        "min_component_area": min_area,
        "removed_components": removed_components,
        "removed_alpha_area": removed_alpha_area,
    }
