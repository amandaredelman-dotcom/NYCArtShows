"""Build the website and the Sunday email from the scan plus the Sunday review.

Inputs
  data/shows.json        what the scanner found (Saturday night / Sunday morning)
  data/labels.json       Sunday review: genres, fixes and notes per show id
  data/web_shows.json    Sunday review: shows found on the web for venues the scanner couldn't read
  data/permanent.json    "Always on view" collections
  data/published.json    show ids already announced in earlier emails (to spot what's new)
  venues.yaml, site/config.yaml, scanner/taxonomy.py

Outputs
  web/index.html         the page to publish
  site/email.html        the Sunday email (HTML)    site/email.txt (plain-text version)
  data/review_queue.json shows that still need genres or a date check

Usage:  python web/build.py            (preview)
        python web/build.py --final    (also records this week's shows as announced)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scanner.taxonomy import FAMILIES  # noqa: E402

DATA, SITE = ROOT / "data", ROOT / "web"


def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def presets(cfg: dict) -> dict:
    p = {"Everything": []}
    for name in ("Old Masters", "18th–19th century", "Modern", "Contemporary", "Photography"):
        p[name] = FAMILIES[name]
    p.update(cfg.get("presets", {}))
    return p


def assemble(today: dt.date) -> tuple[list[dict], dict]:
    venues = {v["id"]: v for v in yaml.safe_load((ROOT / "venues.yaml").read_text())}
    scan = load(DATA / "shows.json", {"shows": []})
    labels = load(DATA / "labels.json", {})
    web = load(DATA / "web_shows.json", [])
    out, queue = [], []

    def venue_bits(vid: str, fallback: dict) -> dict:
        v = {**fallback, **venues.get(vid, {})}
        return {"venue": v.get("name", ""), "type": v.get("type", ""), "area": v.get("area", ""),
                "hood": v.get("neighborhood", ""), "address": v.get("address", ""), "subway": v.get("subway", "—"),
                "admission": v.get("admission", "See venue"), "free": bool(v.get("free")),
                "hours": v.get("hours", "See venue"), "access": v.get("access", "Check with venue")}

    for s in scan.get("shows", []) + web:
        sid = s.get("id") or f"{s['venue_id']}--{s.get('key', '')}"
        lab = labels.get(sid, {})
        if lab.get("hide"):
            continue
        start = lab.get("start_date", s.get("start_date"))
        end = lab.get("end_date", s.get("end_date"))
        if end and end < today.isoformat():
            continue
        show = {
            "id": sid, "title": lab.get("title", s["title"]),
            **venue_bits(s["venue_id"], {"name": (s.get("venue") or {}).get("name", "")} if isinstance(s.get("venue"), dict) else {}),
            "start": start, "end": end, "through": bool(end and not start),
            "tba": lab.get("tba") or s.get("tba"), "ongoing": lab.get("ongoing", False),
            "genres": lab.get("genres", s.get("genres", [])), "media": lab.get("media", s.get("media", [])),
            "related": [{"g": r["genre"], "note": r["note"]} for r in lab.get("related", s.get("related", []))],
            "blurb": lab.get("blurb") or s.get("summary") or "",
            "reception": lab.get("reception", "—"),
            "url": lab.get("url", s.get("url")),
            "source": s.get("source", "scan"),
        }
        for k in ("hours", "access", "admission"):
            if lab.get(k):
                show[k] = lab[k]
        out.append(show)
        needs_date = (s.get("needs_check") and sid not in labels) or (not start and not end and not show["tba"])
        if not show["genres"] or needs_date or s.get("stale"):
            queue.append({"id": sid, "title": show["title"], "venue": show["venue"], "url": show["url"],
                          "needs": [n for n, bad in (("genres", not show["genres"]),
                                                      ("dates", needs_date),
                                                      ("recheck: venue unreachable", s.get("stale"))) if bad]})
    meta = {"venue_count": len({s["venue"] for s in out}),
            "web_checked": len({w["venue_id"] for w in web}),
            "unreachable": scan.get("unreachable", [])}
    (DATA / "review_queue.json").write_text(json.dumps(queue, indent=1, ensure_ascii=False))
    return out, meta


def cal_link(s: dict, today: dt.date) -> str:
    day = max(today, dt.date.fromisoformat(s["start"])) if s.get("start") else today
    while day.weekday() != 5:
        day += dt.timedelta(days=1)
    if s.get("end") and day > dt.date.fromisoformat(s["end"]):
        day = max(today, dt.date.fromisoformat(s["start"])) if s.get("start") else today
    ymd = day.strftime("%Y%m%d")
    details = (f"{s['title']}\n{s['venue']}\n"
               f"{'On view through ' + fmt(s['end']) if s.get('end') else 'Check dates on the venue page'}\n"
               f"Hours: {s['hours']}\nAdmission: {s['admission']}\nSubway: {s['subway']}\n{s['url']}")
    q = {"action": "TEMPLATE", "text": f"Art: {s['title']}", "dates": f"{ymd}T110000/{ymd}T130000",
         "ctz": "America/New_York", "details": details, "location": f"{s['venue']}, {s['address']}"}
    return "https://calendar.google.com/calendar/render?" + urlencode(q)


def fmt(iso: str | None) -> str:
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def build_page(shows, meta, cfg, today):
    tpl = (SITE / "template.html").read_text()
    js = lambda x: json.dumps(x, ensure_ascii=False).replace("</", "<\\/")  # noqa: E731
    page = (tpl.replace("__AS_OF__", today.isoformat()).replace("__FAMILIES__", js(FAMILIES))
               .replace("__PRESETS__", js(presets(cfg))).replace("__SHOWS__", js(shows))
               .replace("__PERMANENT__", js(load(DATA / "permanent.json", []))).replace("__META__", js(meta)))
    (SITE / "index.html").write_text(page)


def build_email(shows, meta, cfg, today, published):
    e = html.escape
    soon = today + dt.timedelta(days=14)
    week = today + dt.timedelta(days=7)
    pick_genres = set(cfg.get("presets", {}).get(cfg.get("email_picks_preset", ""), []))
    is_pick = lambda s: bool(pick_genres & set(s["genres"]) or pick_genres & {r["g"] for r in s["related"]})  # noqa: E731
    opening = [s for s in shows if s.get("start") and today < dt.date.fromisoformat(s["start"]) <= week]
    closing = [s for s in shows if s.get("end") and today <= dt.date.fromisoformat(s["end"]) <= soon]
    new = [s for s in shows if s["id"] not in published and s not in opening]
    horizon = [s for s in shows if s["type"] in ("Art fair", "Auction house") and
               (s.get("tba") or (s.get("start") and dt.date.fromisoformat(s["start"]) <= today + dt.timedelta(days=60)))]
    picks = [s for s in shows if is_pick(s) and (s in opening or s in closing or s in new)]

    def item(s, note=""):
        dates = (f"Through {fmt(s['end'])}" if s.get("end") and not s.get("start") else
                 f"{fmt(s['start'])} – {fmt(s['end'])}" if s.get("start") and s.get("end") else
                 f"Opens {fmt(s['start'])}" if s.get("start") else s.get("tba") or "Dates on venue site")
        tags = " · ".join(s["genres"][:3])
        btn = ("" if s.get("tba") else
               f'<a href="{e(cal_link(s, today))}" style="display:inline-block;background:#cfa860;color:#1a140a;'
               f'text-decoration:none;font-weight:600;padding:6px 12px;border-radius:6px;margin-right:8px">I&rsquo;m in</a>')
        return (f'<tr><td style="padding:14px 0;border-bottom:1px solid #3a3340">'
                f'<div style="font-family:Georgia,serif;font-size:19px;color:#efe8dd">{e(s["title"])}</div>'
                f'<div style="color:#a69c94;font-size:13px;margin:2px 0 6px">{e(s["venue"])} · {e(s["hood"])} · {e(dates)}'
                f'{(" · " + e(note)) if note else ""}</div>'
                f'<div style="color:#cfa860;font-size:12px;margin-bottom:6px">{e(tags)}</div>'
                f'<div style="color:#d8d0c5;font-size:14px;margin-bottom:8px">{e(s["blurb"][:220])}</div>'
                f'{btn}<a href="{e(s["url"])}" style="color:#cfa860;font-size:13px">Venue page</a></td></tr>')

    def section(title, items, note_fn=lambda s: ""):
        if not items:
            return ""
        rows = "".join(item(s, note_fn(s)) for s in items[:12])
        return (f'<h2 style="font-family:Georgia,serif;color:#cfa860;font-weight:normal;font-size:24px;margin:28px 0 4px">'
                f'{e(title)}</h2><table width="100%" cellpadding="0" cellspacing="0">{rows}</table>')

    site_url = cfg.get("site_url", "")
    body = (
        '<div style="background:#110e13;padding:24px;font-family:Helvetica,Arial,sans-serif">'
        '<div style="max-width:640px;margin:0 auto">'
        f'<div style="color:#cfa860;font-size:12px;letter-spacing:.14em;text-transform:uppercase">On View New York · {fmt(today.isoformat())}</div>'
        f'<h1 style="font-family:Georgia,serif;color:#efe8dd;font-weight:normal;font-size:34px;margin:6px 0">This week in art</h1>'
        f'<p style="color:#a69c94;font-size:14px">{len(shows)} exhibitions on the site. Tap <b style="color:#efe8dd">I&rsquo;m in</b> '
        'to open a calendar hold you can adjust before saving. '
        + (f'<a href="{e(site_url)}" style="color:#cfa860">Open the full site</a>.' if site_url else "") + "</p>"
        + section("Picks for you", picks)
        + section("Opening this week", opening)
        + section("Closing within two weeks", sorted(closing, key=lambda s: s["end"]))
        + section("New on the site", [s for s in new if s not in picks])
        + section("On the horizon", horizon)
        + f'<p style="color:#6f6770;font-size:12px;margin-top:30px">Scanner health: '
        f'{len(meta["unreachable"])} venue(s) couldn&rsquo;t be read automatically this week'
        f'{"; " + str(meta["web_checked"]) + " checked by hand on the web" if meta["web_checked"] else ""}.</p>'
        "</div></div>"
    )
    (SITE / "email.html").write_text(body)
    txt = [f"On View New York · {fmt(today.isoformat())}", ""]
    for title, items in (("Picks for you", picks), ("Opening this week", opening), ("Closing within two weeks", closing),
                         ("New on the site", [s for s in new if s not in picks]), ("On the horizon", horizon)):
        if items:
            txt += [title.upper()] + [f"- {s['title']} ({s['venue']})  I'm in: {cal_link(s, today)}" for s in items[:12]] + [""]
    (SITE / "email.txt").write_text("\n".join(txt))
    return {"picks": len(picks), "opening": len(opening), "closing": len(closing), "new": len(new), "horizon": len(horizon)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--today")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    cfg = yaml.safe_load((SITE / "config.yaml").read_text())
    shows, meta = assemble(today)
    build_page(shows, meta, cfg, today)
    published = set(load(DATA / "published.json", []))
    counts = build_email(shows, meta, cfg, today, published)
    if args.final:
        (DATA / "published.json").write_text(json.dumps(sorted(published | {s["id"] for s in shows}), indent=0))
    queue = load(DATA / "review_queue.json", [])
    print(json.dumps({"shows": len(shows), **meta, "email": counts, "review_queue": len(queue)}, indent=1))


if __name__ == "__main__":
    main()
