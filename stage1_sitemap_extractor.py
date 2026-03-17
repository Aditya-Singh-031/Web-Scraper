import undetected_chromedriver as uc
import gzip
import csv
import os
import time
from lxml import etree
from typing import List, Set

OUTPUT_FILE = "data/sitemap_urls.csv"

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


def get_driver():
    options = uc.ChromeOptions()
    options.headless = False  # IMPORTANT

    driver = uc.Chrome(options=options)
    driver.get("https://www.kia.parts")

    print("Solve CAPTCHA / wait 5 sec if needed...")
    time.sleep(5)

    return driver


def fetch(driver, url):
    for i in range(5):
        try:
            driver.get(url)
            time.sleep(2)

            content = driver.page_source.encode()

            if "<html" in content[:200].decode().lower() and "urlset" not in content.decode():
                print(f"[retry {i+1}] Blocked page")
                continue

            return content

        except Exception as e:
            print(f"[retry {i+1}] Error:", e)

    raise Exception("Blocked permanently")


def parse_xml(content: bytes):
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(content, parser)


def extract_urls(root) -> List[str]:
    return [
        e.text.strip()
        for e in root.findall(".//{*}loc")
        if e.text and "/oem-parts/" in e.text
    ]


def main():
    os.makedirs("data", exist_ok=True)

    driver = get_driver()

    all_urls: Set[str] = set()

    for url in SITEMAPS:
        print("Processing:", url)

        try:
            content = fetch(driver, url)

            if url.endswith(".gz"):
                try:
                    content = gzip.decompress(content)
                except:
                    print("⚠️ Not gzipped")

            root = parse_xml(content)
            urls = extract_urls(root)

            print(f"→ {len(urls)} URLs")

            all_urls.update(urls)

        except Exception as e:
            print("❌ Failed:", url)

    driver.quit()

    print("\nTotal:", len(all_urls))

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for u in sorted(all_urls):
            writer.writerow([u])

    print("Saved →", OUTPUT_FILE)


if __name__ == "__main__":
    main()