"""Read exhibition dates from text exactly as a venue writes them, in code, so nothing is guessed.

Handles forms like:
  "October 15, 2026–January 18, 2027"   "Nov 19 – Dec 19, 2026"   "Through January 4, 2027"
  "Opens November 5, 2026"   "15 October 2026 – 18 January 2027"   "10/15/2026 - 1/18/2027"
"""
from __future__ import annotations

import datetime as dt
import re

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"

# Month Day[, Year]   |   Day Month [Year]   |   M/D/YYYY
PATTERNS = [
    re.compile(rf"\b{MON}\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?", re.I),
    re.compile(rf"\b(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?\s+{MON}(?:,?\s+(\d{{4}}))?", re.I),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
]


def _mentions(text: str) -> list[tuple[int, int, int | None, int]]:
    """(month, day, year or None, position) for every date in the text, in reading order."""
    found = []
    for i, pat in enumerate(PATTERNS):
        for m in pat.finditer(text):
            if i == 0:
                mon, day, yr = MONTHS[m.group(1)[:3].lower()], int(m.group(2)), m.group(3)
            elif i == 1:
                day, mon, yr = int(m.group(1)), MONTHS[m.group(2)[:3].lower()], m.group(3)
            else:
                mon, day, yr = int(m.group(1)), int(m.group(2)), m.group(3)
            if 1 <= mon <= 12 and 1 <= day <= 31:
                found.append((mon, day, int(yr) if yr else None, m.start(), m.end()))
    found.sort(key=lambda x: x[3])
    # Drop overlaps (a "Day Month" match inside a "Month Day" match etc.)
    out, last_end = [], -1
    for f in found:
        if f[3] >= last_end:
            out.append(f[:4])
            last_end = f[4]
    return out


def _make(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def parse_range(text: str, today: dt.date) -> tuple[str | None, str | None]:
    """Return (start, end) as YYYY-MM-DD, or None for anything the text doesn't state."""
    if not text:
        return None, None
    ms = _mentions(text)
    if not ms:
        return None, None
    lower = text.lower()
    only_end = bool(re.search(r"\b(through|thru|until|till|closes|ends|on view to)\b", lower)) and len(ms) == 1
    only_start = bool(re.search(r"\b(opens|opening|from|starting|beginning)\b", lower)) and len(ms) == 1

    def resolve(mon, day, yr, fallback_year):
        if yr:
            return _make(yr, mon, day)
        return _make(fallback_year, mon, day)

    if len(ms) == 1:
        mon, day, yr, _ = ms[0]
        if yr is None:  # no year at all: nearest sensible year relative to today
            yr = today.year
            d = _make(yr, mon, day)
            if d and only_end and d < today - dt.timedelta(days=60):
                yr += 1
        d = resolve(mon, day, yr, today.year)
        iso = d.isoformat() if d else None
        if only_start:
            return iso, None
        if only_end:
            return None, iso
        return iso, None  # a single bare date is usually an opening

    (m1, d1, y1, _), (m2, d2, y2, _) = ms[0], ms[-1]
    if y2 is None:
        y2 = y1 or today.year
    if y1 is None:
        y1 = y2 if (m1, d1) <= (m2, d2) else y2 - 1  # "Nov 19 – Jan 4, 2027" starts in 2026
    start, end = _make(y1, m1, d1), _make(y2, m2, d2)
    if start and end and start > end:
        start, end = None, end
    return (start.isoformat() if start else None), (end.isoformat() if end else None)


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())
