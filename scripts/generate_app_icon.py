#!/usr/bin/env python3
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "resources" / "icons"


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _write_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    raw = b"".join(b"\x00" + pixels[row * width * 4 : (row + 1) * width * 4] for row in range(height))
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def _rounded_rect_alpha(x: float, y: float, size: int, radius: float) -> float:
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    distance = math.hypot(x - cx, y - cy)
    return max(0.0, min(1.0, radius + 1.0 - distance))


def render_icon(size: int) -> bytes:
    pixels = bytearray()
    radius = size * 0.22
    for y in range(size):
        for x in range(size):
            alpha = _rounded_rect_alpha(x, y, size - 1, radius)
            if alpha <= 0:
                pixels.extend((0, 0, 0, 0))
                continue
            t = y / max(size - 1, 1)
            r = int(10 + 28 * t)
            g = int(109 + 35 * (1 - t))
            b = int(253 - 28 * t)
            px = x / size
            py = y / size
            # Minimal paper plane / mail mark.
            line = abs((py - 0.56) - 0.42 * (px - 0.5))
            line2 = abs((py - 0.56) + 0.42 * (px - 0.5))
            wing = (0.24 < px < 0.78 and 0.35 < py < 0.72 and (line < 0.035 or line2 < 0.035))
            body = 0.34 < px < 0.72 and abs(py - 0.48) < 0.035
            if wing or body:
                r, g, b = 255, 255, 255
            pixels.extend((r, g, b, int(255 * alpha)))
    return bytes(pixels)


def _write_icns(path: Path, png_chunks: dict[bytes, bytes]) -> None:
    chunks = []
    for chunk_type, data in png_chunks.items():
        chunks.append(chunk_type + struct.pack(">I", len(data) + 8) + data)
    body = b"".join(chunks)
    path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def _write_ico(path: Path, png_files: list[Path]) -> None:
    entries = []
    images = []
    offset = 6 + 16 * len(png_files)
    for png_file in png_files:
        data = png_file.read_bytes()
        size_name = png_file.stem.split("_", 1)[-1].split("x", 1)[0]
        try:
            size = int(size_name.replace("@2", ""))
        except ValueError:
            size = 0
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(data), offset))
        images.append(data)
        offset += len(data)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(png_files)) + b"".join(entries) + b"".join(images))


def main() -> int:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    png_path = ICON_DIR / "app_icon.png"
    _write_png(png_path, 1024, 1024, render_icon(1024))

    iconset = ICON_DIR / "app_icon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    png_by_size: dict[int, Path] = {}
    for size in sizes:
        name = {
            16: "icon_16x16.png",
            32: "icon_16x16@2x.png",
            64: "icon_32x32@2x.png",
            128: "icon_128x128.png",
            256: "icon_128x128@2x.png",
            512: "icon_256x256@2x.png",
            1024: "icon_512x512@2x.png",
        }[size]
        target = iconset / name
        _write_png(target, size, size, render_icon(size))
        png_by_size[size] = target
    for size, name in ((32, "icon_32x32.png"), (256, "icon_256x256.png"), (512, "icon_512x512.png")):
        target = iconset / name
        _write_png(target, size, size, render_icon(size))
        png_by_size.setdefault(size, target)

    iconutil = shutil.which("iconutil")
    wrote_icns = False
    if iconutil:
        try:
            subprocess.run(
                [iconutil, "-c", "icns", str(iconset), "-o", str(ICON_DIR / "app_icon.icns")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            wrote_icns = True
        except subprocess.CalledProcessError:
            pass
    if not wrote_icns:
        _write_icns(
            ICON_DIR / "app_icon.icns",
            {
                b"ic07": png_by_size[128].read_bytes(),
                b"ic08": png_by_size[256].read_bytes(),
                b"ic09": png_by_size[512].read_bytes(),
                b"ic10": png_by_size[1024].read_bytes(),
            },
        )
    _write_ico(
        ICON_DIR / "app_icon.ico",
        [png_by_size[16], png_by_size[32], png_by_size[64], png_by_size[128], png_by_size[256]],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
