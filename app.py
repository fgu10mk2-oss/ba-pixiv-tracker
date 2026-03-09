# ===================================================
# ブルーアーカイブ pixiv R-18率調査ツール
# app.py - Streamlit UI
# ===================================================

import streamlit as st
import pandas as pd
import io
import csv
import base64
from github import Github, Auth
from scraper import run_scraping

# -----------------------------------------------
# 定数
# -----------------------------------------------
GITHUB_REPO  = st.secrets.get("GITHUB_REPO", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
CSV_PATH     = "data/result.csv"

# -----------------------------------------------
# ページ設定
# -----------------------------------------------
st.set_page_config(
    page_title="ブルーアーカイブ pixiv R-18率調査",
    page_icon="📊",
    layout="wide",
)

st.title("📊 ブルーアーカイブ pixiv R-18率調査ツール")
st.caption("Wikipediaからキャラ一覧を取得し、pixivの全件数・健全件数・R-18率を集計します。")


# -----------------------------------------------
# GitHub操作ヘルパー
# -----------------------------------------------
def get_github_repo():
    auth = Auth.Token(GITHUB_TOKEN)
    g    = Github(auth=auth)
    return g.get_repo(GITHUB_REPO)


@st.cache_data(ttl=60)
def load_csv_from_github():
    """GitHubリポジトリのCSVを読み込む。存在しない場合はNoneを返す"""
    try:
        repo    = get_github_repo()
        file    = repo.get_contents(CSV_PATH)
        content = base64.b64decode(file.content).decode("utf-8-sig")
        df      = pd.read_csv(io.StringIO(content))
        return df, file.sha
    except Exception:
        return None, None


def push_csv_to_github(rows: list):
    """CSVをGitHubリポジトリにpushする（新規作成・更新を自動判定）"""
    repo = get_github_repo()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    content_bytes = buf.getvalue().encode("utf-8-sig")

    message = "Update result.csv via Streamlit"

    try:
        existing = repo.get_contents(CSV_PATH)
        current_sha = existing.sha
        repo.update_file(CSV_PATH, message, content_bytes, current_sha)
    except Exception:
        repo.create_file(CSV_PATH, message, content_bytes)


# -----------------------------------------------
# データ読み込み
# -----------------------------------------------
df, current_sha = load_csv_from_github()

# -----------------------------------------------
# タブ構成
# -----------------------------------------------
tab_view, tab_update = st.tabs(["📋 データ閲覧・ダウンロード", "🔄 データ更新"])

# =====================
# タブ1: 閲覧・DL
# =====================
with tab_view:
    if df is None:
        st.warning("CSVデータがまだありません。「データ更新」タブからデータを取得してください。")
    else:
        st.success(f"データ読み込み完了：{len(df)} 件")

        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            schools = ["すべて"] + sorted(df["学校"].dropna().unique().tolist())
            selected_school = st.selectbox("学校で絞り込み", schools)
        with col2:
            min_total = st.number_input("最小全件数", min_value=0, value=0)
        with col3:
            sort_col = st.selectbox("並び替え", ["全件数", "R-18率", "R-18", "全年齢", "名前"])
            sort_asc = st.checkbox("昇順", value=False)

        filtered = df.copy()
        if selected_school != "すべて":
            filtered = filtered[filtered["学校"] == selected_school]
        filtered = filtered[filtered["全件数"].fillna(0) >= min_total]
        filtered = filtered.sort_values(sort_col, ascending=sort_asc)

        display_df = filtered.copy()
        if "R-18率" in display_df.columns:
            display_df["R-18率"] = display_df["R-18率"].apply(
                lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A"
            )

        st.dataframe(display_df, use_container_width=True, height=500)

        st.divider()
        st.subheader("📈 統計サマリー")
        valid = filtered[filtered["全件数"].notna() & (filtered["全件数"] > 0)]

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("表示件数", f"{len(filtered)} 件")
        col_b.metric("全件数合計", f"{int(valid['全件数'].sum()):,}")
        col_c.metric("R-18合計", f"{int(valid['R-18'].sum()):,}")
        if valid["全件数"].sum() > 0:
            overall_r18 = valid["R-18"].sum() / valid["全件数"].sum()
            col_d.metric("全体R-18率", f"{overall_r18*100:.1f}%")

        st.divider()
        csv_bytes = filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="⬇️ 表示中のデータをCSVダウンロード",
            data=csv_bytes,
            file_name="ba_pixiv_result.csv",
            mime="text/csv",
        )

# =====================
# タブ2: データ更新
# =====================
with tab_update:
    st.subheader("🔄 データ更新")
    st.info(
        "「更新開始」を押すと、Wikipediaからキャラ一覧を取得し、"
        "pixivの件数を再取得してGitHubのCSVを上書き更新します。\n\n"
        "⚠️ キャラ数が多いため完了まで **5〜10分程度** かかります。"
    )

    if "running" not in st.session_state:
        st.session_state.running = False

    if st.button("🚀 更新開始", disabled=st.session_state.running, type="primary"):
        st.session_state.running = True

        progress_bar  = st.progress(0.0)
        status_text   = st.empty()
        result_holder = st.empty()

        try:
            def on_progress(val):
                progress_bar.progress(val)

            def on_status(msg):
                status_text.text(msg)

            rows = run_scraping(
                progress_callback=on_progress,
                status_callback=on_status,
            )

            status_text.text("GitHubにCSVをアップロード中...")
            push_csv_to_github(rows)

            st.cache_data.clear()

            progress_bar.progress(1.0)
            result_holder.success(
                f"✅ 更新完了！{len(rows)-1} 件のデータをGitHubに保存しました。"
                "「データ閲覧」タブで確認できます。"
            )

        except Exception as e:
            result_holder.error(f"❌ エラーが発生しました: {e}")

        finally:
            st.session_state.running = False
