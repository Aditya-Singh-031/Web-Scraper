import requests
import gzip
import csv
import os
from lxml import etree
from typing import List, Set

OUTPUT_FILE = "data/sitemap_urls.csv"

# 🔥 YOUR REAL COOKIES (CLEANED + MERGED)
COOKIES = {
    "cf_clearance": "UaQp4rBrx4pKQVEweg1JQTHCteM5yYXt6cD_gKDu0CU-1773757518-1.2.1.1-H9xE71rep.2wk0W8er4QYoXXUsEsOorAEAi72DpiYiYT.lb1WjMyflzf6eUe0weziZbLZ1AQ1RThKGQGrjW2GtWz.anRDcGuZM5HBihMefcUh3g4kalQpbMryTcTqOQkK1q6UWPB8F7hRqd5_Z689k7lKiyEAUJYk4coLfPC96gSrGOStx9GQ010zgsxp9.6lo08EDtullvtC2j856ljgF.4zmttI0gQYaQPmsNGaUdWuxr9njQVL5GMWYcCDrF8me5E9UApVg47V6hov.QpYGBEuyoEtH_VAr5mtfxmWKUGveF0o0t0sSufmfwisM3YjPk_t9khnO8OLXpFBORdfw",
    "_cfuvid": "eIJnFzoyMy8dl7LLl1kxM3i7NOnlkHxMBrXMS13wvZU-1773572410190-0.0.1.1-604800000",
    "_dd_s": "isExpired=1&aid=9321b927-1d39-45b4-ade1-e6193aaa4a38",
    "_sp_id.b10b": "8d8a8c3d1314433c.1773572407.4.1773713982.1773678094",
    "vid": "2f6804168ae1e55015cf92d38376e58c",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.kia.parts/",
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
    for i in range(5):
        try:
            r = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=30)

            if r.status_code != 200:
                print(f"[retry {i+1}] {url} → status {r.status_code}")
                continue

            # 🚨 detect bot block
            if b"<html" in r.content[:200].lower():
                print(f"[retry {i+1}] {url} → Blocked (HTML returned)")
                continue

            return r.content

        except Exception as e:
            print(f"[retry {i+1}] {url} → {e}")

    raise Exception("Blocked permanently")


# -------------------------
# XML PARSER
# -------------------------
def parse_xml(content: bytes):
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(content, parser)


def extract_urls(root) -> List[str]:
    return [
        e.text.strip()
        for e in root.findall(".//{*}loc")
        if e.text and "/oem-parts/" in e.text
    ]


# -------------------------
# MAIN
# -------------------------
def main():
    os.makedirs("data", exist_ok=True)

    all_urls: Set[str] = set()

    for url in SITEMAPS:
        print(f"Processing: {url}")

        try:
            content = fetch(url)

            # 🔥 handle gzip ONLY if real gzip
            if url.endswith(".gz"):
                try:
                    content = gzip.decompress(content)
                except:
                    print("⚠️ Not gzipped, using raw content")

            root = parse_xml(content)
            urls = extract_urls(root)

            print(f"→ Extracted {len(urls)} URLs")

            all_urls.update(urls)

        except Exception as e:
            print(f"❌ Failed permanently: {url}")

    print(f"\nTotal URLs: {len(all_urls)}")

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for url in sorted(all_urls):
            writer.writerow([url])

    print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()