import re
import time
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

driver = create_driver()
tags = ["先生", "先生(ブルーアーカイブ)", "小鳥遊ホシノ"]

try:
    for tag in tags:
        url = f"https://dic.pixiv.net/a/{quote(tag)}"
        print(f"\nアクセス中: {url}")
        driver.get(url)
        time.sleep(5)
        html  = driver.page_source
        title = driver.title
        print(f"タイトル: {title}")
        blocked = "Just a moment" in html or "Just a moment" in title
        print(f"ブロック: {blocked}")
        m = re.findall(r'"pixivWorkCount":(\d+)', html)
        print(f"pixivWorkCount: {m}")
        time.sleep(3)
finally:
    driver.quit()
