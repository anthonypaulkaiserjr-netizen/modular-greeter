import os
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib
from PIL import Image

PALETTE_RGB = [
    (17, 17, 17), (197, 15, 31), (19, 161, 14), (193, 156, 0),
    (0, 55, 218), (136, 23, 152), (58, 150, 221), (204, 204, 204),
    (118, 118, 118), (231, 72, 86), (22, 198, 12), (249, 241, 165),
    (59, 120, 255), (180, 0, 158), (97, 214, 214), (242, 242, 242),
]


def nearest_color(rgb):
    r, g, b = rgb
    return min(
        PALETTE_RGB,
        key=lambda c: (r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2,
    )


class AnsiCanvas(Gtk.Picture):
    def __init__(self, image_path, block_size=18):
        super().__init__()
        self.set_content_fit(Gtk.ContentFit.COVER)
        if not image_path or not os.path.exists(image_path):
            return

        cols = max(32, 1920 // max(4, int(block_size)))
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        rows = max(18, int((h / w) * cols))

        small = img.resize((cols, rows), Image.Resampling.NEAREST)
        px = small.load()
        for y in range(rows):
            for x in range(cols):
                px[x, y] = nearest_color(px[x, y])

        blocky = small.resize((cols * 16, rows * 16), Image.Resampling.NEAREST)
        raw = GLib.Bytes.new(blocky.tobytes())
        texture = Gdk.MemoryTexture.new(
            blocky.width,
            blocky.height,
            Gdk.MemoryFormat.R8G8B8,
            raw,
            blocky.width * 3,
        )
        self.set_paintable(texture)
