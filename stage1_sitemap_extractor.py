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


def decompress_if_needed(url: str, content: bytes) -> bytes:
    if url.endswith(".gz"):
        return gzip.decompress(content)
    return content


def extract_urls(root) -> List[str]:
    return [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
        if elem.text and "/oem-parts/" in elem.text
    ]


# -------------------------
# CORE FETCH (NETWORK INTERCEPT)
# -------------------------
async def fetch_via_network(page, url: str) -> bytes:
    response_data = None

    async def handle_response(response):
        nonlocal response_data
        if response.url == url:
            try:
                response_data = await response.body()
            except:
                pass

    page.on("response", handle_response)

    await page.goto(url, timeout=60000)

    # wait until response captured
    for _ in range(20):
        if response_data:
            return response_data
        await asyncio.sleep(0.5)

    raise Exception("Failed to capture response")


# -------------------------
# PROCESS
# -------------------------
async def process(page, url):
    print(f"Processing: {url}")

    content = await fetch_via_network(page, url)
    content = decompress_if_needed(url, content)

    root = parse_xml(content)
    urls = extract_urls(root)

    print(f"→ Extracted {len(urls)} URLs")
    return urls


# -------------------------
# MAIN
# -------------------------
async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context()
        page = await context.new_page()

        # 🔥 open homepage first (important)
        await page.goto("https://www.kia.parts/", timeout=60000)

        all_urls: Set[str] = set()

        for url in SITEMAPS:
            try:
                urls = await process(page, url)
                all_urls.update(urls)

                await asyncio.sleep(2)  # human delay

            except Exception as e:
                print(f"❌ Skipped {url}: {e}")

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