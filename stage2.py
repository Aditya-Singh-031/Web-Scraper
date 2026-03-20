import undetected_chromedriver as uc
import csv
import time
import pandas as pd # pyright: ignore[reportMissingModuleSource]

INPUT_FILE = "data/sitemap_urls.csv"
OUTPUT_FILE = "data/products_sample.csv"

# -------------------------
# DRIVER
# -------------------------
def get_driver():
    options = uc.ChromeOptions()
    options.headless = False

    driver = uc.Chrome(options=options)
    driver.get("https://www.kia.parts")
    time.sleep(5)

    return driver


# -------------------------
# EXTRACT
# -------------------------
import re

def extract_product(driver, url):
    driver.get(url)
    time.sleep(2)

    try:
        name = driver.find_element("xpath", "//h1").text
    except:
        name = ""

    try:
        price = driver.find_element("xpath", "//span[contains(@class,'price')]").text
    except:
        price = ""

    # ✅ Extract part number from title
    part_number = ""
    match = re.search(r"\((.*?)\)", name)
    if match:
        part_number = match.group(1)

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

    urls = df["url"].head(100)  # 🔥 sample first

    driver = get_driver()

    results = []

    for i, url in enumerate(urls):
        print(f"{i+1}/100 → {url}")

        try:
            data = extract_product(driver, url)
            results.append(data)
        except Exception as e:
            print("❌ error:", e)

    try:
        driver.quit()
    except:
        pass

    pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False)

    print("Saved →", OUTPUT_FILE)


if __name__ == "__main__":
    main()