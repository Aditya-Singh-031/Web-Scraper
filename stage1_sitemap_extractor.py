# stage1_sitemap_extractor.py
import asyncio
import gzip
import os
import csv
import tempfile
from lxml import etree
from typing import List, Set
from playwright.async_api import async_playwright

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


# -------------------------
# XML PARSER
# -------------------------
def parse_xml(content: bytes):
    parser = etree.XMLParser(recover=True, ns_clean=True)
    return etree.fromstring(content, parser=parser)


def is_gzip_bytes(b: bytes) -> bool:
    # gzip files start with \x1f\x8b
    return len(b) >= 2 and b[0] == 0x1f and b[1] == 0x8b


def maybe_decompress(url: str, content: bytes) -> bytes:
    # try to detect gz by magic bytes; if gz, decompress; otherwise return as-is
    if url.endswith(".gz") or is_gzip_bytes(content):
        try:
            return gzip.decompress(content)
        except Exception:
            # if decompress fails, raise to let caller handle/log
            raise
    return content


def extract_urls(root) -> List[str]:
    return [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
        if elem.text and "/oem-parts/" in elem.text
    ]


# -------------------------
# DOWNLOAD USING BROWSER
# -------------------------
async def download_via_click(page, url: str, timeout: int = 60_000) -> bytes:
    """
    Try to trigger a browser download by inserting an <a download> and clicking it,
    then save the file to a temporary path and return bytes.
    """
    tmp_path = None
    try:
        # Expect download triggered by the anchor click
        async with page.expect_download(timeout=timeout) as download_info:
            # create and click an anchor that forces download
            await page.evaluate(
                """(u) => {
                    const a = document.createElement('a');
                    a.href = u;
                    a.setAttribute('download', '');
                    a.style.display = 'none';
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                }""",
                url,
            )

        download = await download_info.value
        # create a temp file where to save the download
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp_path = tmp.name
        tmp.close()
        await download.save_as(tmp_path)

        # read bytes
        with open(tmp_path, "rb") as f:
            data = f.read()

        return data

    except Exception as exc:
        raise Exception(f"download_via_click failed: {exc}") from exc

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# -------------------------
# FALLBACK: context.request (still within browser)
# -------------------------
async def fetch_via_context_request(context, url: str) -> bytes:
    """
    Fallback: use the browser context request to get the resource.
    This may still be blocked by server-side protections but works in some cases.
    """
    resp = await context.request.get(url, timeout=60000)
    if resp.status != 200:
        raise Exception(f"status {resp.status}")
    return await resp.body()


# -------------------------
# PROCESS SINGLE SITEMAP
# -------------------------
async def process(page, context, url: str):
    print(f"Processing: {url}")
    # try download-first (mimic user download)
    try:
        content = await download_via_click(page, url)
    except Exception as e:
        print(f"  → download click failed: {e}. Trying context.request fallback...")
        try:
            content = await fetch_via_context_request(context, url)
        except Exception as e2:
            raise Exception(f"Both download and context.request failed: {e2}") from e2

    # now try to decompress if necessary, then parse XML
    try:
        raw = maybe_decompress(url, content)
    except Exception as e:
        # if decompression fails, surface the error including first bytes
        preview = content[:200]
        raise Exception(f"Decompression failed: {e}. preview bytes: {preview!r}") from e

    # parse xml
    try:
        root = parse_xml(raw)
    except Exception as e:
        preview = raw[:500]
        raise Exception(f"XML parse failed: {e}. preview: {preview!r}") from e

    urls = extract_urls(root)
    print(f"  → Extracted {len(urls)} URLs")
    return urls


# -------------------------
# MAIN
# -------------------------
async def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # warm up the session on the homepage (helps cookies / edge behavior)
        try:
            await page.goto("https://www.kia.parts/", timeout=60000)
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f"Warning: homepage warm-up failed: {e}")

        semaphore = asyncio.Semaphore(3)
        results = []

        async def bounded(url):
            async with semaphore:
                try:
                    return await process(page, context, url)
                except Exception as e:
                    print(f"❌ Skipped {url}: {e}")
                    return []

        tasks = [bounded(u) for u in SITEMAPS]
        chunked = await asyncio.gather(*tasks)

        all_urls: Set[str] = set()
        for urls in chunked:
            all_urls.update(urls)

        print(f"\nTotal URLs: {len(all_urls)}")

        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["url"])
            for url in sorted(all_urls):
                writer.writerow([url])

        await browser.close()
        print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())