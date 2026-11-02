"""Generate the SentinelX Desktop application icon (build-time helper)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parents[1]
TARGET = HERE / "assets" / "icon.ico"
BACKGROUND_TOP = (12, 17, 26)
BACKGROUND_BOTTOM = (6, 8, 13)
GOLD = (201, 162, 39)
CREAM = (243, 235, 221)
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\georgiab.ttf"),
    Path(r"C:\Windows\Fonts\timesbd.ttf"),
    Path(r"C:\Windows\Fonts\seguisb.ttf"),
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _hexagon(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    import math

    return [
        (cx + radius * math.cos(math.radians(60 * index - 90)),
         cy + radius * math.sin(math.radians(60 * index - 90)))
        for index in range(6)
    ]


def render(size: int) -> Image.Image:
    scale = 4
    canvas = size * scale
    image = Image.new("RGB", (canvas, canvas), BACKGROUND_BOTTOM)
    draw = ImageDraw.Draw(image)

    # Vertical gradient backdrop.
    for y in range(canvas):
        ratio = y / max(1, canvas - 1)
        color = tuple(
            round(BACKGROUND_TOP[i] + (BACKGROUND_BOTTOM[i] - BACKGROUND_TOP[i]) * ratio)
            for i in range(3)
        )
        draw.line([(0, y), (canvas, y)], fill=color)

    margin = canvas * 0.13
    radius = canvas * 0.085
    draw.rounded_rectangle(
        [margin, margin, canvas - margin, canvas - margin],
        radius=radius,
        outline=(32, 40, 56),
        width=max(1, round(canvas * 0.012)),
    )

    center = canvas / 2
    hex_radius = canvas * 0.27
    draw.polygon(_hexagon(center, center, hex_radius), outline=GOLD, width=max(2, round(canvas * 0.02)))

    font = _font(int(canvas * 0.34))
    label = "S"
    box = draw.textbbox((0, 0), label, font=font)
    draw.text(
        (center - (box[2] - box[0]) / 2 - box[0], center - (box[3] - box[1]) / 2 - box[1]),
        label,
        font=font,
        fill=CREAM,
    )

    # Gold accent underline beneath the mark.
    line_y = canvas * 0.79
    draw.line(
        [(canvas * 0.38, line_y), (canvas * 0.62, line_y)],
        fill=GOLD,
        width=max(2, round(canvas * 0.012)),
    )

    return image.resize((size, size), Image.LANCZOS)


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(size) for size in sizes]
    images[-1].save(
        TARGET,
        format="ICO",
        sizes=[(size, size) for size in sizes],
        append_images=images[:-1],
    )
    print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
