# mdblist-rss

Turns MDBList lists into RSS feeds, refreshed every 6 hours by GitHub Actions.

- Add lists in `feeds.json` as `"name": "https://mdblist.com/lists/<user>/<slug>"`.
- Feed URL: `https://raw.githubusercontent.com/<owner>/<repo>/main/feeds/<name>.xml`
- Each item: title with IMDb rating, poster, synopsis, IMDb rating + votes, other ratings, links.
- Digital release date: add a repo secret `TMDB_TOKEN` (TMDb "API Read Access Token" from
  https://www.themoviedb.org/settings/api). Prefers the US date, then India, then the earliest anywhere.
- `pubDate` is when an item first appeared on the list.
- Run manually: Actions → Build RSS feeds → Run workflow.
