# ===================================================
# ブルーアーカイブ キャラクターpixiv R-18率調査ツール
# scraper.py - スクレイピング処理（Selenium版・1件ごとリセット）
# ===================================================

import requests
import re
import time
import random
from datetime import datetime, timedelta
from urllib.parse import quote
from bs4 import BeautifulSoup

PAGE_LIMIT    = 10
EXCLUDE_WORDS = ["生誕祭", "×", "(ブルーアーカイブ)", "ブルアカ"]
UPDATE_LIMIT  = 1    # 1回の実行で更新するキャラ数（デフォルト）
STALE_HOURS   = 24   # 何時間経過したら更新対象とみなすか

# 先生の別衣装は例外処理（固定リスト）
SENSEI_COSTUMES = ["アニメ先生(ブルーアーカイブ)", "便利屋先生", "開発部先生"]


class BlockedError(Exception):
    """リトライしてもブロックされた時に送出する例外"""
    def __init__(self, message, rows, completed, total):
        super().__init__(message)
        self.rows      = rows
        self.completed = completed
        self.total     = total


# ===================================================
# Wikipedia キャラ名簿取得
# ===================================================

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

    def is_fullname(raw_name, had_furigana, had_english_bracket):
        has_kanji = bool(re.search(r'[\u4e00-\u9fff々]', raw_name))
        if had_english_bracket or '*' in raw_name or not has_kanji or not had_furigana:
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
            fullname = is_fullname(raw_name, had_furigana, had_english_bracket)
            characters.append({
                "name":    raw_name,
                "school":  current_h2,
                "club":    current_h3,
                "is_full": fullname,
            })

    return characters


# ===================================================
# 別衣装タグ取得（Selenium版）
# ===================================================

def is_costume_tag(char: str, tag: str) -> bool:
    if not tag.startswith(f"{char}("):
        return False
    for word in EXCLUDE_WORDS:
        if word in tag:
            return False
    return True


def selenium_get(url: str, retry: bool = False) -> str:
    """
    Seleniumで指定URLのpage_sourceを取得して返す（1回ごとドライバー起動・終了）
    Cloudflareブロック時: retry=Falseなら15秒待ってリトライ
                          retry=Trueなら空文字を返す
    """
    driver = create_driver()
    try:
        driver.get(url)
        time.sleep(random.uniform(7.0, 10.0))
        html  = driver.page_source
        title = driver.title
        if "Just a moment" in html or "Just a moment" in title:
            if not retry:
                print(f"[BLOCK→RETRY] {url}: ブロック検知、15秒待ってリトライします", flush=True)
                driver.quit()
                time.sleep(15)
                return selenium_get(url, retry=True)
            else:
                print(f"[BLOCK→FAIL] {url}: リトライもブロックされました", flush=True)
                return ""
        return html
    except Exception as e:
        print(f"[ERROR] selenium_get {url}: {e}", flush=True)
        if not retry:
            print(f"[RETRY] 20秒待ってリトライします", flush=True)
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(20)
            return selenium_get(url, retry=True)
        return ""
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def is_ba_page(tag: str) -> bool:
    """articleタグの本文テキストにブルーアーカイブの言及があるか（Selenium版）"""
    url  = f"https://dic.pixiv.net/a/{quote(tag)}"
    html = selenium_get(url)
    if not html:
        return False
    soup    = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article")
    if not article:
        return False
    return "ブルーアーカイブ" in article.get_text()


def _get_search_count(soup) -> int:
    info = soup.select_one("#search-title .info")
    if info:
        m = re.search(r'([\d,]+)件', info.text)
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


def _fetch_search_soup(query: str, page: int) -> BeautifulSoup:
    """大百科検索ページをSeleniumで取得してBeautifulSoupを返す"""
    url  = f"https://dic.pixiv.net/search?query={quote(query)}&page={page}"
    html = selenium_get(url)
    return BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")


def _fetch_articles(query: str, max_pages: int) -> dict:
    """検索結果から {タグ名: 作品数} を取得（Selenium版）"""
    articles = {}
    for page in range(1, max_pages + 1):
        soup  = _fetch_search_soup(query, page)
        found = 0
        for article in soup.select("article"):
            h2      = article.select_one("h2 a")
            work_li = next((li for li in article.select("ul.data li") if "作品数" in li.text), None)
            if h2 and work_li:
                title = h2.text.strip()
                count = int(work_li.text.replace("作品数:", "").replace(",", "").strip())
                articles[title] = count
                found += 1
        if found == 0:
            break
    return articles


