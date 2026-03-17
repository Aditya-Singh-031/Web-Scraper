import asyncio
import tls_client.aio as tls_client
import gzip
import os
import csv
from lxml import etree
from io import BytesIO
from typing import List, Set

SITEMAP_INDEX = "https://www.kia.parts/sitemap.xml"
OUTPUT_FILE = "data/sitemap_urls.csv"

# 🔥 FULL BROWSER HEADERS (CRITICAL)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.kia.parts/",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# -------------------------
# FETCH (ANTI-BOT SAFE)
# -------------------------
async def fetch(client: tls_client.Session, url: str) -> bytes:
    for attempt in range(5):
        try:
            r = await client.get(url, headers=HEADERS)

            if r.status_code == 403:
                raise Exception("403 Blocked")

            r.raise_for_status()

            content = r.content

            # detect HTML block page
            if b"<html" in content[:500].lower():
                raise ValueError("Blocked (HTML returned instead of XML)")

            return content

        except Exception as e:
            print(f"[retry {attempt+1}] {url} → {e}")
            await asyncio.sleep(2 + attempt)

    raise Exception(f"Failed to fetch sitemap: {url}")


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

    client = tls_client.Session(
        client_identifier="chrome_120",
        random_tls_extension_order=True
    )

    print("Fetching main sitemap...")

    content = await fetch(client, SITEMAP_INDEX)
    root = parse_xml(content)

    sitemap_urls = extract_loc_urls(root)
    print(f"Found {len(sitemap_urls)} sitemap files")

    semaphore = asyncio.Semaphore(20)

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

    # save CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for url in sorted(all_urls):
            writer.writerow([url])

    print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())