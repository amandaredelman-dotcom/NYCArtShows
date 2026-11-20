"""Weekly scan: visit every venue, read its shows, label them, and write data/shows.json + data/health.json.

Usage:  python -m scanner.run [--only met,frick] [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml

from .ai import classify_show, extract_shows
from .fetch import FetchError, fetch_html, fetch_rendered
from .llm import MODEL
from .pagetext import readable_text, structured_events

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def log(msg: str) -> None:
    print(msg, flush=True)


def clean_date(value) -> str | None:
    if not value or not isinstance(value, str) or not ISO.match(value.strip()):
        return None
    try:
        dt.date.fromisoformat(value.strip())
        return value.strip()
    except ValueError:
        return None


def key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]


def scan_venue(venue: dict, today: str, force: bool) -> tuple[list[dict], dict]:
    cache_file = CACHE / f"{venue['id']}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    old_labels = {s["key"]: s for s in cache.get("shows", [])}
    health = {"venue": venue["name"], "id": venue["id"], "status": "ok", "notes": [], "shows": 0, "changed": False}

    pages = []
    for url in venue["urls"]:
        try:
            html = fetch_html(url)
            text = readable_text(html, url)
            events = structured_events(html, url)
            if len(text) < 800 and not events:
                health["notes"].append(f"{url}: little text, retried in browser")
                html = fetch_rendered(url)
                text = readable_text(html, url)
                events = structured_events(html, url)
            pages.append((url, text, events))
        except FetchError as e:
            health["notes"].append(f"{url}: {e}")

    if not pages:
        health["status"] = "unreachable"
        # Keep last week's shows that haven't closed, so one bad week doesn't empty the venue.
        kept = [s for s in cache.get("shows", []) if not s.get("end_date") or s["end_date"] >= today]
        for s in kept:
            s["stale"] = True
        health["shows"] = len(kept)
        return kept, health

    fingerprint = hashlib.sha256("".join(t for _, t, _ in pages).encode()).hexdigest()
    if not force and cache.get("fingerprint") == fingerprint:
        kept = [s for s in cache.get("shows", []) if not s.get("end_date") or s["end_date"] >= today]
        health["shows"] = len(kept)
        health["notes"].append("page unchanged since last scan; reused results")
        return kept, health

    health["changed"] = True
    raw = []
    for url, text, events in pages:
        if events:
            raw.extend({**e, "artists": [], "summary": e.get("description", ""), "dates_as_written": "", "source": "structured"} for e in events)
        else:
            try:
                t0 = time.time()
                found = extract_shows(text, venue["name"], today)
                log(f"    AI read {url} in {time.time() - t0:.0f}s: {len(found)} shows")
                raw.extend({**f, "source": "ai"} for f in found)
            except Exception as e:  # noqa: BLE001
                health["notes"].append(f"{url}: AI could not read page ({type(e).__name__})")
                health["status"] = "ai_error"

    shows, seen = [], set()
    for r in raw:
        title = (r.get("title") or "").strip()
        if not title or key(title) in seen:
            continue
        seen.add(key(title))
        start, end = clean_date(r.get("start_date")), clean_date(r.get("end_date"))
        if end and end < today:
            continue  # already closed
        show = {
            "key": key(title),
            "title": title,
            "artists": r.get("artists") or [],
            "start_date": start,
            "end_date": end,
            "dates_as_written": r.get("dates_as_written") or "",
            "summary": (r.get("summary") or "").strip(),
            "url": r.get("url") or venue["urls"][0],
            "source": r.get("source"),
            "dates_unclear": not (start or end),
        }
        prev = old_labels.get(show["key"])
        if prev and prev.get("genres") and not force:
            show.update({k: prev[k] for k in ("genres", "media", "related", "confident") if k in prev})
        else:
            try:
                show.update(classify_show(show, venue["name"]))
            except Exception as e:  # noqa: BLE001
                show.update({"genres": [], "media": [], "related": [], "confident": False})
                health["notes"].append(f"{title}: labeling failed ({type(e).__name__})")
        shows.append(show)

    if not shows:
        health["status"] = "no_shows_found" if health["status"] == "ok" else health["status"]
    health["shows"] = len(shows)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"fingerprint": fingerprint, "checked": today, "shows": shows}, indent=1))
    return shows, health


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated venue ids")
    ap.add_argument("--force", action="store_true", help="re-read every page even if unchanged")
    args = ap.parse_args()

    venues = yaml.safe_load((ROOT / "venues.yaml").read_text())
    if args.only:
        wanted = set(args.only.split(","))
        venues = [v for v in venues if v["id"] in wanted]
    today = dt.date.today().isoformat()
    started = time.time()

    all_shows, health = [], []
    for i, v in enumerate(venues, 1):
        log(f"[{i}/{len(venues)}] {v['name']}")
        try:
            shows, h = scan_venue(v, today, args.force)
        except Exception as e:  # noqa: BLE001  (one broken venue never stops the scan)
            shows, h = [], {"venue": v["name"], "id": v["id"], "status": "error", "notes": [repr(e)[:200]], "shows": 0}
        log(f"    -> {h['status']}, {h['shows']} shows")
        venue_facts = {k: v.get(k) for k in ("name", "type", "area", "neighborhood", "address", "subway", "admission", "free")}
        for s in shows:
            all_shows.append({**s, "id": f"{v['id']}--{s['key']}", "venue_id": v["id"], "venue": venue_facts})
        health.append(h)

    DATA.mkdir(exist_ok=True)
    meta = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "model": MODEL,
            "venues_scanned": len(venues), "show_count": len(all_shows),
            "needs_review": sum(1 for s in all_shows if not s.get("confident", True) or s.get("dates_unclear")),
            "minutes": round((time.time() - started) / 60, 1)}
    (DATA / "shows.json").write_text(json.dumps({**meta, "shows": all_shows}, indent=1, ensure_ascii=False))
    (DATA / "health.json").write_text(json.dumps({**meta, "venues": health}, indent=1, ensure_ascii=False))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = [f"## Scan {today}", f"{meta['show_count']} shows from {len(venues)} venues in {meta['minutes']} min "
                 f"({meta['needs_review']} flagged for review).", "", "| Venue | Status | Shows | Notes |", "|---|---|---|---|"]
        lines += [f"| {h['venue']} | {h['status']} | {h['shows']} | {'; '.join(h['notes'])[:200]} |" for h in health]
        Path(summary).write_text("\n".join(lines) + "\n")
    log(f"Done: {meta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
