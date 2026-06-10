# DePaulia PDF Archive

Automatically archives new stories from [The DePaulia](https://depauliaonline.com) as PDFs.

Every Monday around 5pm Chicago time, a GitHub Actions workflow checks the RSS feed at `depauliaonline.com/feed/`, finds stories it hasn't seen before, loads each one's print view (`?print=true`) in headless Chromium, renders it to PDF and commits the file to this repo.

## How it works

- `scripts/archive.py` does the work: parse feed, diff against `archive/seen.json`, render PDFs with Playwright
- `.github/workflows/archive.yml` runs it hourly (and on demand via the Actions tab)
- PDFs land in `pdfs/YYYY/MM/YYYY-MM-DD-story-slug.pdf`
- `archive/seen.json` tracks every archived URL with its title, PDF path and timestamp, so nothing is saved twice

## Setup

1. Create a new GitHub repo and push these files to it
2. That's it — Actions is on by default and the workflow has `contents: write` permission, so no tokens or secrets are needed
3. To backfill or test immediately, go to **Actions → Archive DePaulia stories → Run workflow**

Note: the feed shows ~10 stories per page, so the script walks back through paginated feed pages (`/feed/?paged=2`, etc., up to 5 pages) until it reaches stories already archived. That comfortably covers The DePaulia's Monday-morning batch of 10-20 stories. For a deeper historical backfill you'd want to walk the sitemap instead.

## Run locally

```bash
pip install -r requirements.txt
playwright install chromium
python scripts/archive.py
```

## Tweaks

- Change the schedule in `archive.yml` (`cron: "17 22 * * 1"` — UTC, so 5:17pm Chicago in summer, 4:17pm in winter)
- Archive a section feed instead by changing `FEED_URL` (e.g. `https://depauliaonline.com/category/sports/feed/`)
- Adjust page size or margins in `render_pdf()` in `scripts/archive.py`
