# ===================================================
# ブルーアーカイブ pixiv R-18率調査ツール
# app.py - Streamlit UI（閲覧専用）
# ===================================================

import streamlit as st
import pandas as pd
import io
import base64
import requests
from github import Github, Auth

GITHUB_REPO  = st.secrets.get("GITHUB_REPO", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
CSV_PATH     = "data/result.csv"

st.set_page_config(
    page_title="ブルーアーカイブ pixiv R-18率調査",
    page_icon="📊",
    layout="wide",
)

st.title("📊 ブルーアーカイブ pixiv R-18率調査ツール")
st.caption("Wikipediaからキャラ一覧を取得し、pixivの全件数・健全件数・R-18率を集計します。")


def get_github_repo():
    auth = Auth.Token(GITHUB_TOKEN)
    g    = Github(auth=auth)
    return g.get_repo(GITHUB_REPO)


def load_csv_from_github():
    """GitHubリポジトリのCSVを読み込む"""
    try:
        repo    = get_github_repo()
        file    = repo.get_contents(CSV_PATH)
        content = base64.b64decode(file.content).decode("utf-8-sig")
        df      = pd.read_csv(io.StringIO(content))
        return df
    except Exception:
        return None


def trigger_github_actions():
    """GitHub Actionsのワークフローを手動トリガー"""
    repo_name = GITHUB_REPO
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo_name}/actions/workflows/scrape.yml/dispatches"
    r = requests.post(url, headers=headers, json={"ref": "main"})
    return r.status_code == 204


def get_workflow_status():
    """最新のワークフロー実行状況を取得"""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/scrape.yml/runs?per_page=1"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        runs = r.json().get("workflow_runs", [])
        if runs:
            run = runs[0]
            return {
                "status":     run["status"],
                "conclusion": run["conclusion"],
                "created_at": run["created_at"],
                "html_url":   run["html_url"],
            }
    return None


# -----------------------------------------------
# データ読み込み（キャッシュなし・常に最新）
# -----------------------------------------------
if "df" not in st.session_state:
    st.session_state.df = None

# -----------------------------------------------
# サイドバー：更新操作
# -----------------------------------------------
with st.sidebar:
    st.header("🔄 データ更新")

    # 最新ワークフロー状況
    wf = get_workflow_status()
    if wf:
        status_map = {
            ("in_progress", None):  ("🟡 実行中...", "warning"),
            ("queued",      None):  ("🟡 待機中...", "warning"),
            ("completed", "success"): ("✅ 完了", "success"),
            ("completed", "failure"): ("❌ 失敗", "error"),
        }
        key = (wf["status"], wf["conclusion"])
        label, kind = status_map.get(key, ("⚪ 不明", "info"))
        st.info(f"最終実行: {wf['created_at'][:16].replace('T',' ')}\n\n状態: {label}")
        st.markdown(f"[ActionsログはこちらからGitHub]({wf['html_url']})")

    st.divider()

    # 更新ボタン
    if st.button("🚀 更新を実行", type="primary", use_container_width=True):
        if trigger_github_actions():
            st.success("GitHub Actionsを起動しました！\n\n完了まで10〜20分かかります。完了後に「データを再読み込み」を押してください。")
        else:
            st.error("起動に失敗しました。PATの権限を確認してください。")

    st.divider()

    # 再読み込みボタン
    if st.button("🔃 データを再読み込み", use_container_width=True):
        st.session_state.df = load_csv_from_github()
        if st.session_state.df is not None:
            st.success("読み込み完了！")
        else:
            st.warning("CSVが見つかりません。")

# 初回読み込み
if st.session_state.df is None:
    st.session_state.df = load_csv_from_github()

df = st.session_state.df

# -----------------------------------------------
# メインエリア：データ閲覧・ダウンロード
# -----------------------------------------------
if df is None:
    st.warning("CSVデータがまだありません。サイドバーの「更新を実行」でデータを取得してください。")
else:
    st.success(f"データ読み込み完了：{len(df)} 件")

    # --- フィルター ---
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

    # --- 統計サマリー ---
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

    # --- ダウンロード ---
    st.divider()
    csv_bytes = filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="⬇️ 表示中のデータをCSVダウンロード",
        data=csv_bytes,
        file_name="ba_pixiv_result.csv",
        mime="text/csv",
    )
