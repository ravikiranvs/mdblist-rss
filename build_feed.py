#!/usr/bin/env python3
"""Build RSS feeds from MDBList lists.

feeds.json maps a feed name to an MDBList list URL. For each list:
  - <list>/json gives the list membership (IMDb ids).
  - The list's HTML page (plus its infinite-scroll pages) gives poster,
    synopsis, IMDb rating/votes, other ratings and links.
State:
  state/<name>.json       first-seen time per item (used as pubDate)
  state/<name>.meta.json  cached metadata per item
Output: feeds/<name>.xml (RSS 2.0 + Media RSS for posters).
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent
MAX_ITEMS = 200
MAX_PAGES = 15
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
DATE_FMT = "%a, %d %b %Y %H:%M:%S %z"


def get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# ---------------------------------------------------------------- MDBList

def fetch_members(list_url: str) -> list[dict]:
    data = json.loads(get(list_url.rstrip("/") + "/json", {"Accept": "application/json"}))
    if isinstance(data, dict):
        data = [i for v in data.values() if isinstance(v, list) for i in v]
    return data


def _txt(s: str | None) -> str | None:
    if s is None:
        return None
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    return s or None


def parse_cards(page: str) -> dict[str, dict]:
    """Return {imdb_id: card metadata} for every card in an HTML page/fragment."""
    out = {}
    for c in re.split(r'<div class="card" data-media-id=', page)[1:]:
        d: dict = {"mediatype": (re.search(r'data-mediatype="(\w+)"', c) or [None, None])[1]}
        m = re.search(r'<img[^>]*poster-card[^>]*src="([^"]+)"', c)
        d["poster"] = m and m.group(1).replace("/w200/", "/w500/")
        m = re.search(r'class="idscore"[^>]*>\s*([^<]*?)\s*<', c)
        d["mdb_score"] = m.group(1) if m and m.group(1) not in ("?", "") else None
        m = re.search(r'movie-title" title="([^"]+)"', c)
        d["title"] = m and html.unescape(m.group(1))
        m = re.search(r'collapsible-description"[^>]*>(.*?)</div>', c, re.S)
        d["synopsis"] = _txt(m and m.group(1))
        ratings = {}
        for g in re.finditer(
            r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a></div>'
            r'(?:<div class="three wide column idtext">\s*([^<]*?)\s*</div>)?'
            r'(?:<div class="one wide column idsmall">/?([^<]*?)/?</div>)?', c):
            ratings[g.group(2).strip()] = {
                "url": g.group(1), "rating": g.group(3) or None, "votes": g.group(4) or None}
        d["ratings"] = ratings
        imdb = re.search(r"tt\d+", ratings.get("IMDb", {}).get("url", ""))
        if imdb:
            out[imdb.group()] = d
    return out


def fetch_cards(list_url: str, wanted: set[str]) -> dict[str, dict]:
    cards = parse_cards(get(list_url).decode("utf-8", "replace"))
    for page in range(1, MAX_PAGES):
        if wanted <= cards.keys():
            break
        q = urllib.parse.urlencode({
            "append": "yes", "filter": "", "new_items": "false", "show_hidden": "false",
            "item_filter": "", "mediatype": "", "sort": "", "sortorder": "",
            "q_current_page": page})
        try:
            frag = get(f"{list_url}?{q}", {"X-Requested-With": "XMLHttpRequest",
                                           "Referer": list_url}).decode("utf-8", "replace")
        except Exception as e:
            print(f"  page {page}: {e}", file=sys.stderr)
            break
        new = parse_cards(frag)
        if not new or new.keys() <= cards.keys():
            break
        cards.update(new)
    print(f"  cards scraped: {len(cards)} (of {len(wanted)} on list)")
    return cards


# ---------------------------------------------------------------- feed

def fmt_votes(v: str | None) -> str:
    try:
        n = int(v.replace(",", ""))
    except (AttributeError, ValueError):
        return ""
    return f" ({n/1000:.1f}k votes)" if n >= 1000 else f" ({n} votes)"


def item_xml(k: str, it: dict, m: dict, pub: str, list_url: str) -> str:
    year = it.get("release_year")
    base_title = m.get("title") or (f"{it.get('title', 'Untitled')}" + (f" ({year})" if year else ""))
    imdb = m.get("ratings", {}).get("IMDb", {})
    imdb_rating = imdb.get("rating")

    title = base_title + (f" — IMDb {imdb_rating}" if imdb_rating else "")
    link = f"https://www.imdb.com/title/{k}/"

    facts = []
    if imdb_rating:
        facts.append(f"<b>IMDb:</b> {escape(imdb_rating)}{escape(fmt_votes(imdb.get('votes')))}")
    elif "ratings" in m:  # scraped, but IMDb has no rating yet
        facts.append("<b>IMDb:</b> not rated yet")
    others = []
    for src, label in (("Letterboxd", "Letterboxd"), ("Tomatoes", "RT"),
                       ("Metacritic", "MC"), ("Trakt", "Trakt")):
        r = m.get("ratings", {}).get(src, {}).get("rating")
        if r:
            others.append(f"{label} {r}{'%' if src == 'Tomatoes' else ''}")
    if others:
        facts.append("<b>Other:</b> " + escape(" · ".join(others)))

    body = ""
    if m.get("poster"):
        body += f'<p><img src="{escape(m["poster"])}" alt="poster" width="200"/></p>'
    if facts:
        body += "<p>" + "<br/>".join(facts) + "</p>"
    if m.get("synopsis"):
        body += f"<p>{escape(m['synopsis'])}</p>"
    links = [f'<a href="{escape(v["url"])}">{escape(s)}</a>'
             for s, v in m.get("ratings", {}).items() if v.get("url")]
    if links:
        body += "<p>" + " · ".join(links) + "</p>"

    media = ""
    if m.get("poster"):
        p = escape(m["poster"])
        media = (f'      <media:content url="{p}" medium="image" type="image/jpeg"/>\n'
                 f'      <media:thumbnail url="{p}"/>\n'
                 f'      <enclosure url="{p}" type="image/jpeg" length="0"/>\n')
    return (
        "    <item>\n"
        f"      <title>{escape(title)}</title>\n"
        f"      <link>{escape(link)}</link>\n"
        f'      <guid isPermaLink="false">{escape(k)}</guid>\n'
        f"      <pubDate>{pub}</pubDate>\n"
        + media +
        f"      <description><![CDATA[{body.replace(']]>', ']]&gt;')}]]></description>\n"
        "    </item>"
    )


def build(name: str, list_url: str) -> None:
    state_path = ROOT / "state" / f"{name}.json"
    meta_path = ROOT / "state" / f"{name}.meta.json"
    feed_path = ROOT / "feeds" / f"{name}.xml"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    print(f"[{name}]")
    members = fetch_members(list_url)
    if not members:
        print("  list returned no items; leaving feed unchanged", file=sys.stderr)
        return
    by_key = {str(it.get("imdb_id") or it.get("id")): it for it in members}

    # first-seen dates
    now_dt = datetime.now(timezone.utc)
    legacy = [k for k, v in state.items() if v.startswith("Thu, 01 Jan 1970")]
    for k in legacy:
        del state[k]
    backlog = not state
    new_keys = []
    for i, k in enumerate(by_key):
        if k not in state:
            state[k] = format_datetime(now_dt - timedelta(minutes=i)) if backlog else format_datetime(now_dt)
            new_keys.append(k)
    print(f"  new items: {len(new_keys)}")

    # scraped metadata (keep cached values if scraping fails or misses an item)
    try:
        cards = fetch_cards(list_url, set(by_key))
    except Exception as e:
        print(f"  scrape failed: {e}", file=sys.stderr)
        cards = {}
    meta.update(cards)

    ordered = sorted(by_key, key=lambda k: datetime.strptime(state[k], DATE_FMT), reverse=True)[:MAX_ITEMS]
    entries = [item_xml(k, by_key[k], meta.get(k, {}), state[k], list_url) for k in ordered]
    channel_body = (
        f"    <title>MDBList: {escape(name)}</title>\n"
        f"    <link>{escape(list_url)}</link>\n"
        f"    <description>Auto-generated from {escape(list_url)}</description>\n"
        + "\n".join(entries))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">\n  <channel>\n'
           f"    <lastBuildDate>{format_datetime(now_dt)}</lastBuildDate>\n"
           + channel_body + "\n  </channel>\n</rss>\n")

    old = feed_path.read_text() if feed_path.exists() else ""
    strip = lambda s: re.sub(r"<lastBuildDate>.*?</lastBuildDate>", "", s)
    feed_path.parent.mkdir(exist_ok=True)
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps(state, indent=1, sort_keys=True))
    meta_path.write_text(json.dumps({k: meta[k] for k in sorted(meta) if k in by_key},
                                    indent=1, ensure_ascii=False))
    if strip(old) != strip(xml):
        feed_path.write_text(xml)
        print(f"  wrote {len(entries)} items")
    else:
        print("  feed unchanged")


def main() -> int:
    feeds = json.loads((ROOT / "feeds.json").read_text())
    failures = 0
    for name, url in feeds.items():
        try:
            build(name, url)
        except Exception as e:
            failures += 1
            print(f"[{name}] ERROR: {e}", file=sys.stderr)
    return 1 if failures == len(feeds) else 0


if __name__ == "__main__":
    sys.exit(main())
