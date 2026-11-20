"""Combine the parallel batches into data/shows.json and data/health.json, and write the run summary."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from .llm import MODEL

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main() -> None:
    parts = sorted((DATA / "parts").glob("part-*.json"))
    shows, health, minutes = [], [], 0.0
    for p in parts:
        d = json.loads(p.read_text())
        shows += d["shows"]
        health += d["health"]
        minutes = max(minutes, d.get("minutes", 0))
    shows.sort(key=lambda s: (s["venue"]["name"], s["title"]))
    meta = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "model": MODEL,
        "venues_scanned": len(health),
        "show_count": len(shows),
        "unreachable": [h["id"] for h in health if h["status"] in ("unreachable", "error", "ai_error", "no_shows_found")],
        "needs_check": sum(1 for s in shows if s.get("needs_check") or s.get("stale")),
        "minutes": minutes,
    }
    (DATA / "shows.json").write_text(json.dumps({**meta, "shows": shows}, indent=1, ensure_ascii=False))
    (DATA / "health.json").write_text(json.dumps({**meta, "venues": health}, indent=1, ensure_ascii=False))
    for p in parts:
        p.unlink()
    (DATA / "cache").mkdir(exist_ok=True)
    for c in (DATA / "parts" / "cache").glob("*.json"):
        c.replace(DATA / "cache" / c.name)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = [f"## Scan {dt.date.today()}",
                 f"{meta['show_count']} shows from {meta['venues_scanned']} venues; longest batch {minutes} min. "
                 f"{len(meta['unreachable'])} venues need a web check on Sunday.", "",
                 "| Venue | Status | Shows | Notes |", "|---|---|---|---|"]
        lines += [f"| {h['venue']} | {h['status']} | {h['shows']} | {'; '.join(h['notes'])[:220]} |"
                  for h in sorted(health, key=lambda h: h['status'] == 'ok')]
        Path(summary).write_text("\n".join(lines) + "\n")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
