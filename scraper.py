# ===================================================
# ブルーアーカイブ キャラクターpixiv R-18率調査ツール
# scraper.py - スクレイピング処理
# ===================================================

import requests
from bs4 import BeautifulSoup
import re
import time
import csv
import os
from urllib.parse import quote


def get_character_list():
    """
    Wikipediaのブルーアーカイブキャラクターページからキャラクターのリストを作成する関数
    """
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

            school = current_h2
            club   = current_h3

            if raw_name in FORCE_DUAL or not is_fullname(raw_name, had_furigana, had_english_bracket):
                tags = [raw_name, f"{raw_name}(ブルーアーカイブ)"]
            else:
                tags = [raw_name]

            for tag_name in tags:
                characters.append({
                    "name":   tag_name,
                    "school": school,
                    "club":   club,
                })

    return characters


def check(tag: str) -> dict:
    """
    指定されたpixivタグの全件数・全年齢件数・R-18件数・R-18率を取得する関数
    """
    result = {"total": None, "r18": None, "kenzen": None, "ratio": None}

    try:
        url = "https://www.pixiv.net/tags/" + quote(tag)
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

        illust_match = re.findall(r'小説。([\d,]+)件のイラスト', response.text)
        novel_match  = re.findall(r'イラスト、([\d,]+)件の小説が投稿さ', response.text)

        if not illust_match:
            kenzen = 0
        else:
            illust = int(illust_match[0].replace(",", ""))
            novel  = int(novel_match[0].replace(",", "")) if novel_match else 0
            kenzen = illust + novel

        time.sleep(2)

        dic_url = f"https://dic.pixiv.net/a/{quote(tag)}"
        dic_response = requests.get(dic_url, headers={"User-Agent": "Mozilla/5.0"})

        all_match = re.findall(r'"pixivWorkCount":(\d+)', dic_response.text)

        if not all_match:
            total = 0
        else:
            total = int(all_match[0])

        r18   = total - kenzen
        ratio = round(1 - (kenzen / total), 4) if total > 0 else 0.0

        time.sleep(2)

        return {"total": total, "r18": r18, "kenzen": kenzen, "ratio": ratio}

    except Exception as e:
        print(f"[ERROR] {tag}: {e}")
        return result


def run_scraping(progress_callback=None, status_callback=None):
    """
    スクレイピングのメイン処理
    引数:
        progress_callback: 進捗率(0.0~1.0)を受け取るコールバック関数
        status_callback:   状況テキストを受け取るコールバック関数
    戻り値: 結果の行リスト（ヘッダー含む）
    """
    if status_callback:
        status_callback("Wikipediaからキャラクター名簿を取得中...")

    characters = get_character_list()
    total_count = len(characters)

    if status_callback:
        status_callback(f"キャラクター {total_count} 件取得完了。pixivデータ取得中...")

    output_rows = [["学校", "部活", "名前", "全件数", "R-18", "全年齢", "R-18率"]]

    for i, chara in enumerate(characters):
        name   = chara["name"]
        school = chara["school"]
        club   = chara["club"]

        stats = check(name)

        row = [school, club, name, stats["total"], stats["r18"], stats["kenzen"], stats["ratio"]]
        output_rows.append(row)

        if progress_callback:
            progress_callback((i + 1) / total_count)

        if status_callback:
            if stats["total"] is None:
                status_callback(f"[{i+1}/{total_count}] {name} | 取得失敗")
            else:
                status_callback(
                    f"[{i+1}/{total_count}] {name} | "
                    f"全:{stats['total']} 全年齢:{stats['kenzen']} "
                    f"R-18:{stats['r18']} R-18率:{stats['ratio']*100:.1f}%"
                )

    return output_rows
