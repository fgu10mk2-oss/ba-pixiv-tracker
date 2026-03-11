# ===================================================
# ブルーアーカイブ pixiv R-18率調査ツール
# app.py - Streamlit UI（閲覧・更新トリガー）
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


def trigger_github_actions(limit: int = 1):
    """GitHub Actionsのワークフローを手動トリガー"""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/scrape.yml/dispatches"
    r = requests.post(url, headers=headers, json={
        "ref": "main",
        "inputs": {"update_limit": str(limit)}
    })
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
# 初回データ読み込み
# -----------------------------------------------
if "df" not in st.session_state:
    st.session_state.df = load_csv_from_github()

df = st.session_state.df

# -----------------------------------------------
# サイドバー：更新操作
# -----------------------------------------------
with st.sidebar:
    st.header("🔄 データ更新")

    wf = get_workflow_status()
    if wf:
        key = (wf["status"], wf["conclusion"])
        status_label = {
            ("in_progress", None):        "🟡 実行中...",
            ("queued",      None):        "🟡 待機中...",
            ("completed",   "success"):   "✅ 完了",
            ("completed",   "failure"):   "❌ 失敗",
            ("completed",   "cancelled"): "⚪ キャンセル",
        }.get(key, "⚪ 不明")

        st.info(
            f"最終実行: {wf['created_at'][:16].replace('T', ' ')}\n\n"
            f"状態: {status_label}"
        )
        st.markdown(f"[ActionsログはこちらからGitHub]({wf['html_url']})")

    st.divider()

    update_limit = st.slider("更新するキャラ数", min_value=1, max_value=50, value=1, step=1)

    if st.button("🚀 更新を実行", type="primary", use_container_width=True):
        if trigger_github_actions(limit=update_limit):
            st.success(
                f"GitHub Actionsを起動しました！\n\n"
                f"{update_limit} キャラ分を処理します。\n"
                "完了後に「🔃 データを再読み込み」を押してください。"
            )
        else:
            st.error(
                "起動に失敗しました。\n"
                "PATに `workflow` スコープが付いているか確認してください。"
            )

    st.divider()

    if st.button("🔃 データを再読み込み", use_container_width=True):
        st.session_state.df = load_csv_from_github()
        df = st.session_state.df
        if df is not None:
            st.success(f"読み込み完了！{len(df)} 件")
        else:
            st.warning("CSVが見つかりません。")
        st.rerun()

# -----------------------------------------------
# メインエリア：データ閲覧・ダウンロード
# -----------------------------------------------
if df is None:
    st.warning("CSVデータがまだありません。サイドバーの「🚀 更新を実行」でデータを取得してください。")
else:
    st.success(f"データ読み込み完了：{len(df)} 件")

    # フィルタ・ソート
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        schools = ["すべて"] + sorted(df["学校"].dropna().unique().tolist())
        selected_school = st.selectbox("学校で絞り込み", schools)
    with col2:
        min_total = st.number_input("最小全件数", min_value=0, value=0)
    with col3:
        sort_col = st.selectbox("並び替え", ["全件数", "R-18率", "R-18", "全年齢", "名前"])
        sort_asc = st.checkbox("昇順", value=False)

    # 別衣装を含む／メインキャラのみ
    show_costumes = st.checkbox("別衣装も表示する", value=True)

    filtered = df.copy()
    if selected_school != "すべて":
        filtered = filtered[filtered["学校"] == selected_school]
    filtered = filtered[filtered["全件数"].fillna(0) >= min_total]
    if not show_costumes:
        # タグ名 == 名前 or タグ名 == 名前(ブルーアーカイブ) のみ表示
        filtered = filtered[
            (filtered["タグ名"] == filtered["名前"]) |
            (filtered["タグ名"] == filtered["名前"] + "(ブルーアーカイブ)")
        ]
    filtered = filtered.sort_values(sort_col, ascending=sort_asc)

    display_df = filtered.copy()
    if "R-18率" in display_df.columns:
        display_df["R-18率"] = display_df["R-18率"].apply(
            lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A"
        )

    # 1行あたり約35px + ヘッダー38px
    table_height = 38 + len(display_df) * 35
    st.dataframe(display_df, use_container_width=True, height=table_height)

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
