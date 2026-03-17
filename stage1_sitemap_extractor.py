import asyncio
import gzip
import os
import csv
from lxml import etree
from io import BytesIO
from typing import List, Set
import httpx

OUTPUT_FILE = "data/sitemap_urls.csv"

# 🔥 MANUALLY PROVIDED SITEMAPS (BYPASS BLOCKED INDEX)
SITEMAPS = [
    # ppicker
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_0.xml.gz",
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_1.xml.gz",
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_2.xml.gz",
    "https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_ppicker_kia_3.xml.gz",
]

# add spp sitemaps (0–26)
SITEMAPS += [
    f"https://www.kia.parts/sitemaps/ec2ff22bf5636da2ba256d2fe11a68d7_sitemap_spp_kia_{i}.xml.gz"
    for i in range(27)
]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.kia.parts/",
}


# -------------------------
# FETCH
# -------------------------
async def fetch(client, url: str) -> bytes:
    for attempt in range(5):
        try:
            r = await client.get(url)

            if r.status_code != 200:
                raise Exception(f"Status {r.status_code}")

            return r.content

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
# PROCESS SITEMAP
# -------------------------
async def process(client, url):
    print(f"Processing: {url}")

    content = await fetch(client, url)
    content = decompress(content)

    root = parse_xml(content)
    return extract_urls(root)


# -------------------------
# MAIN
# -------------------------
async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    async with httpx.AsyncClient(
        headers=HEADERS,
        http2=True,
        timeout=30,
        follow_redirects=True
    ) as client:

        semaphore = asyncio.Semaphore(5)

        async def bounded(url):
            async with semaphore:
                return await process(client, url)

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

        print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())