def resolve_main_tag(char: str, is_full: bool) -> str:
    """
    メインタグを決定する（Selenium版）
    - フルネームあり → キャラ名そのまま
    - フルネームなし → 大百科検索で「キャラ名(ブルーアーカイブ)」完全一致があればそれ、なければキャラ名そのまま
    """
    if is_full:
        return char

    ba_tag = f"{char}(ブルーアーカイブ)"
    soup   = _fetch_search_soup(ba_tag, 1)
    for article in soup.select("article"):
        h2 = article.select_one("h2 a")
        if h2 and h2.text.strip() == ba_tag:
            print(f"[TAG] {char} → {ba_tag} (BA付き確認)", flush=True)
            return ba_tag

    print(f"[TAG] {char} → {char} (BA付きなし)", flush=True)
    return char


def get_costume_tags(char: str, is_full: bool) -> list:
    """
    キャラクターの別衣装タグ一覧を返す（Selenium版）
    先生は例外処理（固定リスト）
    - フルネームあり   → キャラ名そのままで検索
    - フルネームなし   → キャラ名(ブルーアーカイブ)で検索、結果なければキャラ名で再検索
    """
    if char == "先生":
        return SENSEI_COSTUMES

    if is_full:
        query = char
    else:
        ba_query = f"{char}(ブルーアーカイブ)"
        print(f"[COSTUME_SEARCH] {char}: BA付きクエリで検索中...", flush=True)
        soup_ba  = _fetch_search_soup(ba_query, 1)
        total_ba = _get_search_count(soup_ba)
        print(f"[COSTUME_SEARCH] {char}: BA付き検索結果 {total_ba} 件", flush=True)
        query    = ba_query if total_ba > 0 else char

    print(f"[COSTUME_SEARCH] {char}: query={query} で検索開始", flush=True)

    # 1ページ目で件数確認
    soup1  = _fetch_search_soup(query, 1)
    total  = _get_search_count(soup1)
    pages  = min(PAGE_LIMIT, max(1, -(-total // 12))) if total > 0 else 1
    print(f"[COSTUME_SEARCH] {char}: 検索結果 {total} 件 / {pages} ページ", flush=True)

    # 1ページ目の結果を収集
    articles = {}
    for article in soup1.select("article"):
        h2      = article.select_one("h2 a")
        work_li = next((li for li in article.select("ul.data li") if "作品数" in li.text), None)
        if h2 and work_li:
            title = h2.text.strip()
            count = int(work_li.text.replace("作品数:", "").replace(",", "").strip())
            articles[title] = count

    if pages > 1:
        for page in range(2, pages + 1):
            try:
                soup_p = _fetch_search_soup(query, page)
                found  = 0
                for article in soup_p.select("article"):
                    h2      = article.select_one("h2 a")
                    work_li = next((li for li in article.select("ul.data li") if "作品数" in li.text), None)
                    if h2 and work_li:
                        title = h2.text.strip()
                        count = int(work_li.text.replace("作品数:", "").replace(",", "").strip())
                        articles[title] = count
                        found += 1
                if found == 0:
                    break
            except Exception as e:
                print(f"[WARN] get_costume_tags {char} page={page} スキップ: {e}", flush=True)
                continue

    matched = {t: c for t, c in articles.items() if char in t}
    print(f"[COSTUME_SEARCH] {char}: matched候補 {list(matched.keys())}", flush=True)

    costumes = []
    for tag in matched:
        if not is_costume_tag(char, tag):
            print(f"[COSTUME_SKIP] {tag}: is_costume_tag=False", flush=True)
            continue
        print(f"[COSTUME_CHECK] {tag}: is_ba_page確認中...", flush=True)
        if is_ba_page(tag):
            costumes.append(tag)
            print(f"[COSTUME] {char} → {tag}", flush=True)
        else:
            print(f"[COSTUME_SKIP] {tag}: is_ba_page=False", flush=True)

    return costumes


# ===================================================
# 更新対象キャラ選定
# ===================================================

def select_targets(characters: list, existing: dict, limit: int = UPDATE_LIMIT) -> list:
    """
    Wikiのキャラ一覧を先頭から走査し、
    最終更新が24時間以上経過（またはCSV未収録・日時なし）のキャラを
    上からlimit件選んで返す
    """
    threshold = datetime.now() - timedelta(hours=STALE_HOURS)
    targets   = []

    for chara in characters:
        if len(targets) >= limit:
            break

        name = chara["name"]
        row  = existing.get(name)

        if row is None:
            # CSV未収録 → 対象
            targets.append(chara)
            continue

        updated_str = row.get("最終更新日時", "")
        if not updated_str:
            # 日時なし → 対象
            targets.append(chara)
            continue

        try:
            updated = datetime.strptime(updated_str, "%Y-%m-%d %H:%M:%S")
            if updated < threshold:
                targets.append(chara)
        except ValueError:
            # パース失敗 → 対象
            targets.append(chara)

    return targets


# ===================================================
# Selenium（大百科）
# ===================================================

def create_driver():
    """Seleniumドライバーを新規作成"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    return driver


def fetch_one(tag: str, retry: bool = False) -> int:
    """
    1件だけドライバーを起動して大百科から取得し終了する
    ブロックされた場合: retry=Falseなら15秒待ってリトライ
                        retry=Trueなら -1 を返す（完全失敗）
    """
    driver = create_driver()
    try:
        url = f"https://dic.pixiv.net/a/{quote(tag)}"
        driver.get(url)
        time.sleep(random.uniform(7.0, 10.0))
        html  = driver.page_source
        title = driver.title

        if "Just a moment" in html or "Just a moment" in title:
            if not retry:
                print(f"[BLOCK→RETRY] {tag}: ブロック検知、15秒待ってリトライします", flush=True)
                driver.quit()
                time.sleep(15)
                return fetch_one(tag, retry=True)
            else:
                print(f"[BLOCK→FAIL] {tag}: リトライもブロックされました", flush=True)
                return -1

        m = re.findall(r'"pixivWorkCount":(\d+)', html)
        return int(m[0]) if m else 0

    except Exception as e:
        print(f"[ERROR] fetch_one {tag}: {e}", flush=True)
        if not retry:
            print(f"[RETRY] 20秒待ってリトライします", flush=True)
            try:
                driver.quit()
            except Exception:
                pass
            time.sleep(20)
            return fetch_one(tag, retry=True)
        return -1

    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ===================================================
# pixiv 全年齢件数取得（requests）
# ===================================================

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
        print(f"[ERROR] pixiv {tag}: {e}", flush=True)
        return 0


# ===================================================
# メイン処理
# ===================================================

def run_scraping(
    existing=None,
    limit=UPDATE_LIMIT,
    progress_callback=None,
    status_callback=None,
    row_callback=None,
    characters_callback=None
):
    """
    スクレイピングのメイン処理
    existing: {名前: {列名: 値}} の既存CSVデータ（Noneなら空扱い）
    limit:    1回の実行で更新するキャラ数
    リトライしてもブロックされた場合はBlockedErrorを送出
    正常完了時は (rows, completed, total) を返す
    """
    if existing is None:
        existing = {}

    if status_callback:
        status_callback("Wikipediaからキャラクター名簿を取得中...")

    characters = get_character_list()

    if characters_callback:
        characters_callback(characters)

    # 更新対象キャラを選定
    targets = select_targets(characters, existing, limit=limit)

    if status_callback:
        status_callback(
            f"キャラクター {len(characters)} 件取得完了。"
            f"更新対象: {len(targets)} 件。別衣装タグを調査中..."
        )

    # 各キャラのメイン＋別衣装タグを展開
    entries = []
    for chara in targets:
        name    = chara["name"]
        school  = chara["school"]
        club    = chara["club"]
        is_full = chara["is_full"]

        try:
            main_tag = resolve_main_tag(name, is_full)
        except Exception as e:
            print(f"[ERROR] resolve_main_tag {name}: {e}", flush=True)
            main_tag = name

        entries.append({"name": name, "tag": main_tag, "school": school, "club": club})

        try:
            costumes = get_costume_tags(name, is_full)
            for ctag in costumes:
                entries.append({"name": name, "tag": ctag, "school": school, "club": club})
        except Exception as e:
            print(f"[ERROR] get_costume_tags {name}: {e}", flush=True)

    total_count = len(entries)

    if status_callback:
        status_callback(f"処理対象タグ {total_count} 件（メイン＋別衣装）。取得開始...")

    output_rows = [["名前", "タグ名", "学校", "部活", "全件数", "全年齢", "R-18", "R-18率", "最終更新日時"]]
    completed   = 0

    for i, entry in enumerate(entries):
        name   = entry["name"]
        tag    = entry["tag"]
        school = entry["school"]
        club   = entry["club"]

        # 大百科から全件数取得（Selenium・1件ごとリセット）
        total = fetch_one(tag)

        if total == -1:
            msg = (
                f"[BLOCKED] {i+1}件目 ({tag}) でリトライ後もブロックされました。"
                f"{completed}件処理済みで中断します。"
            )
            print(msg, flush=True)
            if status_callback:
                status_callback(msg)
            raise BlockedError(msg, output_rows, completed, total_count)

        time.sleep(random.uniform(1.0, 2.0))

        kenzen  = get_kenzen_from_pixiv(tag)
        time.sleep(random.uniform(1.0, 2.0))

        r18     = total - kenzen
        ratio   = round(1 - (kenzen / total), 4) if total > 0 else 0.0
        updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row = [name, tag, school, club, total, kenzen, r18, ratio, updated]
        output_rows.append(row)

        if row_callback:
            row_callback(entry, row)
        completed += 1

        if progress_callback:
            progress_callback((i + 1) / total_count)

        if status_callback:
            status_callback(
                f"[{i+1}/{total_count}] {tag} | "
                f"全:{total} 全年齢:{kenzen} "
                f"R-18:{r18} R-18率:{ratio*100:.1f}%"
            )

    return output_rows, completed, total_count
