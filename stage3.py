import undetected_chromedriver as uc
import pandas as pd
import time

INPUT_FILE = "data/sitemap_urls.csv"
OUTPUT_FILE = "data/products_with_fitment.csv"


# -------------------------
# DRIVER
# -------------------------
def get_driver():
    options = uc.ChromeOptions()
    options.headless = False

    driver = uc.Chrome(options=options)
    driver.get("https://www.kia.parts")

    print("Waiting for Cloudflare...")
    time.sleep(5)

    return driver


# -------------------------
# EXTRACT BASIC
# -------------------------
def extract_basic(driver):
    try:
        name = driver.find_element("xpath", "//h1").text.strip()
    except:
        name = ""

    try:
        price = driver.find_element(
            "xpath", "//span[contains(@class,'price')]"
        ).text.strip()
    except:
        price = ""

    return name, price


# -------------------------
# EXTRACT FITMENT (CORE)
# -------------------------
def extract_fitment(driver):
    fitment_list = []

    try:
        # Scroll to load section
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

        # Try common fitment container
        elements = driver.find_elements(
            "xpath", "//div[contains(text(),'Fits')]/following::*//li"
        )

        for el in elements:
            text = el.text.strip()
            if text:
                fitment_list.append(text)

        # Fallback (some pages)
        if not fitment_list:
            elements = driver.find_elements("xpath", "//li[contains(text(),'Kia')]")
            for el in elements:
                text = el.text.strip()
                if text:
                    fitment_list.append(text)

    except Exception as e:
        print("fitment error:", e)

    return " | ".join(fitment_list)


# -------------------------
# MAIN
# -------------------------
def main():
    df = pd.read_csv(INPUT_FILE)
    urls = df["url"].head(50)  # start smaller

    driver = get_driver()

    results = []

    for i, url in enumerate(urls):
        print(f"{i+1}/50 → {url}")

        try:
            driver.get(url)
            time.sleep(2)

            name, price = extract_basic(driver)
            fitment = extract_fitment(driver)

            results.append({
                "url": url,
                "name": name,
                "price": price,
                "fitment": fitment
            })

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