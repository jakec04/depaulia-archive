#!/usr/bin/env python3
"""Archive new DePaulia stories as PDFs.

Reads the RSS feed at depauliaonline.com/feed/, finds entries not yet
archived, renders each story's print view (?print=true) to a PDF with
headless Chromium and saves it under pdfs/YYYY/MM/. A JSON state file
(archive/seen.json) tracks which URLs have already been captured so
stories are only saved once.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import feedparser
from playwright.sync_api import sync_playwright

FEED_URL = "https://depauliaonline.com/feed/"
# WordPress feeds show ~10 items per page; walk back this many pages so a
# heavy publishing day (10-20 stories in one morning) is fully captured.
MAX_FEED_PAGES = 5
REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "archive" / "seen.json"
PDF_ROOT = REPO_ROOT / "pdfs"
PAGE_TIMEOUT_MS = 60_000


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def canonical_url(url: str) -> str:
    """Strip query strings and fragments so the same story isn't saved twice."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def print_url(url: str) -> str:
    return canonical_url(url).rstrip("/") + "/?print=true"


def slug_from_url(url: str) -> str:
    """Last meaningful path segment, e.g. .../sports/some-story/ -> some-story."""
    path = urlsplit(url).path.strip("/")
    segments = [s for s in path.split("/") if s]
    slug = segments[-1] if segments else "story"
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", slug).strip("-").lower()
    return slug or "story"


def entry_date(entry) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


def pdf_path_for(entry) -> Path:
    published = entry_date(entry)
    slug = slug_from_url(entry.link)
    folder = PDF_ROOT / f"{published:%Y}" / f"{published:%m}"
    return folder / f"{published:%Y-%m-%d}-{slug}.pdf"


def render_pdf(page, url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
    # Wait for main content to be visible (article or post content)
    try:
        page.wait_for_selector("body > *", timeout=PAGE_TIMEOUT_MS)
    except Exception:
        pass  # Page might not have complex DOM, but that's okay
    # Give late-loading images and dynamic content time to render
    page.wait_for_timeout(3500)
    # Force screen CSS so print-only stylesheets don't hide the article body
    page.emulate_media(media="screen")
    page.pdf(
        path=str(destination),
        format="Letter",
        margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"},
        print_background=True,
    )


def fetch_new_entries(state: dict) -> list:
    """Walk paginated feed (/feed/, /feed/?paged=2, ...) collecting unseen
    entries. Stops early once a whole page contains only stories we've
    already archived, or the feed runs out of pages."""
    new_entries = []
    seen_links = set()

    for page_num in range(1, MAX_FEED_PAGES + 1):
        url = FEED_URL if page_num == 1 else f"{FEED_URL}?paged={page_num}"
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            if page_num == 1:
                print(f"Could not parse feed: {feed.bozo_exception}", file=sys.stderr)
            break

        if not feed.entries:
            break

        page_had_new = False
        for entry in feed.entries:
            if not entry.get("link"):
                continue
            url_key = canonical_url(entry.link)
            if url_key in state or url_key in seen_links:
                continue
            seen_links.add(url_key)
            new_entries.append(entry)
            page_had_new = True

        # Everything on this page was already archived: older pages will be too
        if not page_had_new and page_num > 1:
            break

    return new_entries


def main() -> int:
    state = load_state()
    new_entries = fetch_new_entries(state)

    if not new_entries:
        print("No new stories.")
        return 0

    print(f"Found {len(new_entries)} new stories.")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for entry in new_entries:
            url = canonical_url(entry.link)
            destination = pdf_path_for(entry)
            try:
                render_pdf(page, print_url(url), destination)
            except Exception as exc:  # noqa: BLE001 - log and move on
                print(f"FAILED  {url}: {exc}", file=sys.stderr)
                continue

            state[url] = {
                "title": entry.get("title", ""),
                "pdf": str(destination.relative_to(REPO_ROOT)),
                "archived_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            print(f"Saved   {destination.relative_to(REPO_ROOT)}")

        browser.close()

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
