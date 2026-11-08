"""Draw the app icon (a chip with pins) and write icon.png + icon.ico.

Standard library only:  python packaging/make_icon.py
"""
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).parent


def draw(n: int) -> bytes:
    """RGBA pixels of an n x n icon."""
    px = bytearray(n * n * 4)
    s = n / 64.0                                   # drawn on a 64-unit grid

    def rect(x0, y0, x1, y1, rgba, r=0.0):
        for y in range(int(y0 * s), int(y1 * s)):
            for x in range(int(x0 * s), int(x1 * s)):
                if r:                               # rounded corners
                    cx = min(max(x / s, x0 + r), x1 - r)
                    cy = min(max(y / s, y0 + r), y1 - r)
                    if (x / s - cx) ** 2 + (y / s - cy) ** 2 > r * r:
                        continue
                i = (y * n + x) * 4
                px[i:i + 4] = bytes(rgba)

    pin, body, accent, notch = (176, 184, 196, 255), (38, 43, 54, 255), (59, 130, 246, 255), (14, 17, 23, 255)
    for k in range(5):                              # pins, both sides
        y = 12 + k * 9
        rect(4, y, 16, y + 5, pin, 1)
        rect(48, y, 60, y + 5, pin, 1)
    rect(12, 6, 52, 58, body, 5)                    # package
    rect(28, 6, 36, 10, notch, 3)                   # notch
    rect(20, 22, 44, 26, accent, 1)                 # "logic" inside
    rect(20, 30, 38, 34, accent, 1)
    rect(20, 38, 44, 42, accent, 1)
    rect(17, 49, 21, 53, (169, 176, 191, 255), 2)   # pin-1 dot
    return bytes(px)


def png(n: int) -> bytes:
    raw = draw(n)
    rows = b"".join(b"\x00" + raw[y * n * 4:(y + 1) * n * 4] for y in range(n))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + \
            struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def ico(sizes) -> bytes:
    images = [png(n) for n in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    off = 6 + 16 * len(images)
    dirs = b""
    for n, data in zip(sizes, images):
        dirs += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), off)
        off += len(data)
    return head + dirs + b"".join(images)


if __name__ == "__main__":
    (HERE / "icon.png").write_bytes(png(256))
    (HERE / "icon.ico").write_bytes(ico([16, 24, 32, 48, 64, 128, 256]))
    print("wrote", HERE / "icon.png", "and", HERE / "icon.ico")
