"""Sitemap downloader for Grokipedia"""
import requests
import xml.etree.ElementTree as ET
import os
from pathlib import Path

# === Configuration ===
# Get the scripts directory and navigate to grokipedia-sdk/grokipedia_sdk/links
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent / 'grokipedia-sdk' / 'grokipedia_sdk' / 'links'
SITEMAP_INDEX_URL = "https://grokipedia.com/sitemap.xml"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"  # XML namespace

# Ensure base output folder exists
BASE_DIR.mkdir(parents=True, exist_ok=True)


def get_sitemap_links(sitemap_url):
    """Fetch and parse a sitemap or sitemap index, returning all <loc> URLs."""
    print(f"Fetching: {sitemap_url}")
    r = requests.get(sitemap_url, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    return [loc.text.strip() for loc in root.findall(f".//{NS}loc")]


def get_sitemap_entries(sitemap_url):
    """Fetch and parse a sitemap, returning list of (url, lastmod) tuples."""
    print(f"Fetching: {sitemap_url}")
    r = requests.get(sitemap_url, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    
    entries = []
    for url_elem in root.findall(f"{NS}url"):
        loc = url_elem.find(f"{NS}loc")
        lastmod = url_elem.find(f"{NS}lastmod")
        if loc is not None:
            url = loc.text.strip() if loc.text else ""
            date = lastmod.text.strip() if lastmod is not None and lastmod.text else ""
            entries.append((url, date))
    return entries


if __name__ == '__main__':
    # === Step 1: Get all sitemap part URLs from the index ===
    part_urls = get_sitemap_links(SITEMAP_INDEX_URL)

    for sitemap_url in part_urls:
        # Example: https://assets.grokipedia.com/sitemap/sitemap-00001.xml
        part_name = os.path.basename(sitemap_url).replace(".xml", "")
        folder_path = BASE_DIR / part_name
        folder_path.mkdir(parents=True, exist_ok=True)

        # === Step 2: Get page entries with lastmod from this sitemap ===
        entries = get_sitemap_entries(sitemap_url)
        page_entries = [(u, d) for u, d in entries if "/page/" in u]
        
        slugs = [u.split("/page/")[1] for u, d in page_entries]
        dates = [d for u, d in page_entries]
        urls = [u for u, d in page_entries]

        # === Step 3: Save files ===
        urls_path = folder_path / "urls.txt"
        names_path = folder_path / "names.txt"
        dates_path = folder_path / "dates.txt"

        with open(urls_path, "w", encoding="utf-8") as f:
            f.write("\n".join(urls))

        with open(names_path, "w", encoding="utf-8") as f:
            f.write("\n".join(slugs))

        with open(dates_path, "w", encoding="utf-8") as f:
            f.write("\n".join(dates))

        print(f"✅ Saved {len(page_entries)} pages to {folder_path}")

    print("\nAll sitemap data downloaded successfully!")

