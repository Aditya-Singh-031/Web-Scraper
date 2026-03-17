import undetected_chromedriver as uc
import gzip
import csv
import os
import time
from lxml import etree
from typing import List, Set

DOWNLOAD_DIR = os.path.abspath("downloads")
OUTPUT_FILE = "data/sitemap_urls.csv"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
# DRIVER
# -------------------------
def get_driver():
    options = uc.ChromeOptions()

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }

    options.add_experimental_option("prefs", prefs)
    options.headless = False

    driver = uc.Chrome(options=options)

    driver.get("https://www.kia.parts")
    print("Wait 5 sec for Cloudflare...")
    time.sleep(5)

    return driver


# -------------------------
# DOWNLOAD
# -------------------------
def download_files(driver):
    for url in SITEMAPS:
        print("Downloading:", url)
        driver.get(url)
        time.sleep(2)  # allow download


# -------------------------
# PARSE FILES
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


def process_downloads():
    all_urls: Set[str] = set()

    for file in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, file)

        print("Processing file:", file)

        try:
            with open(path, "rb") as f:
                content = f.read()

            if file.endswith(".gz"):
                content = gzip.decompress(content)

            root = parse_xml(content)
            urls = extract_urls(root)

            print(f"→ {len(urls)} URLs")

            all_urls.update(urls)

        except Exception as e:
            print("❌ Failed:", file, e)

    return all_urls


# -------------------------
# MAIN
# -------------------------
def main():
    os.makedirs("data", exist_ok=True)

    driver = get_driver()

    # Step 1: download all files
    download_files(driver)

    driver.quit()

    print("\nParsing downloaded files...")

    # Step 2: parse files
    all_urls = process_downloads()

    print("\nTotal URLs:", len(all_urls))

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for url in sorted(all_urls):
            writer.writerow([url])

    print("Saved →", OUTPUT_FILE)


if __name__ == "__main__":
    main()