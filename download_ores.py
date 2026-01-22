import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://forge-roblox.fandom.com"
SEARCH_URL = "https://forge-roblox.fandom.com/wiki/Special:Search?query=ore&scope=internal"

OUTPUT_DIR = "ores"
os.makedirs(OUTPUT_DIR, exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0"
}

def get_ore_pages():
    print("Fetching ore list...")
    r = requests.get(SEARCH_URL, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    links = set()
    for a in soup.select("a.unified-search__result__title"):
        href = a.get("href")
        if href and "/wiki/" in href:
            links.add(urljoin(BASE_URL, href))

    print(f"Found {len(links)} ore pages")
    return links

def download_ore_image(page_url):
    r = requests.get(page_url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    title = soup.find("h1")
    if not title:
        return

    ore_name = title.text.strip().replace("/", "_")
    img = soup.select_one(".pi-image-thumbnail")

    if not img:
        print(f"❌ No image for {ore_name}")
        return

    img_url = img.get("src")
    if not img_url:
        return

    img_data = requests.get(img_url).content
    path = os.path.join(OUTPUT_DIR, f"{ore_name}.png")

    with open(path, "wb") as f:
        f.write(img_data)

    print(f"✅ Downloaded {ore_name}")

def main():
    pages = get_ore_pages()
    for page in pages:
        download_ore_image(page)

if __name__ == "__main__":
    main()
