import asyncio
import gzip
import os
import csv
from lxml import etree
from io import BytesIO
from typing import List, Set
import tls_client

SITEMAP_INDEX = "https://www.kia.parts/sitemap.xml"
OUTPUT_FILE = "data/sitemap_urls.csv"


# -------------------------
# TLS SESSION (REAL BROWSER)
# -------------------------
session = tls_client.Session(
    client_identifier="chrome_120",  # mimics real Chrome
    random_tls_extension_order=True
)


# -------------------------
# FETCH (BYPASS 403)
# -------------------------
def fetch_sync(url: str) -> bytes:
    for attempt in range(5):
        try:
            res = session.get(url)

            if res.status_code != 200:
                raise Exception(f"Status {res.status_code}")

            content = res.content

            # detect block page
            if b"<html" in content[:500].lower():
                raise Exception("Blocked HTML")

            return content

        except Exception as e:
            print(f"[retry {attempt+1}] {url} → {e}")
            import time
            time.sleep(2 + attempt)

    raise Exception(f"Failed to fetch: {url}")


async def fetch(url: str) -> bytes:
    return await asyncio.to_thread(fetch_sync, url)


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
async def process_sitemap(url: str) -> List[str]:
    print(f"Processing: {url}")

    content = await fetch(url)
    content = decompress_if_needed(url, content)

    root = parse_xml(content)
    return extract_part_urls(root)


# -------------------------
# MAIN
# -------------------------
async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    print("Fetching main sitemap...")

    content = await fetch(SITEMAP_INDEX)
    root = parse_xml(content)

    sitemap_urls = extract_loc_urls(root)
    print(f"Found {len(sitemap_urls)} sitemap files")

    semaphore = asyncio.Semaphore(5)

    async def bounded(url):
        async with semaphore:
            return await process_sitemap(url)

    tasks = [bounded(url) for url in sitemap_urls]
    results = await asyncio.gather(*tasks)

    # flatten + deduplicate
    all_urls: Set[str] = set()
    for urls in results:
        all_urls.update(urls)

    print(f"Total unique part URLs: {len(all_urls)}")

    # save CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for url in sorted(all_urls):
            writer.writerow([url])

    print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())