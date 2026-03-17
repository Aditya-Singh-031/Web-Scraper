import asyncio
import gzip
import os
import csv
from lxml import etree
from io import BytesIO
from typing import List, Set
from playwright.async_api import async_playwright

OUTPUT_FILE = "data/sitemap_urls.csv"

# sitemap list (same as before)
SITEMAPS = [
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_0.xml.gz",
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_1.xml.gz",
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_2.xml.gz",
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_3.xml.gz",
]

SITEMAPS += [
    f"https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_spp_kia_{i}.xml.gz"
    for i in range(27)
]


# -------------------------
# PLAYWRIGHT FETCH
# -------------------------
async def fetch_with_browser(context, url: str) -> bytes:
    for attempt in range(5):
        try:
            page = await context.new_page()

            response = await page.goto(url, timeout=60000)

            if not response or response.status != 200:
                raise Exception(f"Status {response.status if response else 'None'}")

            content = await response.body()

            await page.close()
            return content

        except Exception as e:
            print(f"[retry {attempt+1}] {url} → {e}")
            await asyncio.sleep(2 + attempt)

    raise Exception(f"Failed: {url}")


# -------------------------
# XML PARSER
# -------------------------
def parse_xml(content: bytes):
    parser = etree.XMLParser(recover=True, ns_clean=True)
    return etree.fromstring(content, parser=parser)


def decompress(content: bytes) -> bytes:
    return gzip.decompress(content)


def extract_urls(root) -> List[str]:
    return [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
        if elem.text and "/oem-parts/" in elem.text
    ]


# -------------------------
# PROCESS
# -------------------------
async def process(context, url):
    print(f"Processing: {url}")

    content = await fetch_with_browser(context, url)
    content = decompress(content)

    root = parse_xml(content)
    return extract_urls(root)


# -------------------------
# MAIN
# -------------------------
async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 🔥 persistent context = more human-like
        context = await browser.new_context()

        semaphore = asyncio.Semaphore(3)  # keep low for stability

        async def bounded(url):
            async with semaphore:
                return await process(context, url)

        tasks = [bounded(url) for url in SITEMAPS]
        results = await asyncio.gather(*tasks)

        all_urls: Set[str] = set()
        for urls in results:
            all_urls.update(urls)

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