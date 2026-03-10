# ===================================================
# GitHub Actions から呼び出されるスクレイピング実行スクリプト
# ===================================================

import csv
import os
import sys
from scraper import run_scraping, BlockedError


def load_existing_csv(filepath):
    """既存CSVを {名前: row} の辞書として読み込む"""
    if not os.path.exists(filepath):
        return {}
    existing = {}
    with open(filepath, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return {}
        for row in reader:
            if len(row) >= 3:
                name = row[2]  # 3列目が名前
                existing[name] = row
    return existing


def merge_results(character_names, new_data, existing_data):
    """
    Wikipediaの名簿を正のリストとして結果をマージする
    - 名簿にある & 新データあり  → 新データで更新
    - 名簿にある & 新データなし  → 既存データを維持
    - 名簿にない                → 削除（出力しない）
    """
    header = ["学校", "部活", "名前", "全件数", "R-18", "全年齢", "R-18率"]
    rows   = [header]

    for chara in character_names:
        name = chara["name"]
        if name in new_data:
            # 今回取得できた → 新データを使用
            rows.append(new_data[name])
        elif name in existing_data:
            # 今回取得できなかった & 既存データあり → 既存を維持
            rows.append(existing_data[name])
        # 既存にも新規にもない → 行を追加しない（実質0件キャラは空行になるが今回はスキップ）

    return rows


def main():
    base_dir    = os.path.dirname(os.path.abspath(__file__))
    output_dir  = os.path.join(base_dir, "data")
    output_file = os.path.join(output_dir, "result.csv")

    os.makedirs(output_dir, exist_ok=True)

    # 既存CSVを読み込んでおく
    existing_data = load_existing_csv(output_file)
    if existing_data:
        print(f"既存CSV読み込み: {len(existing_data)} 件", flush=True)
    else:
        print("既存CSVなし（新規作成）", flush=True)

    new_data      = {}   # 今回取得できたデータ {名前: row}
    character_names = [] # Wikipediaから取得したキャラ名簿
    error_msg     = None

    def on_status(msg):
        print(msg, flush=True)

    def on_progress(val):
        print(f"進捗: {val*100:.1f}%", flush=True)

    def on_row(chara, row):
        """1件処理完了のたびに呼ばれるコールバック"""
        new_data[chara["name"]] = row

    def on_characters(characters):
        """キャラ名簿取得後に呼ばれるコールバック"""
        character_names.extend(characters)

    print("スクレイピング開始...", flush=True)

    try:
        _, completed, total = run_scraping(
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
        error_msg = f"予期しないエラーで中断: {len(new_data)} 件処理済み / {e}"
        print(f"\n❌ {error_msg}", flush=True)

    # キャラ名簿が取得できていない場合は保存しない（Wikipedia取得失敗）
    if not character_names:
        print("⚠️ キャラ名簿が取得できなかったため保存をスキップします。", flush=True)
        sys.exit(1)

    # マージして保存
    rows = merge_results(character_names, new_data, existing_data)

    new_count      = sum(1 for c in character_names if c["name"] in new_data)
    preserved_count = sum(1 for c in character_names if c["name"] not in new_data and c["name"] in existing_data)
    deleted_count  = len(existing_data) - sum(1 for c in character_names if c["name"] in existing_data)

    print(f"\n📊 マージ結果:", flush=True)
    print(f"  今回更新: {new_count} 件", flush=True)
    print(f"  既存維持: {preserved_count} 件", flush=True)
    print(f"  削除:     {max(0, deleted_count)} 件", flush=True)
    print(f"  合計:     {len(rows)-1} 件", flush=True)

    with open(output_file, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"💾 {len(rows)-1} 件を {output_file} に保存しました。", flush=True)

    if error_msg:
        sys.exit(1)


if __name__ == "__main__":
    main()
