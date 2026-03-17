
import asyncio
import httpx
import gzip
from lxml import etree
from io import BytesIO
import csv
from typing import List, Set

# For Playwright fallback
import sys
import subprocess
try:
    from playwright.async_api import async_playwright
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "lxml"])
    from playwright.async_api import async_playwright

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
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.kia.parts/",
                    "Connection": "keep-alive",
                    "DNT": "1",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1"
                }
                # Enable HTTP/2 and cookies
                r = await client.get(url, headers=headers, timeout=30, http2=True)
                r.raise_for_status()
                return r.content
            except Exception as e:
                if attempt == 2:
                    # Try Playwright fallback
                    print("httpx failed, trying Playwright fallback...")
                    content = await fetch_with_playwright(url)
                    if content:
                        return content
                    raise e
                await asyncio.sleep(2)

    # Playwright fallback for protected sites
    async def fetch_with_playwright(url: str) -> bytes:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=30000)
                # Wait for network idle or XML loaded
                await page.wait_for_load_state('networkidle')
                content = await page.content()
                await browser.close()
                # If XML, return as bytes
                if content.strip().startswith("<?xml"):
                    return content.encode()
                # Try to extract XML from HTML body
                import re
                xml_match = re.search(r'<\?xml.*', content, re.DOTALL)
                if xml_match:
                    return xml_match.group(0).encode()
                return content.encode()
        except Exception as e:
            print(f"Playwright fetch failed: {e}")
            return None


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