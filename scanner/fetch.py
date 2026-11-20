"""Polite page fetching: robots.txt, a clear user agent, retries, and a browser fallback."""
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = (
    "NYCArtShowsBot/0.1 (weekly exhibition listings; "
    "+https://github.com/amandaredelman-dotcom/NYCArtShows)"
)
TIMEOUT = 30
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}
MIN_GAP_SECONDS = 3.0  # never hit the same site more than once every 3 seconds


class FetchError(Exception):
    pass


def _allowed(url: str) -> bool:
    host = urlparse(url).netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(f"https://{host}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=15)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp = None  # no robots.txt -> allowed
        except requests.RequestException:
            rp = None
        _robots[host] = rp
    rp = _robots[host]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def _wait_turn(url: str) -> None:
    host = urlparse(url).netloc
    gap = time.time() - _last_hit.get(host, 0)
    if gap < MIN_GAP_SECONDS:
        time.sleep(MIN_GAP_SECONDS - gap)
    _last_hit[host] = time.time()


def fetch_html(url: str, retries: int = 3) -> str:
    if not _allowed(url):
        raise FetchError("blocked by robots.txt")
    last = None
    for attempt in range(retries):
        _wait_turn(url)
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US"}, timeout=TIMEOUT)
            if r.status_code == 200 and r.text:
                return r.text
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 404, 410):
                break  # retrying won't help
        except requests.RequestException as e:
            last = type(e).__name__
        time.sleep(2 ** attempt * 3)
    raise FetchError(last or "unknown error")


def fetch_rendered(url: str) -> str:
    """Load the page in a headless browser, for sites that build their listings with JavaScript."""
    if not _allowed(url):
        raise FetchError("blocked by robots.txt")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # browser not installed
        raise FetchError("browser unavailable") from e
    _wait_turn(url)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=60_000)
            return page.content()
        except Exception as e:  # noqa: BLE001
            raise FetchError(f"browser: {type(e).__name__}") from e
        finally:
            browser.close()
