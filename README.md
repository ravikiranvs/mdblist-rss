# mdblist-rss

Turns MDBList lists into RSS feeds, refreshed daily at 2:00 PM IST by GitHub Actions.

- Add lists in `feeds.json` as `"name": "https://mdblist.com/lists/<user>/<slug>"`.
- Feed URL: `https://raw.githubusercontent.com/<owner>/<repo>/main/feeds/<name>.xml`
- Each item: title with IMDb rating, poster, synopsis, IMDb rating + votes, other ratings, links.
- `pubDate` is when an item first appeared on the list.
- Run manually: Actions → Build RSS feeds → Run workflow.
