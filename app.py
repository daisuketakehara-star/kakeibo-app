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

# キーワードでピンポイント行を検索する関数
def find_row_by_keywords(rows, keywords):
    for idx, row in enumerate(rows):
        if not row or not row[0]:
            continue
        first_cell = str(row[0]).replace(" ", "").strip()
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

        # 各「月」のインデックスマッピング
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
        # スプレッドシートキー行のピンポイント取得（1〜119行範囲）
        # ----------------------------------------------------
        kakeibo_area = data[:119]

        _, row_income = find_row_by_keywords(kakeibo_area, ["預入合計", "預入合計"])
        _, row_expense = find_row_by_keywords(kakeibo_area, ["引出合計", "出費合計", "支出合計"])
        _, row_balance = find_row_by_keywords(kakeibo_area, ["収支合計", "収支合計"])
        
        _, row_bank_total = find_row_by_keywords(kakeibo_area, ["銀行残高合計", "銀行残高合計"])
        if not row_bank_total:
            _, row_bank_total = find_row_by_keywords(kakeibo_area, ["銀行残高"])

        _, row_nisa = find_row_by_keywords(kakeibo_area, ["積み立てNISA", "NISA"])
        _, row_ideco = find_row_by_keywords(kakeibo_area, ["イデコ", "iDeCo"])
        _, row_gakushi = find_row_by_keywords(kakeibo_area, ["学資保険"])

        # 月ごとの値抽出処理
        def get_value_for_month(row_data, month_name, mode="sum"):
            if not row_data:
                return 0.0
            cols = month_col_indices.get(month_name, [])
            vals = [clean_num(row_data[c]) for c in cols if c < len(row_data) and clean_num(row_data[c]) != 0.0]
            if not vals:
                return 0.0
            if mode == "last":
                return vals[-1]
            return sum(vals)

        # 月別トレンド計算
        monthly_trend = {}
        for m in months:
            monthly_trend[m] = {
                "預入合計": get_value_for_month(row_income, m, "sum"),
                "引出合計": get_value_for_month(row_expense, m, "sum"),
                "収支合計": get_value_for_month(row_balance, m, "sum"),
                "銀行残高合計": get_value_for_month(row_bank_total, m, "last"),
                "積立NISA": get_value_for_month(row_nisa, m, "sum"),
                "iDeCo": get_value_for_month(row_ideco, m, "sum"),
                "学資保険": get_value_for_month(row_gakushi, m, "sum"),
            }

        # 選択月の数値
        cur_income = monthly_trend[selected_month]["預入合計"]
        cur_expense = monthly_trend[selected_month]["引出合計"]
        cur_balance = monthly_trend[selected_month]["収支合計"]
        cur_bank = monthly_trend[selected_month]["銀行残高合計"]
        
        cur_nisa = monthly_trend[selected_month]["積立NISA"]
        cur_ideco = monthly_trend[selected_month]["iDeCo"]
        cur_gakushi = monthly_trend[selected_month]["学資保険"]
        cur_invest_total = cur_nisa + cur_ideco + cur_gakushi

        # ----------------------------------------------------
        # UI レイアウト
        # ----------------------------------------------------
        st.title(f"📊 家計簿ダッシュボード ({selected_sheet})")
        st.markdown(f"### 📍 【{selected_month}】 収支サマリー")

        # 1. KPI サマリーカード（預入合計・引出合計・収支合計）
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💰 預入合計 (行13)", f"¥{cur_income:,.0f}")
        k2.metric("💸 引出合計 (行85)", f"¥{cur_expense:,.0f}")
        k3.metric("⚖️ 収支 合計 (行89)", f"¥{cur_balance:,.0f}", 
                  delta="黒字" if cur_balance >= 0 else "赤字",
                  delta_color="normal" if cur_balance >= 0 else "inverse")
        k4.metric("🏦 銀行残高 合計", f"¥{cur_bank:,.0f}")

        # 資産形成・積立内訳
        st.markdown("##### 内部積立・資産形成")
        sub1, sub2, sub3, sub4 = st.columns(4)
        sub1.metric("🌱 積立NISA (行106)", f"¥{cur_nisa:,.0f}")
        sub2.metric("🛡️ iDeCo (行111)", f"¥{cur_ideco:,.0f}")
        sub3.metric("🎓 学資保険 (行117)", f"¥{cur_gakushi:,.0f}")
        sub4.metric("📊 資産形成 小計", f"¥{cur_invest_total:,.0f}")

        st.markdown("---")

        # ----------------------------------------------------
        # 2. 可視化セクション (年間推移グラフ)
        # ----------------------------------------------------
        st.markdown("#### 📈 年間 預入・引出・収支推移")
        
        trend_df = pd.DataFrame.from_dict(monthly_trend, orient="index").reset_index()
        trend_df.rename(columns={"index": "月"}, inplace=True)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=trend_df["月"], y=trend_df["預入合計"], name="預入合計", marker_color="#28a745"))
        fig.add_trace(go.Bar(x=trend_df["月"], y=trend_df["引出合計"], name="引出合計", marker_color="#dc3545"))
        fig.add_trace(go.Scatter(x=trend_df["月"], y=trend_df["収支合計"], name="収支 合計", mode="lines+markers", line=dict(color="#ffc107", width=3)))
        fig.add_trace(go.Scatter(x=trend_df["月"], y=trend_df["銀行残高合計"], name="銀行残高 合計", mode="lines+markers", line=dict(color="#007bff", width=2, dash="dash")))

        fig.update_layout(
            barmode="group",
            height=380,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # ----------------------------------------------------
        # 3. 明細データテーブル (1行目〜118行目)
        # ----------------------------------------------------
        st.markdown("#### 📋 家計簿明細テーブル (1行目〜118行目)")

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
            
            first_cell = str(row[0]).strip()
            is_highlight = any(k in first_cell for k in ["預入合計", "引出合計", "出費合計", "収支合計", "収支 合計", "銀行残高", "NISA", "イデコ", "学資保険"])
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
