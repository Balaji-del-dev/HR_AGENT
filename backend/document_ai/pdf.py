"""Render plain text lines as a simple PDF (demo data and tests)."""

from collections.abc import Iterable

import pymupdf


def make_pdf(lines: Iterable[str], *, hidden: Iterable[str] = (), tiny: Iterable[str] = ()) -> bytes:
    """One page per 40 lines. ``hidden`` lines are white text and ``tiny`` lines use a 2pt font,
    the two tricks the sanitizer must strip."""
    document = pymupdf.open()  # type: ignore[no-untyped-call]
    page, y = document.new_page(), 60
    for line in lines:
        if y > 780:
            page, y = document.new_page(), 60
        page.insert_text((50, y), line, fontsize=11)
        y += 18
    for line in hidden:
        page.insert_text((50, y), line, fontsize=11, color=(1, 1, 1))
        y += 18
    for line in tiny:
        page.insert_text((50, y), line, fontsize=2)
        y += 6
    data: bytes = document.tobytes()  # type: ignore[no-untyped-call]
    document.close()  # type: ignore[no-untyped-call]
    return data
