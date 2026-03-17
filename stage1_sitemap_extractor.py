import requests
import gzip
import csv
import os
import time
from lxml import etree
from typing import List, Set

OUTPUT_FILE = "data/sitemap_urls.csv"

# 🔥 IMPORTANT: ADD cf_clearance HERE
COOKIES = {
    "_cfuvid": "eIJnFzoyMy8dl7LLl1kxM3i7NOnlkHxMBrXMS13wvZU-1773572410190-0.0.1.1-604800000",
    "_dd_s": "isExpired=1&aid=9321b927-1d39-45b4-ade1-e6193aaa4a38",
    "_sp_id.b10b": "8d8a8c3d1314433c.1773572407.4.1773713982.1773678094",
    "vid": "2f6804168ae1e55015cf92d38376e58c",

    # 🚨 YOU MUST ADD THIS
    # "cf_clearance": "PASTE_FROM_BROWSER"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.kia.parts/",
    "Connection": "keep-alive",
}

# -------------------------
# SITEMAPS
# -------------------------
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
# FETCH
# -------------------------
def fetch(url: str) -> bytes:
    for attempt in range(5):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                cookies=COOKIES,
                timeout=30
            )

            if response.status_code != 200:
                print(f"[retry {attempt+1}] {url} → status {response.status_code}")
                time.sleep(2)
                continue

            content = response.content

            # 🚨 Detect Cloudflare block (HTML instead of XML/GZ)
            if content[:100].lower().startswith(b"<!doctype html") or b"<html" in content[:200].lower():
                print(f"[retry {attempt+1}] {url} → Blocked (HTML)")
                time.sleep(3)
                continue

            return content

        except Exception as e:
            print(f"[retry {attempt+1}] {url} → {e}")
            time.sleep(2)

    raise Exception(f"Failed permanently: {url}")


# -------------------------
# XML PARSER
# -------------------------
def parse_xml(content: bytes):
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(content, parser)


def extract_urls(root) -> List[str]:
    return [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
        if elem.text and "/oem-parts/" in elem.text
    ]


# -------------------------
# PROCESS
# -------------------------
def process(url):
    print(f"Processing: {url}")

    content = fetch(url)

    # Handle gzip safely
    if url.endswith(".gz"):
        try:
            content = gzip.decompress(content)
        except:
            raise Exception("Invalid gzip (likely still blocked)")

    root = parse_xml(content)
    urls = extract_urls(root)

    print(f"→ Extracted {len(urls)} URLs")
    return urls


# -------------------------
# MAIN
# -------------------------
def main():
    os.makedirs("data", exist_ok=True)

    all_urls: Set[str] = set()

    for url in SITEMAPS:
        try:
            urls = process(url)
            all_urls.update(urls)

            # 🔥 small delay (important for not getting blocked again)
            time.sleep(1.5)

        except Exception as e:
            print(f"❌ {e}")

    print(f"\nTotal URLs: {len(all_urls)}")

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for url in sorted(all_urls):
            writer.writerow([url])

    print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()