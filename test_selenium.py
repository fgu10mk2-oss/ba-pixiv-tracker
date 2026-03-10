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

tags = ["先生", "先生(ブルーアーカイブ)", "小鳥遊ホシノ", "ホシノ(ブルーアーカイブ)"]
driver = create_driver()

try:
    for i, tag in enumerate(tags):
        url = f"https://dic.pixiv.net/a/{quote(tag)}"
        print(f"\n[{i+1}] アクセス中: {url}")
        driver.get(url)
        time.sleep(6)
        html  = driver.page_source
        title = driver.title
        blocked = "Just a moment" in html or "Just a moment" in title
        print(f"タイトル: {title}")
        print(f"ブロック: {blocked}")
        m = re.findall(r'"pixivWorkCount":(\d+)', html)
        print(f"pixivWorkCount: {m}")

        # ブロックされたらドライバーを作り直して15秒待機
        if blocked:
            print("→ ドライバーをリセットして15秒待機...")
            driver.quit()
            time.sleep(15)
            driver = create_driver()
        else:
            time.sleep(4)
finally:
    driver.quit()
