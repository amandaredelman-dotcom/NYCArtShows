"""The AI model's one job: read the shows listed on a venue's page. Genres are assigned in the Sunday review."""
from __future__ import annotations

from .llm import ask_json

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
                    "dates_as_written": {"type": "string", "description": "copied character for character from the page"},
                    "url": {"type": ["string", "null"]},
                    "summary": {"type": "string"},
                },
                "required": ["title", "dates_as_written", "url", "summary"],
            },
        }
    },
    "required": ["exhibitions"],
}

EXTRACT_SYSTEM = (
    "You read art venue web pages and list the exhibitions they announce. "
    "Only list art exhibitions that are current or upcoming at THIS venue in New York. "
    "Skip past shows, events, talks, tours, shop items, online-only content, and shows at other locations. "
    "For dates, copy the exact words the page uses for that show (for example 'October 15, 2026–January 18, 2027' "
    "or 'Through Feb 8'); copy them character for character and leave the field empty if the page gives none. "
    "Write a one-sentence neutral summary in your own words. Use the link from the page for url."
)


def extract_shows(page_text: str, venue_name: str, today: str) -> list[dict]:
    user = f"Venue: {venue_name}\nToday: {today}\n\nPAGE:\n{page_text}"
    out = ask_json(EXTRACT_SYSTEM, user, EXTRACT_SCHEMA)
    return out.get("exhibitions", [])
