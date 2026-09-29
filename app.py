import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go

# 1. ページ基本設定
st.set_page_config(page_title="家計簿ダッシュボード", page_icon="📊", layout="wide")

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

# 数値変換ヘルパー関数
def clean_num(val):
    if not val:
        return 0.0
    s = str(val).replace(",", "").replace("¥", "").replace("￥", "").replace(" ", "").strip()
    if s in ["-", "", "None", "null"]:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0

@st.cache_data(ttl=60)
def load_raw_sheet_data(sheet_name):
    client = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    sheet = sh.worksheet(sheet_name)
    return sheet.get_all_values()

# 特定のキーワードを含む行を検索するヘルパー関数
def find_row_by_keywords(rows, keywords):
    for idx, row in enumerate(rows):
        if not row or not row[0]:
            continue
        first_cell = str(row[0]).strip()
        if any(k in first_cell for k in keywords):
            return idx, row
    return None, None

# --- サイドバー設定 ---
st.sidebar.header("⚙️ ダッシュボード設定")
selected_sheet = st.sidebar.selectbox("表示年度（シート）", sheet_names, index=0)

try:
    data = load_raw_sheet_data(selected_sheet)
    
    if len(data) >= 2:
        title_row = data[0]  # 1行目（年・月）
        header_row = data[1] # 2行目（費目・実行日・口座名）

        # 各「月」のインデックスマッピング（例: "4月" -> [2, 3] 列）
        months = []
        month_col_indices = {}
        current_m = ""
        
        for idx, cell in enumerate(title_row):
            m_clean = cell.replace("[merged]", "").strip()
            if m_clean and ("月" in m_clean or m_clean in ["合計", "平均"]):
                current_m = m_clean
            if current_m and "月" in current_m and current_m not in ["合計", "平均"]:
                if current_m not in months:
                    months.append(current_m)
                    month_col_indices[current_m] = []
                month_col_indices[current_m].append(idx)

        selected_month = st.sidebar.selectbox("分析対象月を選択", months, index=0)

        # ----------------------------------------------------
        # 指定行のピンポイント取得（キーバリュー特定 ＋ バックアップ検索）
        # ----------------------------------------------------
        # スプレッドシート上の定義行（1インデックスから0インデックスへの調整）
        # 行13: 収入合計
        # 行83: 支出合計
        # 行87: 銀行口座残高
        # 行106: 積立NISA
        # 行111: iDeCo
        # 行117: 学資保険

        def get_row_data(row_idx, keywords):
            if row_idx < len(data):
                row = data[row_idx]
                if row and row[0]:
                    return row
            # インデックスズレ防止用フォールバック検索
            _, found_row = find_row_by_keywords(data[:119], keywords)
            return found_row if found_row else []

        row_income = get_row_data(12, ["預入", "収入"])          # 行13 (Index 12)
        row_expense = get_row_data(82, ["出費", "支出"])         # 行83 (Index 82)
        row_bank = get_row_data(86, ["口座残高", "銀行口座"])     # 行87 (Index 86)
        row_nisa = get_row_data(105, ["積み立てNISA", "NISA"])   # 行106 (Index 105)
        row_ideco = get_row_data(110, ["イデコ", "iDeCo"])       # 行111 (Index 110)
        row_gakushi = get_row_data(116, ["学資保険"])            # 行117 (Index 116)

        # 月ごとの値取得関数（複数の列にまたがる場合は合算/最大値取得）
        def extract_month_value(row_data, month_name):
            if not row_data:
                return 0.0
            cols = month_col_indices.get(month_name, [])
            vals = [clean_num(row_data[c]) for c in cols if c < len(row_data)]
            return sum(vals) if vals else 0.0

        # 月別トレンドデータの計算
        monthly_trend = {
            m: {
                "収入合計": extract_month_value(row_income, m),
                "支出": extract_month_value(row_expense, m),
                "銀行口座残高": extract_month_value(row_bank, m),
                "積立NISA": extract_month_value(row_nisa, m),
                "iDeCo": extract_month_value(row_ideco, m),
                "学資保険": extract_month_value(row_gakushi, m),
            } for m in months
        }

        # 選択月の数値
        cur_income = monthly_trend[selected_month]["収入合計"]
        cur_expense = monthly_trend[selected_month]["支出"]
        cur_bank = monthly_trend[selected_month]["銀行口座残高"]
        cur_nisa = monthly_trend[selected_month]["積立NISA"]
        cur_ideco = monthly_trend[selected_month]["iDeCo"]
        cur_gakushi = monthly_trend[selected_month]["学資保険"]
        cur_invest_total = cur_nisa + cur_ideco + cur_gakushi

        # ----------------------------------------------------
        # UI レイアウト
        # ----------------------------------------------------
        st.title(f"📊 家計簿ダッシュボード ({selected_sheet})")
        st.markdown(f"### 📍 【{selected_month}】 収支・資産サマリー")

        # 1. サマリーカード (主要指標)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💰 収入合計 (行13)", f"¥{cur_income:,.0f}")
        k2.metric("💸 支出 (行83)", f"¥{cur_expense:,.0f}")
        k3.metric("🏦 銀行口座残高 (行87)", f"¥{cur_bank:,.0f}")
        k4.metric("📈 投資・積立・保険 合計", f"¥{cur_invest_total:,.0f}")

        # 投資・積立・保険の内訳サブカード
        st.markdown("##### 内部積立・資産形成の内訳")
        sub1, sub2, sub3 = st.columns(3)
        sub1.metric("🌱 積立NISA (行106)", f"¥{cur_nisa:,.0f}")
        sub2.metric("🛡️ iDeCo (行111)", f"¥{cur_ideco:,.0f}")
        sub3.metric("🎓 学資保険 (行117)", f"¥{cur_gakushi:,.0f}")

        st.markdown("---")

        # ----------------------------------------------------
        # 2. 可視化セクション (年間推移グラフ)
        # ----------------------------------------------------
        st.markdown("#### 📈 年間 収支 & 銀行口座残高 推移")
        
        trend_df = pd.DataFrame.from_dict(monthly_trend, orient="index").reset_index()
        trend_df.rename(columns={"index": "月"}, inplace=True)

        fig = go.Figure()
        # 収入合計 (棒グラフ)
        fig.add_trace(go.Bar(x=trend_df["月"], y=trend_df["収入合計"], name="収入合計", marker_color="#28a745"))
        # 支出 (棒グラフ)
        fig.add_trace(go.Bar(x=trend_df["月"], y=trend_df["支出"], name="支出", marker_color="#dc3545"))
        # 銀行口座残高 (折れ線グラフ)
        fig.add_trace(go.Scatter(x=trend_df["月"], y=trend_df["銀行口座残高"], name="銀行口座残高", mode="lines+markers", line=dict(color="#007bff", width=3)))

        fig.update_layout(
            barmode="group",
            height=360,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # ----------------------------------------------------
        # 3. 明細データテーブル (行1〜118の「家計簿」範囲限定表示)
        # ----------------------------------------------------
        st.markdown("#### 📋 家計簿明細テーブル (1行目〜118行目)")

        # 1行目〜118行目までに限定（120行目以降の「財産」は除外）
        kakeibo_body_rows = data[2:118] if len(data) >= 118 else data[2:]

        header_groups = [("区分/項目", 1)]
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

        html = """
        <style>
            .sheet-container {
                overflow-x: auto;
                max-height: 60vh;
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
            .sheet-table tbody tr:hover { background-color: #f5f5f5; }
            .sheet-table td.num { text-align: right; }
            .sheet-table td.sticky-col {
                position: sticky;
                left: 0;
                background-color: #f9f9f9;
                z-index: 1;
                font-weight: 600;
            }
            .highlight-row { background-color: #e8f4f8; font-weight: bold; }
        </style>
        <div class="sheet-container">
        <table class="sheet-table">
        <thead>
        <tr>
        """

        for val, span in header_groups:
            html += f'<th colspan="{span}">{val}</th>'
        html += "</tr><tr><th>No.</th>"

        for idx, col in enumerate(header_row):
            sticky_class = ' class="sticky-col"' if idx == 0 else ''
            html += f'<th{sticky_class}>{col}</th>'
        html += "</tr></thead><tbody>"

        for row_idx, row in enumerate(kakeibo_body_rows, start=3):
            if not any(row):
                continue
            
            # 重要集計行の強調表示スタイル（行13, 83, 87, 106, 111, 117）
            is_highlight = row_idx in [13, 83, 87, 106, 111, 117]
            row_style = ' class="highlight-row"' if is_highlight else ''

            html += f'<tr{row_style}><td>{row_idx}</td>'
            
            for idx, cell in enumerate(row):
                sticky_class = ' class="sticky-col"' if idx == 0 else ''
                cell_str = cell.strip()
                align_class = ' class="num"' if cell_str.replace(',', '').replace('¥', '').replace('-', '').isdigit() else ''
                if idx == 0 and sticky_class:
                    align_class = ' class="sticky-col"'

                html += f'<td{align_class}>{cell_str}</td>'
            html += "</tr>"

        html += "</tbody></table></div>"

        st.components.v1.html(html, height=600, scrolling=True)

    else:
        st.warning("シートに十分なデータがありません。")

except Exception as e:
    st.error(f"データ取得・描画エラー: {e}")
