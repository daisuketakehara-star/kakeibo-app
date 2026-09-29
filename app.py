import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ページ基本設定
st.set_page_config(page_title="家計簿（収支・投資カテゴリ分析）", page_icon="📊", layout="wide")

# Google Sheets 認証処理
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    return gspread.authorize(creds)

spreadsheet_id = "1QQB9OndMMFP33V8TUusNUKvaIyMrD8-qYlu0icobGfA"

# シート（年度）一覧の取得
try:
    client = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    sheet_names = [ws.title for ws in sh.worksheets() if ws.title.startswith("FY") or "20" in ws.title]
except Exception:
    sheet_names = ["FY2027", "FY2026", "FY2025", "FY2024", "FY2023"]

st.sidebar.header("⚙️ 設定")
selected_sheet = st.sidebar.selectbox("表示年度（シート）", sheet_names, index=0)

# 費目を「収入」「投資・貯蓄」「固定費」「変動費」に分類する判定関数
def classify_item(item_name):
    name = str(item_name).strip()
    
    # 1. 収入判定
    income_keywords = ["給料", "給与", "賞与", "ボーナス", "手当", "還付", "収入", "売却"]
    if any(k in name for k in income_keywords):
        return "💰 収入"
        
    # 2. 投資・貯蓄判定
    invest_keywords = ["NISA", "iDeCo", "投資", "積立", "貯蓄", "投信", "株", "資産"]
    if any(k in name for k in invest_keywords):
        return "📈 投資・貯蓄"
        
    # 3. 固定費判定
    fixed_keywords = ["ローン", "家賃", "電気", "ガス", "水道", "通信", "携帯", "スマホ", "保険", "学費", "保育", "管理費", "修繕", "サブスク"]
    if any(k in name for k in fixed_keywords):
        return "🏠 固定費"
        
    # 4. その他は変動費
    return "🛍️ 変動費"

@st.cache_data(ttl=60)
def load_raw_sheet_data(sheet_name):
    client = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    sheet = sh.worksheet(sheet_name)
    return sheet.get_all_values()

try:
    data = load_raw_sheet_data(selected_sheet)
    
    if len(data) >= 2:
        title_row = data[0]  # 1行目（年・月）
        header_row = data[1] # 2行目（費目・実行日・口座名）
        body_rows = data[2:] # 3行目以降（データ）

        # 1行目の結合セル（空欄補完）を展開
        header_groups = [("区分", 1)]  # 先頭に区分列を追加
        i = 0
        while i < len(title_row):
            val = title_row[i].replace("[merged]", "").strip()
            colspan = 1
            j = i + 1
            while j < len(title_row) and title_row[j].replace("[merged]", "").strip() == "" and title_row[j] == title_row[i]:
                colspan += 1
                j += 1
            header_groups.append((val, colspan))
            i += colspan

        # データの分類処理
        categorized_rows = []
        for row in body_rows:
            if not any(row):
                continue
            item_name = row[0]
            category = classify_item(item_name)
            categorized_rows.append((category, row))

        # カテゴリフィルター
        st.sidebar.markdown("---")
        category_filter = st.sidebar.multiselect(
            "表示カテゴリで絞り込み",
            ["💰 収入", "📈 投資・貯蓄", "🏠 固定費", "🛍️ 変動費"],
            default=["💰 収入", "📈 投資・貯蓄", "🏠 固定費", "🛍️ 変動費"]
        )

        # HTMLテーブル構築
        html = """
        <style>
            .sheet-container {
                overflow-x: auto;
                max-height: 75vh;
                border: 1px solid #e0e0e0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .sheet-table {
                border-collapse: collapse;
                width: 100%;
                font-size: 13px;
                background-color: #ffffff;
            }
            .sheet-table th, .sheet-table td {
                border: 1px solid #d3d3d3;
                padding: 6px 10px;
                white-space: nowrap;
            }
            .sheet-table thead tr:nth-child(1) th {
                background-color: #107c41;
                color: #ffffff;
                font-weight: bold;
                text-align: center;
                position: sticky;
                top: 0;
                z-index: 3;
            }
            .sheet-table thead tr:nth-child(2) th {
                background-color: #e2efda;
                color: #274e13;
                font-weight: bold;
                text-align: center;
                position: sticky;
                top: 29px;
                z-index: 2;
            }
            .sheet-table tbody tr:hover {
                background-color: #f5f5f5;
            }
            .sheet-table td.num {
                text-align: right;
            }
            .sheet-table td.sticky-col {
                position: sticky;
                left: 0;
                background-color: #f9f9f9;
                z-index: 1;
                font-weight: 600;
            }
            .cat-badge {
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 4px;
                font-weight: bold;
            }
            .cat-income { background-color: #d4edda; color: #155724; }
            .cat-invest { background-color: #cce5ff; color: #004085; }
            .cat-fixed { background-color: #fff3cd; color: #856404; }
            .cat-variable { background-color: #f8d7da; color: #721c24; }
        </style>
        <div class="sheet-container">
        <table class="sheet-table">
        <thead>
        <tr>
        """

        # 1行目（月ヘッダー）
        for val, span in header_groups:
            html += f'<th colspan="{span}">{val}</th>'
        html += "</tr><tr><th>区分</th>"

        # 2行目（費目・口座ヘッダー）
        for idx, col in enumerate(header_row):
            sticky_class = ' class="sticky-col"' if idx == 0 else ''
            html += f'<th{sticky_class}>{col}</th>'
        html += "</tr></thead><tbody>"

        # 3行目以降（データ行＋カテゴリバッジ）
        for cat, row in categorized_rows:
            if cat not in category_filter:
                continue

            # バッジ用のCSSクラス判定
            badge_class = "cat-variable"
            if "収入" in cat: badge_class = "cat-income"
            elif "投資" in cat: badge_class = "cat-invest"
            elif "固定費" in cat: badge_class = "cat-fixed"

            html += f'<tr><td><span class="cat-badge {badge_class}">{cat}</span></td>'
            
            for idx, cell in enumerate(row):
                sticky_class = ' class="sticky-col"' if idx == 0 else ''
                cell_str = cell.strip()
                align_class = ' class="num"' if cell_str.replace(',', '').replace('¥', '').replace('-', '').isdigit() else ''
                if idx == 0 and sticky_class:
                    align_class = ' class="sticky-col"'

                html += f'<td{align_class}>{cell_str}</td>'
            html += "</tr>"

        html += "</tbody></table></div>"

        st.title(f"📊 家計簿 ({selected_sheet})")
        st.caption("※「収入」「投資・貯蓄」「固定費」「変動費」の分類概念を自動適用しています。")
        st.components.v1.html(html, height=750, scrolling=True)

    else:
        st.warning("シートに十分なデータがありません。")

except Exception as e:
    st.error(f"データ取得エラー: {e}")
