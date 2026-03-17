import asyncio
import gzip
import os
import csv
from lxml import etree
from io import BytesIO
from typing import List, Set
import httpx
from playwright.async_api import async_playwright

SITEMAP_INDEX = "https://www.kia.parts/sitemap.xml"
OUTPUT_FILE = "data/sitemap_urls.csv"


# -------------------------
# STEP 1: GET COOKIES VIA REAL BROWSER
# -------------------------
async def get_cookies():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        page = await context.new_page()
        await page.goto("https://www.kia.parts/", timeout=60000)

        cookies = await context.cookies()

        await browser.close()

        return {cookie["name"]: cookie["value"] for cookie in cookies}


# -------------------------
# FETCH WITH COOKIES
# -------------------------
async def fetch(client, url: str) -> bytes:
    for attempt in range(5):
        try:
            r = await client.get(url)

            if r.status_code == 403:
                raise Exception("403 Blocked")

            r.raise_for_status()

            content = r.content

            if b"<html" in content[:500].lower():
                raise Exception("Blocked HTML")

            return content

        except Exception as e:
            print(f"[retry {attempt+1}] {url} → {e}")
            await asyncio.sleep(2 + attempt)

    raise Exception(f"Failed to fetch: {url}")


# -------------------------
# XML PARSER
# -------------------------
def parse_xml(content: bytes):
    parser = etree.XMLParser(recover=True, ns_clean=True)
    return etree.fromstring(content, parser=parser)


# -------------------------
# UTIL FUNCTIONS
# -------------------------
def extract_loc_urls(root) -> List[str]:
    return [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
        if elem.text
    ]


def decompress_if_needed(url: str, content: bytes) -> bytes:
    if url.endswith(".gz"):
        return gzip.decompress(content)
    return content


def extract_part_urls(root) -> List[str]:
    urls = []
    for url in extract_loc_urls(root):
        if "/oem-parts/" in url:
            urls.append(url)
    return urls


# -------------------------
# PROCESS SITEMAP
# -------------------------
async def process_sitemap(client, url: str) -> List[str]:
    print(f"Processing: {url}")

    content = await fetch(client, url)
    content = decompress_if_needed(url, content)

    root = parse_xml(content)
    return extract_part_urls(root)


# -------------------------
# MAIN
# -------------------------
async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    print("Launching browser to get cookies...")
    cookies = await get_cookies()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.kia.parts/",
    }

    async with httpx.AsyncClient(
        headers=headers,
        cookies=cookies,
        http2=True,
        follow_redirects=True,
        timeout=30
    ) as client:

        print("Fetching sitemap index...")

        content = await fetch(client, SITEMAP_INDEX)
        root = parse_xml(content)

        sitemap_urls = extract_loc_urls(root)
        print(f"Found {len(sitemap_urls)} sitemap files")

        semaphore = asyncio.Semaphore(5)

        async def bounded(url):
            async with semaphore:
                return await process_sitemap(client, url)

        tasks = [bounded(url) for url in sitemap_urls]
        results = await asyncio.gather(*tasks)

        # flatten + deduplicate
        all_urls: Set[str] = set()
        for urls in results:
            all_urls.update(urls)

        print(f"Total unique part URLs: {len(all_urls)}")

        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["url"])
            for url in sorted(all_urls):
                writer.writerow([url])

        print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())