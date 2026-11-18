#!/usr/bin/env python3
"""Build RSS feeds from MDBList lists.

Reads feeds.json ({"name": "list URL", ...}), fetches each list's JSON
(<list URL>/json), tracks when each item was first seen in state/<name>.json,
and writes feeds/<name>.xml. pubDate = first-seen time, so new additions
surface as new items in any RSS reader.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent
MAX_ITEMS = 200
UA = "Mozilla/5.0 (mdblist-rss; +https://github.com)"


def fetch_items(list_url: str) -> list[dict]:
    url = list_url.rstrip("/") + "/json"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if isinstance(data, dict):  # tolerate {"movies": [...], "shows": [...]} shapes
        data = [i for v in data.values() if isinstance(v, list) for i in v]
    return data


def item_key(it: dict) -> str:
    return str(it.get("imdb_id") or it.get("id") or it.get("tmdb_id") or it.get("title"))


def item_link(it: dict, list_url: str) -> str:
    if it.get("imdb_id"):
        return f"https://www.imdb.com/title/{it['imdb_id']}/"
    return list_url


def build(name: str, list_url: str) -> bool:
    state_path = ROOT / "state" / f"{name}.json"
    feed_path = ROOT / "feeds" / f"{name}.xml"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    items = fetch_items(list_url)
    if not items:
        print(f"[{name}] list returned no items; leaving feed unchanged", file=sys.stderr)
        return False

    now = format_datetime(datetime.now(timezone.utc))
    first_run = not state
    changed = False
    for it in items:
        k = item_key(it)
        if k not in state:
            # On the very first run, date everything at epoch so the
            # initial backlog doesn't flood readers as "new".
            state[k] = "Thu, 01 Jan 1970 00:00:00 +0000" if first_run else now
            changed = True

    if not changed and feed_path.exists():
        print(f"[{name}] no new items")
        return False

    by_key = {item_key(it): it for it in items}
    ordered = sorted(
        by_key.items(),
        key=lambda kv: datetime.strptime(state[kv[0]], "%a, %d %b %Y %H:%M:%S %z"),
        reverse=True,
    )[:MAX_ITEMS]

    entries = []
    for k, it in ordered:
        year = it.get("release_year") or it.get("year")
        title = f"{it.get('title', 'Untitled')}" + (f" ({year})" if year else "")
        mtype = it.get("mediatype") or it.get("type") or ""
        link = item_link(it, list_url)
        desc = " · ".join(str(x) for x in (mtype, year, it.get("imdb_id")) if x)
        entries.append(
            "    <item>\n"
            f"      <title>{escape(title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid isPermaLink=\"false\">{escape(k)}</guid>\n"
            f"      <pubDate>{state[k]}</pubDate>\n"
            f"      <description>{escape(desc)}</description>\n"
            "    </item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n  <channel>\n'
        f"    <title>MDBList: {escape(name)}</title>\n"
        f"    <link>{escape(list_url)}</link>\n"
        f"    <description>Auto-generated from {escape(list_url)}</description>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(entries)
        + "\n  </channel>\n</rss>\n"
    )

    feed_path.parent.mkdir(exist_ok=True)
    state_path.parent.mkdir(exist_ok=True)
    feed_path.write_text(xml)
    state_path.write_text(json.dumps(state, indent=1, sort_keys=True))
    print(f"[{name}] wrote {len(entries)} items")
    return True


def main() -> int:
    feeds = json.loads((ROOT / "feeds.json").read_text())
    failures = 0
    for name, url in feeds.items():
        try:
            build(name, url)
        except Exception as e:  # keep going for other lists
            failures += 1
            print(f"[{name}] ERROR: {e}", file=sys.stderr)
    return 1 if failures == len(feeds) else 0


if __name__ == "__main__":
    sys.exit(main())
