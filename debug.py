import streamlit as st
import requests
import re
from urllib.parse import quote

st.title("🔍 接続検証ツール")

tag = "小鳥遊ホシノ"

if st.button("検証開始"):
    # --- 大百科 ---
    st.subheader("① pixiv大百科")
    dic_url = f"https://dic.pixiv.net/en/"
    try:
        r = requests.get(dic_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        st.write("STATUS:", r.status_code)
        m = re.findall(r'"pixivWorkCount":(\d+)', r.text)
        st.write("pixivWorkCount:", m)
        st.write("HTML先頭300字:", r.text[:300])
    except Exception as e:
        st.error(f"エラー: {e}")

    # --- pixiv本体 ---
    st.subheader("② pixiv本体タグページ")
    url = f"https://www.pixiv.net/tags/{quote(tag)}"
    try:
        r2 = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        st.write("STATUS:", r2.status_code)
        illust = re.findall(r'小説。([\d,]+)件のイラスト', r2.text)
        st.write("illust_match:", illust)
        st.write("HTML先頭300字:", r2.text[:300])
    except Exception as e:
        st.error(f"エラー: {e}")

    # --- AJAX ---
    st.subheader("③ pixiv AJAX API")
    ajax_url = f"https://www.pixiv.net/ajax/search/artworks/{quote(tag)}?word={quote(tag)}&order=date_d&mode=all&p=1&s_mode=s_tag"
    try:
        r3 = requests.get(ajax_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.pixiv.net/"}, timeout=10)
        st.write("STATUS:", r3.status_code)
        j = r3.json()
        if "body" in j and "illustManga" in j["body"]:
            st.write("illustManga total:", j["body"]["illustManga"].get("total"))
    except Exception as e:
        st.error(f"エラー: {e}")
