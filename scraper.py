#!/usr/bin/env python3
"""
Velo Finder — S-Works Tarmac SL8 offer scanner for EU shops.

Strategy:
- Each shop is a config entry with a search URL.
- Generic parser extracts schema.org Product JSON-LD (works on most modern shops).
- Optional CSS-selector parser for shops without JSON-LD.
- Results filtered by KEYWORDS, written to docs/offers.json for the dashboard.

Run:  python scraper.py
"""

import json
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------- config

KEYWORDS = ["s-works", "tarmac", "sl8"]   # all must appear in title (case-insensitive)
EXCLUDE = ["frameset", "frame kit", "cadre", "rahmen", "kit cadre"]  # drop framesets; empty list to keep them
SIZE_HINT = "56"                          # tagged in output if found, not a hard filter
MAX_PRICE_EUR = None                      # e.g. 9000 to cap; None = no cap

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8,de;q=0.7",
}
TIMEOUT = 20
DELAY_BETWEEN_SHOPS = 2  # seconds, be polite

SHOPS = [
    {
        "name": "Alltricks",
        "country": "FR",
        "search_url": "https://www.alltricks.fr/recherche?text=s-works+tarmac+sl8",
        "parser": "jsonld",
    },
    {
        "name": "Corebicycle",
        "country": "ES",
        "search_url": "https://www.corebicycle.com/fr/catalogsearch/result/?q=s-works+tarmac+sl8",
        "parser": "jsonld",
    },
    {
        "name": "Lordgun",
        "country": "IT",
        "search_url": "https://www.lordgunbicycles.fr/recherche?q=s-works%20tarmac%20sl8",
        "parser": "jsonld",
    },
    {
        "name": "Specialized FR (outlet)",
        "country": "FR",
        "search_url": "https://www.specialized.com/fr/fr/shop/search?q=s-works%20tarmac%20sl8",
        "parser": "jsonld",   # JS-heavy; may return nothing with plain requests — see README
    },
    {
        "name": "buycycle",
        "country": "EU",
        "search_url": "https://buycycle.com/fr-fr/shop?search=s-works%20tarmac%20sl8",
        "parser": "jsonld",   # JS-heavy; may need the Playwright fallback
    },
]

# Shops that block bots or are fully JS-rendered: shown as one-tap manual
# search links on the dashboard instead of scraped.
MANUAL_SEARCH_LINKS = [
    {"name": "leboncoin", "country": "FR",
     "url": "https://www.leboncoin.fr/recherche?text=s-works%20tarmac%20sl8"},
    {"name": "Troc-Vélo", "country": "FR",
     "url": "https://www.troc-velo.com/fr-fr/velo-route/q/s-works%20tarmac%20sl8"},
    {"name": "Kleinanzeigen", "country": "DE",
     "url": "https://www.kleinanzeigen.de/s-s-works-tarmac-sl8/k0"},
    {"name": "buycycle", "country": "EU",
     "url": "https://buycycle.com/fr-fr/shop?search=s-works%20tarmac%20sl8"},
    {"name": "Specialized outlet FR", "country": "FR",
     "url": "https://www.specialized.com/fr/fr/c/velosenpromotion"},
]

# ---------------------------------------------------------------- helpers


def title_matches(title: str) -> bool:
    t = title.lower()
    if not all(k in t for k in KEYWORDS):
        return False
    if any(x in t for x in EXCLUDE):
        return False
    return True


def to_eur(price, currency):
    """Rough normalization so sorting works; refine rates if needed."""
    rates = {"EUR": 1.0, "GBP": 1.17, "CHF": 1.05, "PLN": 0.23,
             "SEK": 0.088, "DKK": 0.134, "CZK": 0.040}
    try:
        return round(float(price) * rates.get(currency, 1.0), 2)
    except (TypeError, ValueError):
        return None


def detect_size(title: str):
    m = re.search(r"\b(4[49]|5[0246]|58|61)\b", title)
    return m.group(1) if m else None


def extract_jsonld_products(soup, base_url):
    """Pull schema.org Product objects out of JSON-LD blocks."""
    offers = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = data if isinstance(data, list) else [data]
        # unwrap @graph and ItemList
        expanded = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if "@graph" in n:
                expanded.extend(x for x in n["@graph"] if isinstance(x, dict))
            elif n.get("@type") == "ItemList":
                for it in n.get("itemListElement", []):
                    item = it.get("item", it) if isinstance(it, dict) else None
                    if isinstance(item, dict):
                        expanded.append(item)
            else:
                expanded.append(n)
        for node in expanded:
            if node.get("@type") not in ("Product", ["Product"]):
                continue
            name = node.get("name") or ""
            offer = node.get("offers") or {}
            if isinstance(offer, list):
                offer = offer[0] if offer else {}
            price = offer.get("price") or offer.get("lowPrice")
            currency = offer.get("priceCurrency", "EUR")
            url = node.get("url") or offer.get("url") or base_url
            if name and price:
                offers.append({
                    "title": name.strip(),
                    "price": price,
                    "currency": currency,
                    "url": url,
                })
    return offers


def scan_shop(shop):
    print(f"→ {shop['name']} ...", end=" ")
    try:
        r = requests.get(shop["search_url"], headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"FAIL ({e.__class__.__name__})")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    raw = extract_jsonld_products(soup, shop["search_url"])
    results = []
    for o in raw:
        if not title_matches(o["title"]):
            continue
        eur = to_eur(o["price"], o["currency"])
        if MAX_PRICE_EUR and eur and eur > MAX_PRICE_EUR:
            continue
        results.append({
            "shop": shop["name"],
            "country": shop["country"],
            "title": o["title"],
            "price": float(o["price"]) if str(o["price"]).replace(".", "", 1).isdigit() else o["price"],
            "currency": o["currency"],
            "price_eur": eur,
            "size": detect_size(o["title"]),
            "url": o["url"],
        })
    print(f"{len(results)} offer(s)")
    return results


def main():
    all_offers = []
    for shop in SHOPS:
        all_offers.extend(scan_shop(shop))
        time.sleep(DELAY_BETWEEN_SHOPS)

    # dedupe by URL, sort by price
    seen, deduped = set(), []
    for o in sorted(all_offers, key=lambda x: x["price_eur"] or 1e9):
        if o["url"] in seen:
            continue
        seen.add(o["url"])
        deduped.append(o)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": " ".join(KEYWORDS),
        "size_hint": SIZE_HINT,
        "offers": deduped,
        "manual_links": MANUAL_SEARCH_LINKS,
    }
    with open("docs/offers.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n{len(deduped)} offers → docs/offers.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
