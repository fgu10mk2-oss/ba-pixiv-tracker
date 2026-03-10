# ===================================================
# GitHub Actions から呼び出されるスクレイピング実行スクリプト
# ===================================================

import csv
import os
import sys
from scraper import run_scraping, BlockedError


def main():
    base_dir    = os.path.dirname(os.path.abspath(__file__))
    output_dir  = os.path.join(base_dir, "data")
    output_file = os.path.join(output_dir, "result.csv")

    os.makedirs(output_dir, exist_ok=True)

    def on_status(msg):
        print(msg, flush=True)

    def on_progress(val):
        print(f"進捗: {val*100:.1f}%", flush=True)

    print("スクレイピング開始...", flush=True)

    rows      = None
    completed = 0
    total     = 0
    blocked   = False

    try:
        rows, completed, total = run_scraping(
            progress_callback=on_progress,
            status_callback=on_status,
        )
        print(f"\n✅ 全件完了: {completed}/{total} 件", flush=True)

    except BlockedError as e:
        rows      = e.rows
        completed = e.completed
        total     = e.total
        blocked   = True
        print(f"\n⚠️ ブロックにより中断: {completed}/{total} 件処理済み", flush=True)

    # 結果をCSVに保存（中断分でも保存する）
    if rows and len(rows) > 1:
        with open(output_file, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        print(f"💾 {len(rows)-1} 件を {output_file} に保存しました。", flush=True)
    else:
        print("⚠️ 保存できるデータがありませんでした。", flush=True)

    # ブロックされた場合はexit code 1（Actionsログに赤く表示）
    if blocked:
        sys.exit(1)


if __name__ == "__main__":
    main()
