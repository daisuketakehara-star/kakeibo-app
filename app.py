import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px

st.set_page_config(page_title="家計簿ダッシュボード", layout="wide")
st.title("📊 家計簿ダッシュボード (FY2027)")

@st.cache_resource
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

try:
    gc = get_gspread_client()
    doc = gc.open_by_key("1QQB9OndMMFP33V8TUusNUKvaIyMrD8-qYlu0icobGfA")
    sheet = doc.worksheet("FY2027")
    
    data = sheet.get_all_values()
    df = pd.DataFrame(data[2:], columns=data[1])
    
    st.success("✓ Googleスプレッドシートとリアルタイム同期中")

    st.subheader("📋 全費目・年間比較テーブル (直接編集可能)")
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        key="kakeibo_editor"
    )

    if st.button("💾 変更をスプレッドシートに保存"):
        sheet.update([edited_df.columns.values.tolist()] + edited_df.values.tolist())
        st.success("スプレッドシートへ最新データを保存しました！")

    with st.expander("⚙ クレカ明細・レシートのスキャン入力"):
        uploaded_file = st.file_uploader("明細画像またはPDFを添付してください", type=["png", "jpg", "jpeg", "pdf"])
        if uploaded_file:
            st.info("AI解析準備完了")

except Exception as e:
    st.error(f"スプレッドシートとの接続エラー: {e}")
