# ===================================================
# GitHub Actions から呼び出されるスクレイピング実行スクリプト
# ===================================================

import csv
import os
import sys
from scraper import run_scraping, BlockedError


def load_existing_csv(filepath):
    """
    既存CSVを {タグ名: {列名: 値}} の辞書として読み込む
    タグ名をキーにすることで別衣装も個別に管理できる
    """
    if not os.path.exists(filepath):
        return {}
    existing = {}
    with open(filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tag = row.get("タグ名", "")
            if tag:
                existing[tag] = dict(row)
    return existing


def load_existing_by_name(filepath):
    """
    既存CSVを {名前: {列名: 値}} の辞書として読み込む
    select_targets()での24時間判定用（名前単位で最終更新日時を取得）
    同名が複数ある場合（別衣装）はメインタグ（名前==タグ名）を優先
    """
    if not os.path.exists(filepath):
        return {}
    existing = {}
    with open(filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("名前", "")
            tag  = row.get("タグ名", "")
            if not name:
                continue
            # メインタグ（名前==タグ名）を優先、なければ最初に見つかったもの
            if name not in existing or name == tag:
                existing[name] = dict(row)
    return existing


def merge_results(character_names, new_data_by_tag, existing_by_tag):
    """
    結果をマージしてCSV行リストを返す
    - character_names: Wikiから取得したキャラ名簿（nameベース）
    - new_data_by_tag: 今回取得した {タグ名: row}
    - existing_by_tag: 既存CSV {タグ名: row}

    出力ルール：
    - 今回更新したタグ → 新データで上書き
    - 今回更新していないタグ → 既存データを維持
    - Wikiの名前一覧に存在しない名前のタグ → 削除
    """
    header = ["名前", "タグ名", "学校", "部活", "全件数", "全年齢", "R-18", "R-18率", "最終更新日時"]
    rows   = [header]

    # Wikiに存在する名前セット
    wiki_names = {c["name"] for c in character_names}

    # 既存データのうちWikiに存在する名前のタグをベースに構築
    # タグ名をキーにして順序を保つ（既存順を維持）
    merged = {}
    for tag, row in existing_by_tag.items():
        name = row.get("名前", "")
        if name in wiki_names:
            merged[tag] = row

    # 今回取得した新データで上書き
    for tag, row in new_data_by_tag.items():
        merged[tag] = row

    # Wiki名簿順に並び替えて出力
    # 各キャラのメインタグ→別衣装タグの順になるよう整理
    # ※別衣装はcharacter_namesに含まれないのでmergedから名前単位でグループ化
    name_to_tags = {}
    for tag, row in merged.items():
        name = row.get("名前", "")
        if name not in name_to_tags:
            name_to_tags[name] = []
        name_to_tags[name].append(tag)

    # Wiki名簿の順番でキャラを処理（重複排除）
    seen_names = set()
    for chara in character_names:
        name = chara["name"]
        if name in seen_names:
            continue
        seen_names.add(name)
        if name not in name_to_tags:
            continue
        tags = name_to_tags[name]
        # メインタグ（名前==タグ名 or 名前+(BA)）を先頭に、残りはソート
        main_candidates = [t for t in tags if t == name or t == f"{name}(ブルーアーカイブ)"]
        other_tags      = sorted([t for t in tags if t not in main_candidates])
        for tag in main_candidates + other_tags:
            row = merged[tag]
            rows.append([row.get(col, "") for col in header])

    return rows


def main():
    base_dir    = os.path.dirname(os.path.abspath(__file__))
    output_dir  = os.path.join(base_dir, "data")
    output_file = os.path.join(output_dir, "result.csv")

    os.makedirs(output_dir, exist_ok=True)

    # 既存CSVを2種類の辞書で読み込む
    existing_by_tag  = load_existing_csv(output_file)
    existing_by_name = load_existing_by_name(output_file)

    if existing_by_tag:
        print(f"既存CSV読み込み: {len(existing_by_tag)} 件（タグ単位）", flush=True)
    else:
        print("既存CSVなし（新規作成）", flush=True)

    new_data_by_tag = {}   # 今回取得できたデータ {タグ名: row_dict}
    character_names = []   # Wikipediaから取得したキャラ名簿
    error_msg       = None

    def on_status(msg):
        print(msg, flush=True)

    def on_progress(val):
        print(f"進捗: {val*100:.1f}%", flush=True)

    def on_row(entry, row):
        """1件処理完了のたびに呼ばれるコールバック"""
        header = ["名前", "タグ名", "学校", "部活", "全件数", "全年齢", "R-18", "R-18率", "最終更新日時"]
        tag = entry["tag"]
        new_data_by_tag[tag] = dict(zip(header, row))

    def on_characters(characters):
        """キャラ名簿取得後に呼ばれるコールバック"""
        character_names.extend(characters)

    print("スクレイピング開始...", flush=True)

    try:
        _, completed, total = run_scraping(
            existing=existing_by_name,
            progress_callback=on_progress,
            status_callback=on_status,
            row_callback=on_row,
            characters_callback=on_characters,
        )
        print(f"\n✅ 全件完了: {completed}/{total} 件", flush=True)

    except BlockedError as e:
        error_msg = f"ブロックにより中断: {e.completed}/{e.total} 件処理済み"
        print(f"\n⚠️ {error_msg}", flush=True)

    except Exception as e:
        error_msg = f"予期しないエラーで中断: {len(new_data_by_tag)} 件処理済み / {e}"
        print(f"\n❌ {error_msg}", flush=True)

    # キャラ名簿が取得できていない場合は保存しない
    if not character_names:
        print("⚠️ キャラ名簿が取得できなかったため保存をスキップします。", flush=True)
        sys.exit(1)

    # マージして保存
    rows = merge_results(character_names, new_data_by_tag, existing_by_tag)

    new_count       = len(new_data_by_tag)
    preserved_count = len([t for t in existing_by_tag if t not in new_data_by_tag
                           and existing_by_tag[t].get("名前", "") in {c["name"] for c in character_names}])
    deleted_count   = len([t for t in existing_by_tag
                           if existing_by_tag[t].get("名前", "") not in {c["name"] for c in character_names}])

    print(f"\n📊 マージ結果:", flush=True)
    print(f"  今回更新: {new_count} 件", flush=True)
    print(f"  既存維持: {preserved_count} 件", flush=True)
    print(f"  削除:     {deleted_count} 件", flush=True)
    print(f"  合計:     {len(rows)-1} 件", flush=True)

    with open(output_file, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"💾 {len(rows)-1} 件を {output_file} に保存しました。", flush=True)

    if error_msg:
        sys.exit(1)


if __name__ == "__main__":
    main()
