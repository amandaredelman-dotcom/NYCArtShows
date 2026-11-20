"""The two jobs the AI model does: read shows off a page, and label each show's genres."""
from __future__ import annotations

from .llm import ask_json
from .taxonomy import GENRES, MEDIA, guide_text

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "exhibitions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "artists": {"type": "array", "items": {"type": "string"}},
                    "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "end_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "dates_as_written": {"type": "string"},
                    "url": {"type": ["string", "null"]},
                    "summary": {"type": "string"},
                },
                "required": ["title", "start_date", "end_date", "dates_as_written", "url", "summary"],
            },
        }
    },
    "required": ["exhibitions"],
}

EXTRACT_SYSTEM = (
    "You read art venue web pages and list the exhibitions they announce. "
    "Only list art exhibitions that are current or upcoming at THIS venue in New York. "
    "Skip past shows, events, talks, tours, shop items, online-only content, and shows at other locations. "
    "Never invent a date: copy the dates as written, and give YYYY-MM-DD only when the page states them. "
    "If a year is missing, assume the nearest future year relative to {today}. "
    "Write a one-sentence neutral summary in your own words. Use the link from the page for url."
)


def extract_shows(page_text: str, venue_name: str, today: str) -> list[dict]:
    user = f"Venue: {venue_name}\nToday: {today}\n\nPAGE:\n{page_text}"
    out = ask_json(EXTRACT_SYSTEM.format(today=today), user, EXTRACT_SCHEMA)
    return out.get("exhibitions", [])


CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "genres": {"type": "array", "items": {"type": "string", "enum": GENRES}},
        "media": {"type": "array", "items": {"type": "string", "enum": MEDIA}},
        "related": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"genre": {"type": "string", "enum": GENRES}, "note": {"type": "string"}},
                "required": ["genre", "note"],
            },
        },
        "confident": {"type": "boolean"},
    },
    "required": ["genres", "media", "related", "confident"],
}

CLASSIFY_SYSTEM = "You are an art historian labeling exhibitions for a public listings site.\n\n" + guide_text()


def classify_show(show: dict, venue_name: str) -> dict:
    user = (
        f"Exhibition: {show['title']}\nVenue: {venue_name}\n"
        f"Artists: {', '.join(show.get('artists') or []) or 'not stated'}\n"
        f"About: {show.get('summary') or show.get('description') or ''}"
    )
    out = ask_json(CLASSIFY_SYSTEM, user, CLASSIFY_SCHEMA)
    # Belt and braces: keep only known labels, cap counts.
    out["genres"] = [g for g in out.get("genres", []) if g in GENRES][:4]
    out["media"] = [m for m in out.get("media", []) if m in MEDIA][:4]
    out["related"] = [r for r in out.get("related", []) if r.get("genre") in GENRES and r["genre"] not in out["genres"]][:2]
    if not out["genres"]:
        out["confident"] = False
    return out
