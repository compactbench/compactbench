"""Share images for the site (1200x630), drawn with the site's own fonts and palette.

    python scripts/og_images.py            # the site-wide image, web/public/og.png

``web/public/og.png`` is committed. Per-method images (``method_image``) are drawn by
``scripts/export_site_data.py`` at build time into ``web/public/og/methods/`` (ignored
by git). Needs Pillow and web/node_modules (the Inter and JetBrains Mono font files).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "web" / "node_modules" / "@fontsource-variable"
SITE_IMAGE = ROOT / "web" / "public" / "og.png"

W, H, S = 1200, 630, 2  # S: supersampling factor
BG = (5, 6, 11)
TEXT = (230, 234, 242)
MUTED = (138, 147, 166)
GRID = (16, 20, 34)
CYAN, BLUE, VIOLET = (34, 211, 238), (59, 130, 246), (139, 92, 246)
RGB = tuple[int, int, int]
Point = tuple[float, float]


def fonts_available() -> bool:
    return (FONTS / "inter").is_dir() and (FONTS / "jetbrains-mono").is_dir()


def font(name: str, size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(
        str(FONTS / name / "files" / f"{name}-latin-wght-normal.woff2"), size * S
    )
    f.set_variation_by_axes([weight])
    return f


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def gradient(t: float) -> RGB:
    return mix(CYAN, BLUE, t * 2) if t < 0.5 else mix(BLUE, VIOLET, (t - 0.5) * 2)


def bezier(p0: Point, p1: Point, p2: Point, p3: Point, n: int = 60) -> Iterator[Point]:
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        yield (
            u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
        )


def canvas() -> Image.Image:
    """The shared background: deep black, soft blue and violet glows, a faint grid."""
    img = Image.new("RGB", (W * S, H * S), BG)
    glow = Image.new("RGB", img.size, BG)
    g = ImageDraw.Draw(glow)
    g.ellipse([700 * S, -260 * S, 1400 * S, 300 * S], fill=mix(BG, BLUE, 0.28))
    g.ellipse([-300 * S, 420 * S, 500 * S, 900 * S], fill=mix(BG, VIOLET, 0.20))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(140 * S)), 1.0)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 60):
        d.line([(x * S, 0), (x * S, H * S)], fill=GRID, width=S)
    for y in range(0, H, 60):
        d.line([(0, y * S), (W * S, y * S)], fill=GRID, width=S)
    return img


def gradient_text(img: Image.Image, at: Point, text: str, face: ImageFont.FreeTypeFont) -> None:
    """Draw ``text`` filled with the cyan-blue-violet gradient."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(at, text, font=face, fill=255)
    box = mask.getbbox() or (0, 0, 1, 1)
    ramp = Image.new("RGB", img.size, BG)
    rd = ImageDraw.Draw(ramp)
    for x in range(box[0], box[2] + 1):
        rd.line([(x, box[1]), (x, box[3])], fill=gradient((x - box[0]) / max(1, box[2] - box[0])))
    img.paste(ramp, (0, 0), mask)


def curve(img: Image.Image, pts: Sequence[Point], floor_y: float, *, width: int = 6) -> None:
    """A gradient line through ``pts`` (canvas coordinates) with a fading area under it."""
    fade = Image.new("L", img.size, 0)
    fd = ImageDraw.Draw(fade)
    top = min(p[1] for p in pts)
    for y in range(int(top), int(floor_y) + 1):
        fd.line(
            [(0, y), (W * S, y)], fill=round(255 * 0.30 * (1 - (y - top) / max(1, floor_y - top)))
        )
    area = Image.new("L", img.size, 0)
    ImageDraw.Draw(area).polygon([*pts, (pts[-1][0], floor_y), (pts[0][0], floor_y)], fill=255)
    img.paste(Image.new("RGB", img.size, BLUE), (0, 0), ImageChops.multiply(fade, area))
    d = ImageDraw.Draw(img)
    for i in range(len(pts) - 1):
        d.line(
            [pts[i], pts[i + 1]],
            fill=gradient(i / max(1, len(pts) - 2)),
            width=width * S,
            joint="curve",
        )


