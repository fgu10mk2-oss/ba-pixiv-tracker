# ===================================================
# ブルーアーカイブ キャラクターpixiv R-18率調査ツール
# scraper.py - スクレイピング処理（Selenium版）
# ===================================================

import requests
import re
import time
from urllib.parse import quote
from bs4 import BeautifulSoup


def get_character_list():
    """Wikipediaからキャラクター一覧を取得"""
    url = "https://ja.wikipedia.org/wiki/ブルーアーカイブ_-Blue_Archive-の登場キャラクター"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    def clean_name(raw):
        name = re.sub(r'\[\d+\]', '', raw)
        name = re.sub(r'[「」]', '', name)
        name = re.sub(r'（[^）]*）', '', name)
        name = re.sub(r'\s*\([ぁ-んァ-ン\s]+\)', '', name)
        name = re.sub(
            r'([\u4e00-\u9fff々]+)\s+([\u4e00-\u9fff\u30a0-\u30ff])',
            r'\1\2', name
        )
        name = name.replace('＊', '*')
        return name.strip()

    def has_furigana(raw):
        return (
            bool(re.search(r'（[^）]*）', raw)) or
            bool(re.search(r'\s*\([ぁ-んァ-ン\s]+\)', raw))
        )

    def has_english_bracket(raw):
        return bool(re.search(r'（[^）]*[A-Za-z0-9][^）]*）', raw))

    def has_asterisk(name):
        return '*' in name

    def is_fullname(raw_name, had_furigana, had_english_bracket):
        has_kanji = bool(re.search(r'[\u4e00-\u9fff々]', raw_name))
        if had_english_bracket or has_asterisk(raw_name) or not has_kanji or not had_furigana:
            return False
        return True

    FORCE_DUAL = {"アロナ"}

    characters = []
    current_h2 = ""
    current_h3 = ""

    for tag in soup.find_all(["h2", "h3", "dt"]):
        text = tag.get_text(strip=True)
        if tag.name == "h2":
            if text in ["目次", "脚注", "関連項目", "外部リンク"]:
                continue
            current_h2 = text
            current_h3 = ""
        elif tag.name == "h3":
            current_h3 = text
        elif tag.name == "dt":
            if any(x in text for x in ["漫画", "アニメ", "ゲーム開発"]):
                continue
            had_furigana        = has_furigana(text)
            had_english_bracket = has_english_bracket(text)
            raw_name            = clean_name(text)
            if not raw_name:
                continue
            if raw_name in FORCE_DUAL or not is_fullname(raw_name, had_furigana, had_english_bracket):
                tags = [raw_name, f"{raw_name}(ブルーアーカイブ)"]
            else:
                tags = [raw_name]
            for tag_name in tags:
                characters.append({
                    "name":   tag_name,
                    "school": current_h2,
                    "club":   current_h3,
                })

    return characters


def create_driver():
    """Seleniumドライバーを作成"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

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

    try:
        # GitHub Actions環境（chromiumがPATHにある）
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    except Exception:
        driver = webdriver.Chrome(options=options)

    return driver


def get_total_from_daihyakka(driver, tag: str) -> int:
    """Seleniumで大百科からR-18含む全件数を取得"""
    try:
        url = f"https://dic.pixiv.net/a/{quote(tag)}"
        driver.get(url)
        time.sleep(0.1)
        html = driver.page_source
        m = re.findall(r'"pixivWorkCount":(\d+)', html)
        return int(m[0]) if m else 0
    except Exception as e:
        print(f"[ERROR] 大百科 {tag}: {e}")
        return 0


def get_kenzen_from_pixiv(tag: str) -> int:
    """requestsでpixiv本体から全年齢件数を取得"""
    try:
        url = f"https://www.pixiv.net/tags/{quote(tag)}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        illust_match = re.findall(r'小説。([\d,]+)件のイラスト', r.text)
        novel_match  = re.findall(r'イラスト、([\d,]+)件の小説が投稿さ', r.text)
        if not illust_match:
            return 0
        illust = int(illust_match[0].replace(",", ""))
        novel  = int(novel_match[0].replace(",", "")) if novel_match else 0
        return illust + novel
    except Exception as e:
        print(f"[ERROR] pixiv {tag}: {e}")
        return 0


def run_scraping(progress_callback=None, status_callback=None):
    """
    スクレイピングのメイン処理
    戻り値: 結果の行リスト（ヘッダー含む）
    """
    if status_callback:
        status_callback("Wikipediaからキャラクター名簿を取得中...")

    characters  = get_character_list()
    total_count = len(characters)

    if status_callback:
        status_callback(f"キャラクター {total_count} 件取得完了。Seleniumドライバー起動中...")

    driver = create_driver()

    output_rows = [["学校", "部活", "名前", "全件数", "R-18", "全年齢", "R-18率"]]

    try:
        for i, chara in enumerate(characters):
            name   = chara["name"]
            school = chara["school"]
            club   = chara["club"]

            # 大百科からR-18含む全件数（Selenium）
            total = get_total_from_daihyakka(driver, name)
            time.sleep(0.1)

            # pixiv本体から全年齢件数（requests）
            kenzen = get_kenzen_from_pixiv(name)
            time.sleep(0.1)

            r18   = total - kenzen
            ratio = round(1 - (kenzen / total), 4) if total > 0 else 0.0

            row = [school, club, name, total, r18, kenzen, ratio]
            output_rows.append(row)

            if progress_callback:
                progress_callback((i + 1) / total_count)

            if status_callback:
                status_callback(
                    f"[{i+1}/{total_count}] {name} | "
                    f"全:{total} 全年齢:{kenzen} "
                    f"R-18:{r18} R-18率:{ratio*100:.1f}%"
                )

    finally:
        driver.quit()

    return output_rows
