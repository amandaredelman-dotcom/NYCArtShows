"""Weekly scan: visit venues, read their shows, and save what was found.

Genres are NOT assigned here; the Sunday review does that.

Usage:
  python -m scanner.run                       # all venues, one job
  python -m scanner.run --shard 0 --of 4      # one of four parallel batches
  python -m scanner.run --only met,frick --force
Then:  python -m scanner.merge                # combine batches into data/shows.json + data/health.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import yaml

from .ai import extract_shows
from .dates import normalize, parse_range
from .fetch import BLOCKED, FetchError, fetch_html, fetch_rendered
from .pagetext import readable_text, structured_events

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
PARTS = DATA / "parts"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def log(msg: str) -> None:
    print(msg, flush=True)


def iso_or_none(value) -> str | None:
    if isinstance(value, str) and ISO.match(value.strip()):
        try:
            return dt.date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            return None
    return None


def key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]


def get_page(url: str, health: dict) -> tuple[str, list[dict]]:
    try:
        html = fetch_html(url)
    except FetchError as e:
        if e.status in BLOCKED:
            health["notes"].append(f"{url}: {e}, retried in browser")
            html = fetch_rendered(url)
        else:
            raise
    text, events = readable_text(html, url), structured_events(html, url)
    if len(text) < 800 and not events:
        health["notes"].append(f"{url}: little text, retried in browser")
        html = fetch_rendered(url)
        text, events = readable_text(html, url), structured_events(html, url)
    return text, events


def scan_venue(venue: dict, today: dt.date, force: bool) -> tuple[list[dict], dict]:
    today_iso = today.isoformat()
    cache_file = CACHE / f"{venue['id']}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    health = {"venue": venue["name"], "id": venue["id"], "status": "ok", "notes": [], "shows": 0, "changed": False}

    pages = []
    for url in venue["urls"]:
        try:
            text, events = get_page(url, health)
            pages.append((url, text, events))
        except FetchError as e:
            health["notes"].append(f"{url}: {e}")

    def still_open(shows):
        return [s for s in shows if not s.get("end_date") or s["end_date"] >= today_iso]

    if not pages:
        health["status"] = "unreachable"
        kept = still_open(cache.get("shows", []))
        for s in kept:
            s["stale"] = True  # last known listing; the Sunday review checks these on the web
        health["shows"] = len(kept)
        return kept, health

    fingerprint = hashlib.sha256("".join(t for _, t, _ in pages).encode()).hexdigest()
    if not force and cache.get("fingerprint") == fingerprint:
        kept = still_open(cache.get("shows", []))
        health["shows"] = len(kept)
        health["notes"].append("page unchanged since last scan; reused results")
        return kept, health

    health["changed"] = True
    raw = []
    for url, text, events in pages:
        page_norm = normalize(text)
        if events:
            for e in events:
                raw.append({**e, "artists": [], "summary": e.get("description", ""), "dates_as_written": "",
                            "source": "structured", "start_date": iso_or_none(e.get("start_date")),
                            "end_date": iso_or_none(e.get("end_date"))})
            continue
        try:
            t0 = time.time()
            found = extract_shows(text, venue["name"], today_iso)
            log(f"    AI read {url} in {time.time() - t0:.0f}s: {len(found)} shows")
        except Exception as e:  # noqa: BLE001
            health["notes"].append(f"{url}: AI could not read page ({type(e).__name__})")
            health["status"] = "ai_error"
            continue
        for f in found:
            written = (f.get("dates_as_written") or "").strip()
            # Only trust date words that really appear on the page; the model can't invent them.
            verified = bool(written) and normalize(written) in page_norm
            start, end = parse_range(written, today)  # unverified dates are kept but flagged for the Sunday check
            title = (f.get("title") or "").strip()
            raw.append({**f, "source": "ai", "start_date": start, "end_date": end,
                        "title_on_page": bool(title) and normalize(title)[:40] in page_norm,
                        "dates_verified": verified})

    shows, seen = [], set()
    for r in raw:
        title = (r.get("title") or "").strip()
        if not title or key(title) in seen:
            continue
        if r.get("source") == "ai" and not r.get("title_on_page"):
            health["notes"].append(f"dropped '{title[:50]}': title not found on page")
            continue
        seen.add(key(title))
        if r.get("end_date") and r["end_date"] < today_iso:
            continue  # already closed
        shows.append({
            "key": key(title),
            "title": title,
            "artists": r.get("artists") or [],
            "start_date": r.get("start_date"),
            "end_date": r.get("end_date"),
            "dates_as_written": r.get("dates_as_written") or "",
            "summary": (r.get("summary") or "").strip(),
            "url": r.get("url") or venue["urls"][0],
            "source": r.get("source"),
            "needs_check": not (r.get("start_date") or r.get("end_date")) or r.get("dates_verified") is False,
        })

    if not shows and health["status"] == "ok":
        health["status"] = "no_shows_found"
    health["shows"] = len(shows)
    out = PARTS / "cache" / f"{venue['id']}.json"  # merge.py moves it into data/cache
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"fingerprint": fingerprint, "checked": today_iso, "shows": shows},
                                     indent=1, ensure_ascii=False))
    return shows, health


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated venue ids")
    ap.add_argument("--force", action="store_true", help="re-read every page even if unchanged")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--of", type=int, default=1)
    args = ap.parse_args()

    venues = yaml.safe_load((ROOT / "venues.yaml").read_text())
    if args.only:
        wanted = {v.strip() for v in args.only.split(",") if v.strip()}
        venues = [v for v in venues if v["id"] in wanted]
    venues = [v for i, v in enumerate(venues) if i % args.of == args.shard]
    today = dt.date.today()
    started = time.time()

    shows_out, health = [], []
    for i, v in enumerate(venues, 1):
        log(f"[{i}/{len(venues)}] {v['name']}")
        try:
            shows, h = scan_venue(v, today, args.force)
        except Exception as e:  # noqa: BLE001  (one broken venue never stops the scan)
            shows, h = [], {"venue": v["name"], "id": v["id"], "status": "error", "notes": [repr(e)[:200]], "shows": 0}
        log(f"    -> {h['status']}, {h['shows']} shows")
        facts = {k: v.get(k) for k in ("name", "type", "area", "neighborhood", "address", "subway", "admission", "free")}
        for s in shows:
            shows_out.append({**s, "id": f"{v['id']}--{s['key']}", "venue_id": v["id"], "venue": facts})
        health.append(h)

    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / f"part-{args.shard}.json").write_text(json.dumps(
        {"shard": args.shard, "minutes": round((time.time() - started) / 60, 1), "shows": shows_out, "health": health},
        indent=1, ensure_ascii=False))
    log(f"Batch {args.shard + 1}/{args.of} done: {len(shows_out)} shows from {len(venues)} venues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
