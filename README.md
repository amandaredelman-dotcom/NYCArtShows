# NYC Art Shows

A weekly scan of exhibitions in Manhattan, Long Island City and Brooklyn, labeled by genre so anyone can
filter for what they love. It feeds the **On View New York** site and a Sunday-evening email.

## How it works

1. **Sundays, 4 AM Eastern**, GitHub Actions runs `.github/workflows/scan.yml`.
2. It visits each venue in `venues.yaml` (politely: robots.txt respected, one request per site every few seconds).
3. Pages that haven't changed since last week are skipped. Changed pages are read by a small local AI model
   (Ollama, `qwen2.5:3b`) that lists each show's title, artists and dates. Sites that publish structured
   event data are read directly, without the model.
4. Each new show gets genre labels from `scanner/taxonomy.py`, including "in dialogue with" links for edge cases,
   and a flag when the model isn't confident.
5. Results are saved to `data/shows.json`; a per-venue report goes to `data/health.json` and the run summary.
6. **Sundays, 6 PM Eastern**, Claude reviews flagged shows, publishes the site and sends the email.

## Everyday tasks

- **Add a venue:** copy a block in `venues.yaml` and fill it in.
- **Run a scan now:** Actions tab → Weekly scan → Run workflow (optionally list venue ids, e.g. `met,frick`).
- **See what broke:** open the latest run's summary, or `data/health.json`. A venue that can't be reached keeps
  last week's shows (marked stale) instead of disappearing.
