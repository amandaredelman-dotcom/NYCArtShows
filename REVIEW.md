# Sunday review (run by Claude every Sunday, finished by 6 PM Eastern)

The scanner runs at 4 AM and saves `data/shows.json`. This review adds genres, fills gaps from the web,
publishes the site and emails Amanda. Work in a clone of this repository.

## 1. Get the latest scan
`git pull`, then `python3 web/build.py` to refresh `data/review_queue.json` and see what needs attention.

## 2. Check the big venues on the web
For every venue in `unreachable` (from `data/shows.json`), every venue with stale shows, and always for
**the Met, MoMA, the Morgan, the Frick, the Brooklyn Museum and the Guggenheim**, search the web for their
current and upcoming exhibitions (official venue pages and press releases first; listings sites only to
confirm). Record shows the scan missed in `data/web_shows.json` as:

```json
{"id": "<venue_id>--<slug>", "venue_id": "<id from venues.yaml>", "title": "...", "start_date": "YYYY-MM-DD",
 "end_date": "YYYY-MM-DD", "summary": "one neutral sentence in your own words", "url": "official page",
 "source": "web", "checked": "YYYY-MM-DD"}
```

Rewrite each venue's entries every week (drop closed shows). Use only dates you saw on an official or
reliable source; if unsure, leave the date out. Don't duplicate a show the scan already found.

## 3. Label every show in the review queue
Edit `data/labels.json`, keyed by show id:

```json
"frick--kent-monkman-officer-and-laughing-girl": {
  "genres": ["Contemporary painting", "Indigenous"],
  "media": ["Painting"],
  "related": [{"genre": "Dutch Golden Age", "note": "responds to Vermeer's Officer and Laughing Girl at the Frick"}],
  "blurb": "optional better one-sentence description",
  "start_date": "optional fix", "end_date": "optional fix", "title": "optional fix",
  "reception": "optional, e.g. Thu Nov 19, 6–8 PM", "hours": "optional", "tba": "optional, e.g. Late Jan 2027",
  "hide": false
}
```

- Use only labels from `scanner/taxonomy.py` (genres and media).
- Living artists get contemporary labels; earlier traditions they respond to go in `related` with a note.
- Set `"hide": true` for things that aren't exhibitions (events, past sales, page furniture like "Hard Art Ends").
- Fix any date that's flagged or looks wrong (check the venue page). Add opening receptions when known.
- Shows already labeled in earlier weeks keep their labels; only fix them if something changed.

## 4. Build and check
`python3 web/build.py --final`. The review queue should be empty or contain only shows whose dates truly
aren't published. Check the page's script parses (`node --check` on the extracted script).

## 5. Publish and email
- Republish `web/index.html` to the artifact in `web/config.yaml` (`artifact_slug`), as `index.html`.
- Send the email from Amanda's Gmail to `email_to` in `web/config.yaml`: subject
  `On View New York · <Mon D>`, HTML body `web/email.html`, plain-text body `web/email.txt`.
- Commit `data/labels.json`, `data/web_shows.json` and `data/published.json`, open a pull request and merge it.

## 6. If something goes wrong
Publish and send whatever is ready by 6 PM. Add a one-line note at the top of the email about anything
skipped. Never send an empty email.
