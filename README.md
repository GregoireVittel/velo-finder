# Velo Finder — S-Works Tarmac SL8

Scans EU shops for S-Works Tarmac SL8 offers, publishes results to a GitHub Pages dashboard. Runs 4x/day via GitHub Actions.

## Run locally

```bash
pip install -r requirements.txt
python scraper.py
open docs/index.html   # or python -m http.server -d docs 8080
```

## Deploy (same pattern as Offer Radar)

```bash
gh repo create velo-finder --public --source . --push
```

Then: repo → Settings → Pages → Deploy from branch → `main` / `/docs`.
The Actions workflow commits `docs/offers.json` on each scheduled scan; Pages redeploys automatically. Trigger a first run manually: Actions → Scan offers → Run workflow.

## Config (top of scraper.py)

- `KEYWORDS` — all must appear in the title (`s-works tarmac sl8`)
- `EXCLUDE` — drops framesets; set to `[]` to include them
- `MAX_PRICE_EUR` — optional price cap
- `SHOPS` — add a shop: name, country, search URL, `parser: "jsonld"`

## Notes on shops

Specialized is dealer-only, so Bike24/Bike-Discount won't have it. Scraped: Alltricks, Corebicycle, Lordgun, specialized.com, buycycle. specialized.com and buycycle render via JS — if plain requests return 0 offers there, the dashboard still gives you one-tap manual search links (leboncoin, Kleinanzeigen, Troc-Vélo, buycycle, Specialized outlet). A Playwright-based fetch for those two is the natural v2 if needed.
