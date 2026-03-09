# ===================================================
# GitHub Actions から呼び出されるスクレイピング実行スクリプト
# ===================================================

import csv
import os
from scraper import run_scraping


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
    rows = run_scraping(
        progress_callback=on_progress,
        status_callback=on_status,
    )

    with open(output_file, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"\n完了: {len(rows)-1} 件を {output_file} に保存しました。", flush=True)


if __name__ == "__main__":
    main()
