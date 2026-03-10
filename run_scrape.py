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

    rows      = [["学校", "部活", "名前", "全件数", "R-18", "全年齢", "R-18率"]]
    completed = 0
    total     = 0
    error_msg = None

    def on_status(msg):
        print(msg, flush=True)

    def on_progress(val):
        print(f"進捗: {val*100:.1f}%", flush=True)

    # rowsをrun_scrapingの外から参照できるようにするため
    # run_scrapingが途中でどんな例外を投げても保存できるよう
    # scraper側のrowsをここで受け取れるようにする
    scraper_state = {"rows": rows}

    def on_row(row):
        """1件処理完了のたびに呼ばれるコールバック"""
        scraper_state["rows"].append(row)

    print("スクレイピング開始...", flush=True)

    try:
        rows, completed, total = run_scraping(
            progress_callback=on_progress,
            status_callback=on_status,
            row_callback=on_row,
        )
        print(f"\n✅ 全件完了: {completed}/{total} 件", flush=True)

    except BlockedError as e:
        rows      = e.rows
        completed = e.completed
        total     = e.total
        error_msg = f"ブロックにより中断: {completed}/{total} 件処理済み"
        print(f"\n⚠️ {error_msg}", flush=True)

    except Exception as e:
        # タイムアウトなどの予期しないエラー
        rows      = scraper_state["rows"]
        completed = len(rows) - 1  # ヘッダー行を除く
        error_msg = f"予期しないエラーで中断: {completed} 件処理済み / {e}"
        print(f"\n❌ {error_msg}", flush=True)

    # どんな場合でもCSVを保存
    if len(rows) > 1:
        with open(output_file, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        print(f"💾 {len(rows)-1} 件を {output_file} に保存しました。", flush=True)
    else:
        print("⚠️ 保存できるデータがありませんでした。", flush=True)

    if error_msg:
        sys.exit(1)


if __name__ == "__main__":
    main()