def save(img: Image.Image, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    img.resize((W, H), Image.Resampling.LANCZOS).save(out, optimize=True)


def site_image(out: Path = SITE_IMAGE) -> None:
    img = canvas()
    d = ImageDraw.Draw(img)
    x0 = 72
    d.text(
        (x0 * S, 84 * S),
        "CONTEXT COMPACTION BENCHMARK",
        font=font("jetbrains-mono", 20, 600),
        fill=CYAN,
    )
    d.text((x0 * S, 124 * S), "CompactBench", font=font("inter", 88, 800), fill=TEXT)
    head = font("inter", 44, 650)
    d.text((x0 * S, 262 * S), "How much does your agent", font=head, fill=TEXT)
    left = (x0 * S, 318 * S)
    gradient_text(img, left, "forget", head)
    d.text(
        (left[0] + d.textlength("forget ", font=head), left[1]),
        "when it compacts?",
        font=head,
        fill=TEXT,
    )
    d.text(
        (x0 * S, 420 * S),
        "8 failure families · hidden Elite set · any model",
        font=font("inter", 24, 450),
        fill=MUTED,
    )
    d.text((x0 * S, 540 * S), "compactbench.com", font=font("jetbrains-mono", 26, 500), fill=TEXT)

    # Decay curve, from the home page hero (600x260 viewBox) into the right column.
    rx, ry, rw, rh = 700, 250, 440, 230

    def at(p: Point) -> Point:
        return ((rx + p[0] / 600 * rw) * S, (ry + p[1] / 260 * rh) * S)

    line = [
        *bezier((0, 40), (90, 48), (140, 84), (240, 118)),
        *bezier((240, 118), (340, 152), (420, 176), (600, 206)),
    ]
    kept = [
        *bezier((0, 40), (120, 42), (240, 46), (360, 50)),
        *bezier((360, 50), (480, 54), (520, 56), (600, 58)),
    ]
    pts = [at(p) for p in kept]
    for i in range(0, len(pts) - 1, 4):  # dashed: what a perfect memory keeps
        d.line([pts[i], pts[min(i + 2, len(pts) - 1)]], fill=(39, 48, 73), width=3 * S)
    curve(img, [at(p) for p in line], at((0, 260))[1])
    d = ImageDraw.Draw(img)
    for p in [(0, 40), (120, 66), (240, 118), (360, 152), (480, 182)]:
        cx, cy = at(p)
        r = 8 * S
        d.ellipse(
            [cx - r, cy - r, cx + r, cy + r], fill=BG, outline=gradient(p[0] / 600), width=3 * S
        )
    d.text(
        (rx * S, (ry + rh + 22) * S),
        "compaction 1 · 2 · 3 · 4 · 5",  # the latin font subset has no arrows
        font=font("jetbrains-mono", 18, 500),
        fill=MUTED,
    )
    save(img, out)


def _fit(
    d: ImageDraw.ImageDraw, text: str, name: str, weight: int, size: int, width: int
) -> ImageFont.FreeTypeFont:
    """The largest font size (down to half of ``size``) at which ``text`` fits ``width``."""
    for s in range(size, size // 2, -2):
        face = font(name, s, weight)
        if d.textlength(text, font=face) <= width * S:
            return face
    return font(name, size // 2, weight)


def method_image(row: Mapping[str, Any], out: Path) -> None:
    """A leaderboard row's card: method, model, score with its interval, score by compaction."""
    img = canvas()
    d = ImageDraw.Draw(img)
    x0 = 72
    kind = {"submission": "RANKED SUBMISSION", "baseline": "BASELINE", "control": "CONTROL"}.get(
        str(row.get("row_kind")), ""
    )
    season = f"SEASON {str(row['season']).upper().removeprefix('S')}" if row.get("season") else ""
    eyebrow = " · ".join(x for x in ("COMPACTBENCH", season, kind) if x)
    d.text((x0 * S, 72 * S), eyebrow, font=font("jetbrains-mono", 20, 600), fill=CYAN)
    name = f"{row['method_name']} {row['method_version']}"
    d.text((x0 * S, 110 * S), name, font=_fit(d, name, "inter", 800, 76, 1056), fill=TEXT)
    model = str(row.get("model_label") or row["compactor_model"])
    who = f"  ·  @{row['handle']}" if row.get("handle") else ""
    d.text(
        (x0 * S, 214 * S),
        f"{model}{who}",
        font=_fit(d, model + who, "inter", 500, 30, 1056),
        fill=MUTED,
    )

    gradient_text(
        img, (x0 * S, 300 * S), f"{float(row['score']) * 100:.1f}", font("inter", 140, 800)
    )
    mono = font("jetbrains-mono", 22, 500)
    d.text((x0 * S, 470 * S), "SCORE", font=mono, fill=MUTED)
    low, high = float(row["score_ci_low"]) * 100, float(row["score_ci_high"]) * 100
    d.text((x0 * S, 504 * S), f"95% interval {low:.1f} to {high:.1f}", font=mono, fill=MUTED)
    d.text((x0 * S, 560 * S), "compactbench.com", font=font("jetbrains-mono", 24, 500), fill=TEXT)

    cycles = [float(v) for v in row.get("by_cycle") or []]
    if len(cycles) >= 2:
        rx, ry, rw, rh = 560, 300, 570, 210  # score 1.0 at the top, 0 at the bottom
        pts = [
            ((rx + i / (len(cycles) - 1) * rw) * S, (ry + (1 - v) * rh) * S)
            for i, v in enumerate(cycles)
        ]
        d.line([(rx * S, ry * S), ((rx + rw) * S, ry * S)], fill=(39, 48, 73), width=2 * S)
        curve(img, pts, (ry + rh) * S, width=5)
        d = ImageDraw.Draw(img)
        small = font("jetbrains-mono", 18, 500)
        for i, (p, v) in enumerate(zip(pts, cycles, strict=True)):
            r = 7 * S
            d.ellipse(
                [p[0] - r, p[1] - r, p[0] + r, p[1] + r],
                fill=BG,
                outline=gradient(i / (len(pts) - 1)),
                width=3 * S,
            )
            label = f"{v * 100:.0f}"
            d.text(
                (p[0] - d.textlength(label, font=small) / 2, p[1] - 34 * S),
                label,
                font=small,
                fill=TEXT,
            )
        d.text((rx * S, (ry + rh + 20) * S), "score after each compaction", font=small, fill=MUTED)
    save(img, out)


if __name__ == "__main__":
    site_image()
    print(f"wrote {SITE_IMAGE.relative_to(ROOT)}")
