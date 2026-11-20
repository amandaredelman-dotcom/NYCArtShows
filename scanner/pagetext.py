"""Turn an exhibitions page into compact text the model can read, and pull any structured event data."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

DROP = ["script", "style", "noscript", "svg", "iframe", "form", "header", "footer", "nav", "aside"]
MAX_CHARS = 14_000


def structured_events(html: str, base_url: str) -> list[dict]:
    """Exhibition data some sites publish for search engines (schema.org JSON-LD). Free and exact when present."""
    soup = BeautifulSoup(html, "lxml")
    found = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "@graph" in item:
                    stack.extend(item["@graph"] if isinstance(item["@graph"], list) else [item["@graph"]])
                kind = item.get("@type")
                kinds = kind if isinstance(kind, list) else [kind]
                if any(k in ("ExhibitionEvent", "Event", "VisualArtsEvent") for k in kinds) and item.get("name"):
                    found.append({
                        "title": str(item.get("name")).strip(),
                        "start_date": (item.get("startDate") or "")[:10] or None,
                        "end_date": (item.get("endDate") or "")[:10] or None,
                        "url": urljoin(base_url, item.get("url") or base_url),
                        "description": (item.get("description") or "")[:600],
                    })
            elif isinstance(item, list):
                stack.extend(item)
    return found


def readable_text(html: str, base_url: str) -> str:
    """Main page text with links kept as [text](url), trimmed to fit the model."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(DROP):
        t.decompose()
    main = soup.find("main") or soup.body or soup
    for a in main.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label:
            a.replace_with(f"[{label}]({urljoin(base_url, a['href'])})")
    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text[:MAX_CHARS]
