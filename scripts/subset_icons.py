"""Shrink the Material Symbols icon font to the icons Suraksha AI actually uses.

The full variable font is ~5 MB; the app uses about a hundred icons. Run after adding icons:

    pip install fonttools brotli
    python scripts/subset_icons.py frontend/vendor/fonts/material-symbols-rounded.full.woff2 \
        frontend/vendor/fonts/material-symbols-rounded.woff2

Icon names are collected from frontend/index.html (template ligatures and JS string literals) and
from the API services that send icon names (gamification, readiness, dashboard).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [
    ROOT / "frontend/index.html",
    ROOT / "backend/services/gamification_service.py",
    ROOT / "backend/services/readiness_service.py",
    ROOT / "backend/services/dashboard_service.py",
]


def candidate_names() -> set[str]:
    names: set[str] = set()
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        names |= set(re.findall(r"<i[^>]*>([a-z0-9_]+)</i>", text))
        names |= set(re.findall(r"""['"]([a-z][a-z0-9_]{1,40})['"]""", text))
    return names


def ligature_map(font: TTFont) -> dict[str, str]:
    """ligature text (e.g. 'gpp_bad') -> glyph name."""
    rev = {g: chr(c) for c, g in font.getBestCmap().items()}
    out: dict[str, str] = {}
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            st = getattr(st, "ExtSubTable", st)
            for first, ligs in getattr(st, "ligatures", {}).items():
                for lig in ligs:
                    comps = [first, *lig.Component]
                    if all(c in rev for c in comps):
                        out["".join(rev[c] for c in comps)] = lig.LigGlyph
    return out


def main(src: str, dst: str) -> None:
    font = TTFont(src)
    ligs = ligature_map(font)
    wanted = sorted(n for n in candidate_names() if n in ligs)
    keep = {ligs[n] for n in wanted}
    cmap = font.getBestCmap()
    chars = {c for c in cmap if chr(c).isascii() and (chr(c).isalnum() or chr(c) == "_")}
    keep |= {cmap[c] for c in chars}
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.layout_closure = False  # keep only ligatures whose result glyph we kept
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(glyphs=sorted(keep), unicodes=sorted(chars))
    sub.subset(font)
    font.flavor = "woff2"
    font.save(dst)
    print(f"{len(wanted)} icons kept -> {dst} ({Path(dst).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
