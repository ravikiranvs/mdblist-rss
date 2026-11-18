# mdblist-rss

Turns MDBList lists into RSS feeds, refreshed every 6 hours by GitHub Actions.

- Add lists in `feeds.json` as `"name": "https://mdblist.com/lists/<user>/<slug>"`.
- Feed URL: `https://raw.githubusercontent.com/<owner>/<repo>/main/feeds/<name>.xml`
- `pubDate` is when an item first appeared on the list; the initial backlog is stamped with the first run's time, one minute apart in list order.
- Run manually: Actions → Build RSS feeds → Run workflow.
