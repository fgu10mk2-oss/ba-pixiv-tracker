import re
import time
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

tag = "小鳥遊ホシノ"

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

try:
    url = f"https://dic.pixiv.net/a/{quote(tag)}"
    print("アクセス中:", url)
    driver.get(url)
    time.sleep(5)

    html = driver.page_source
    print("タイトル:", driver.title)
    print("HTML先頭300字:", html[:300])

    m = re.findall(r'"pixivWorkCount":(\d+)', html)
    print("pixivWorkCount:", m)

finally:
    driver.quit()
