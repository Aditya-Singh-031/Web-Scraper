import undetected_chromedriver as uc
import pandas as pd # pyright: ignore[reportMissingModuleSource]
import time
import re

INPUT_FILE = "data/sitemap_urls.csv"
OUTPUT_FILE = "data/products_sample.csv"

# -------------------------
# DRIVER
# -------------------------
def get_driver():
    options = uc.ChromeOptions()
    options.headless = False  # keep visible for stability

    driver = uc.Chrome(options=options)

    driver.get("https://www.kia.parts")
    print("Waiting for Cloudflare...")
    time.sleep(5)

    return driver


# -------------------------
# HELPERS
# -------------------------
def extract_part_number_from_title(title: str) -> str:
    """
    Extract text inside last parentheses
    Example:
    "0 Deg Meg Nozzle - Kia (WURTH-1799140030)"
    → WURTH-1799140030
    """
    match = re.search(r"\(([^()]+)\)\s*$", title)
    return match.group(1) if match else ""


# -------------------------
# EXTRACT
# -------------------------
def extract_product(driver, url):
    driver.get(url)
    time.sleep(2)

    # NAME (solid)
    try:
        name = driver.find_element("xpath", "//h1").text.strip()
    except:
        name = ""

    # PRICE (solid fallback)
    try:
        price = driver.find_element(
            "xpath", "//span[contains(@class,'price')]"
        ).text.strip()
    except:
        price = ""

    # PART NUMBER (FIXED)
    part_number = extract_part_number_from_title(name)

    return {
        "url": url,
        "name": name,
        "price": price,
        "part_number": part_number,
    }


# -------------------------
# MAIN
# -------------------------
def main():
    df = pd.read_csv(INPUT_FILE)

    urls = df["url"].head(100)  # sample first

    driver = get_driver()

    results = []

    for i, url in enumerate(urls):
        print(f"{i+1}/100 → {url}")

        try:
            data = extract_product(driver, url)
            results.append(data)
        except Exception as e:
            print("❌ error:", e)

    # CLEAN QUIT (fix WinError 6)
    try:
        driver.quit()
    except:
        pass

    pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False)

    print("Saved →", OUTPUT_FILE)


if __name__ == "__main__":
    main()