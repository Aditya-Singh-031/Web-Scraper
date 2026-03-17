import asyncio
import httpx
import gzip
from lxml import etree
from io import BytesIO
import csv
from typing import List, Set

SITEMAP_INDEX = "https://www.kia.parts/sitemap.xml"
OUTPUT_FILE = "data/sitemap_urls.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
}


async def fetch(client: httpx.AsyncClient, url: str) -> bytes:
    """Fetch content with retries"""
    for attempt in range(3):
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                r = await client.get(url, headers=headers, timeout=30)
                r.raise_for_status()
                return r.content
            except Exception as e:
                if attempt == 2:
                    raise e
                await asyncio.sleep(2)


def parse_xml(content: bytes) -> etree._Element:
    """Parse XML safely"""
    return etree.parse(BytesIO(content)).getroot()


def extract_sitemap_urls(root) -> List[str]:
    """Extract sitemap URLs from sitemap index"""
    return [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
    ]


def decompress_if_needed(url: str, content: bytes) -> bytes:
    """Handle .gz sitemaps"""
    if url.endswith(".gz"):
        return gzip.decompress(content)
    return content


def extract_part_urls(root) -> List[str]:
    """Extract URLs from sitemap"""
    urls = []
    for elem in root.findall(".//{*}loc"):
        url = elem.text.strip()
        if "/oem-parts/" in url:   # filter only product pages
            urls.append(url)
    return urls


async def process_sitemap(client, url: str) -> List[str]:
    """Download and parse one sitemap"""
    print(f"Processing sitemap: {url}")

    content = await fetch(client, url)
    content = decompress_if_needed(url, content)

    root = parse_xml(content)
    return extract_part_urls(root)


async def main():
    async with httpx.AsyncClient(headers=HEADERS, http2=True) as client:

        # Step 1: Fetch main sitemap index
        print("Fetching sitemap index...")
        content = await fetch(client, SITEMAP_INDEX)
        root = parse_xml(content)

        sitemap_urls = extract_sitemap_urls(root)
        print(f"Found {len(sitemap_urls)} sitemap files")

        # Step 2: Process all sitemaps concurrently
        tasks = [
            process_sitemap(client, url)
            for url in sitemap_urls
        ]

        results = await asyncio.gather(*tasks)

        # Step 3: Flatten + deduplicate
        all_urls: Set[str] = set()
        for urls in results:
            all_urls.update(urls)

        print(f"Total unique part URLs: {len(all_urls)}")

        # Step 4: Save CSV
        with open(OUTPUT_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["url"])
            for url in sorted(all_urls):
                writer.writerow([url])

        print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())