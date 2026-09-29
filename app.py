import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ページ基本設定
st.set_page_config(page_title="家計簿ダッシュボード", page_icon="📊", layout="wide")

st.title("📊 家計簿ダッシュボード (FY2027)")

# Google Sheets 認証処理
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Secrets から GCP サービスアカウント情報を読み込み
    credentials_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    client = gspread.authorize(creds)
    return client

# 重複する列名や空欄列名を補正して一意（ユニーク）にする関数
def fix_duplicate_columns(df):
    cols = []
    counts = {}
    for i, col in enumerate(df.columns):
        c_str = str(col).strip() if str(col).strip() and not str(col).startswith("Unnamed") else f"Col_{i+1}"
        if c_str in counts:
            counts[c_str] += 1
            cols.append(f"{c_str}_{counts[c_str]}")
        else:
            counts[c_str] = 0
            cols.append(c_str)
    df.columns = cols
    return df

# データ取得処理
@st.cache_data(ttl=60)
def load_data():
    client = get_gspread_client()
    # 対象のスプレッドシートID
    spreadsheet_id = "1QQB9OndMMFP33V8TUusNUKvaIyMrD8-qYlu0icobGfA"
    sheet = client.open_by_key(spreadsheet_id).worksheet("FY2027")
    
    # データを取得
    data = sheet.get_all_values()
    if not data:
        return pd.DataFrame()
    
    # 2行目をヘッダーとして読み込み
    if len(data) >= 2:
        df = pd.DataFrame(data[2:], columns=data[1])
    else:
        df = pd.DataFrame(data)
        
    # 列名の重複・空欄を補正
    df = fix_duplicate_columns(df)
    return df

try:
    df = load_data()
    st.success("✓ Googleスプレッドシートとリアルタイム同期中")
    
    st.subheader("📋 全費目・年間比較テーブル (直接編集可能)")
    
    # 重複エラーが解消されたテーブルを表示
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

except Exception as e:
    st.error(f"スプレッドシートとの接続エラー: {e}")
