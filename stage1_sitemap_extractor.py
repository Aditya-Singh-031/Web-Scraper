import asyncio
import gzip
import os
import csv
from lxml import etree
from typing import List, Set
from playwright.async_api import async_playwright

OUTPUT_FILE = "data/sitemap_urls.csv"

SITEMAPS = [
    "https://www.kia.parts/sitemaps/sitemap_static_0.xml",
]

SITEMAPS += [
    f"https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_{i}.xml.gz"
    for i in range(4)
]

SITEMAPS += [
    f"https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_spp_kia_{i}.xml.gz"
    for i in range(27)
]


# -------------------------
# PARSER
# -------------------------
def parse_xml(content: bytes):
    parser = etree.XMLParser(recover=True, ns_clean=True)
    return etree.fromstring(content, parser=parser)


def is_gzip(content: bytes):
    return len(content) > 2 and content[:2] == b'\x1f\x8b'


def decompress_if_needed(content: bytes):
    if is_gzip(content):
        return gzip.decompress(content)
    return content


def extract_urls(root) -> List[str]:
    return [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
        if elem.text and "/oem-parts/" in elem.text
    ]


# -------------------------
# 🔥 CORE FIX: REAL TAB NAVIGATION
# -------------------------
async def fetch_via_new_tab(context, url: str) -> bytes:
    page = await context.new_page()

    try:
        response = await page.goto(url, timeout=60000, wait_until="domcontentloaded")

        if not response:
            raise Exception("No response")

        content = await response.body()

        # 🔥 detect HTML block page
        if content.startswith(b"<!DOCTYPE") or b"<html" in content[:200].lower():
            raise Exception("Blocked (HTML returned)")

        return content

    finally:
        await page.close()


# -------------------------
# PROCESS
# -------------------------
async def process(context, url):
    print(f"Processing: {url}")

    for attempt in range(5):
        try:
            content = await fetch_via_new_tab(context, url)

            content = decompress_if_needed(content)
            root = parse_xml(content)

            urls = extract_urls(root)
            print(f"→ Extracted {len(urls)} URLs")

            return urls

        except Exception as e:
            print(f"[retry {attempt+1}] {url} → {e}")
            await asyncio.sleep(3 + attempt)

    print(f"❌ Failed permanently: {url}")
    return []


# -------------------------
# MAIN
# -------------------------
async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context()

        # 🔥 IMPORTANT: warm up session
        page = await context.new_page()
        await page.goto("https://www.kia.parts/", timeout=60000)
        await asyncio.sleep(3)
        await page.close()

        all_urls: Set[str] = set()

        # 🔥 SEQUENTIAL (VERY IMPORTANT)
        for url in SITEMAPS:
            urls = await process(context, url)
            all_urls.update(urls)

            # human delay
            await asyncio.sleep(2)

        print(f"\nTotal URLs: {len(all_urls)}")

        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["url"])
            for url in sorted(all_urls):
                writer.writerow([url])

        await browser.close()

        print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())