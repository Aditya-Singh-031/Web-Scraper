import asyncio
import httpx
import gzip
import os
import csv
from lxml import etree
from io import BytesIO
from typing import List, Set


SITEMAP_INDEX = "https://www.kia.parts/sitemap.xml"
OUTPUT_FILE = "data/sitemap_urls.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
}


# -------------------------
# FETCH
# -------------------------
async def fetch(client: httpx.AsyncClient, url: str) -> bytes:
    for attempt in range(3):
        try:
            r = await client.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()

            content = r.content

            # 🔥 CRITICAL: ensure we actually got XML
            if b"<html" in content[:500].lower():
                raise ValueError("Received HTML instead of XML (likely blocked)")

            return content

        except Exception as e:
            print(f"[retry {attempt+1}] Failed: {url} → {e}")
            await asyncio.sleep(2)

    raise Exception(f"Failed to fetch sitemap: {url}")


# -------------------------
# XML PARSER (SAFE)
# -------------------------
def parse_xml(content: bytes):
    try:
        parser = etree.XMLParser(recover=True, ns_clean=True)
        return etree.fromstring(content, parser=parser)
    except Exception as e:
        print("XML parsing failed. Content preview:\n", content[:300])
        raise e


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
# PROCESS EACH SITEMAP
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

    async with httpx.AsyncClient() as client:

        print("Fetching main sitemap...")

        content = await fetch(client, SITEMAP_INDEX)
        root = parse_xml(content)

        sitemap_urls = extract_loc_urls(root)
        print(f"Found {len(sitemap_urls)} sitemap files")

        # limit concurrency (important for stability)
        semaphore = asyncio.Semaphore(5)

        async def bounded_process(url):
            async with semaphore:
                return await process_sitemap(client, url)

        tasks = [bounded_process(url) for url in sitemap_urls]

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