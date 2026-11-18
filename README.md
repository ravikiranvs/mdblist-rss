# mdblist-rss

Turns MDBList lists into RSS feeds, refreshed every 6 hours by GitHub Actions.

- Add lists in `feeds.json` as `"name": "https://mdblist.com/lists/<user>/<slug>"`.
- Feed URL: `https://raw.githubusercontent.com/<owner>/<repo>/main/feeds/<name>.xml`
- `pubDate` is when an item first appeared on the list; the initial backlog is dated 1970 so only later additions show as new.
- Run manually: Actions → Build RSS feeds → Run workflow.
