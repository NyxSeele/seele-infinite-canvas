"""生成内置 .cube LUT 文件到 backend/assets/luts/。"""

from __future__ import annotations

from pathlib import Path

LUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "luts"
SIZE = 33


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _write_cube(path: Path, title: str, transform) -> None:
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {SIZE}"]
    denom = SIZE - 1
    for b in range(SIZE):
        for g in range(SIZE):
            for r in range(SIZE):
                ri, gi, bi = r / denom, g / denom, b / denom
                ro, go, bo = transform(ri, gi, bi)
                lines.append(f"{_clamp(ro):.6f} {_clamp(go):.6f} {_clamp(bo):.6f}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _identity(r: float, g: float, b: float) -> tuple[float, float, float]:
    return r, g, b


def _cool_teal(r: float, g: float, b: float) -> tuple[float, float, float]:
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    shadow = max(0.0, 1.0 - lum * 2.2)
    return r * 0.92 + shadow * 0.02, g * 0.96 + shadow * 0.08, min(1.0, b * 1.05 + shadow * 0.12)


def _warm_orange(r: float, g: float, b: float) -> tuple[float, float, float]:
    return min(1.0, r * 1.08 + 0.03), g * 0.98 + 0.02, b * 0.88


def _natural(r: float, g: float, b: float) -> tuple[float, float, float]:
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    mix = 0.92
    return lum + (r - lum) * mix, lum + (g - lum) * mix, lum + (b - lum) * mix


def _high_contrast(r: float, g: float, b: float) -> tuple[float, float, float]:
    def curve(v: float) -> float:
        return _clamp((v - 0.5) * 1.25 + 0.5)

    return curve(r), curve(g), curve(b)


def _vintage_fade(r: float, g: float, b: float) -> tuple[float, float, float]:
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    fade = 0.88
    shadow = max(0.0, 0.35 - lum)
    return lum * fade + r * 0.12 + shadow * 0.02, lum * fade + g * 0.1 + shadow * 0.06, lum * fade + b * 0.08 + 0.04


PRESETS = [
    ("cool_teal.cube", "Cool Teal", _cool_teal),
    ("warm_orange_film.cube", "Warm Orange Film", _warm_orange),
    ("natural_realistic.cube", "Natural Realistic", _natural),
    ("high_contrast_commercial.cube", "High Contrast Commercial", _high_contrast),
    ("vintage_fade.cube", "Vintage Fade", _vintage_fade),
    ("identity.cube", "Identity", _identity),
]


def main() -> None:
    for filename, title, fn in PRESETS:
        _write_cube(LUT_DIR / filename, title, fn)
        print(f"wrote {LUT_DIR / filename}")


if __name__ == "__main__":
    main()
