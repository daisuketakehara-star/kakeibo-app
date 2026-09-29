import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
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

# 費目を「収入」「投資・貯蓄」「固定費」「変動費」に分類する関数
def classify_item(item_name):
    name = str(item_name).strip()
    income_keywords = ["給料", "給与", "賞与", "ボーナス", "手当", "還付", "収入", "売却"]
    if any(k in name for k in income_keywords):
        return "💰 収入"
    invest_keywords = ["NISA", "iDeCo", "投資", "積立", "貯蓄", "投信", "株", "資産"]
    if any(k in name for k in invest_keywords):
        return "📈 投資・貯蓄"
    fixed_keywords = ["ローン", "家賃", "電気", "ガス", "水道", "通信", "携帯", "スマホ", "保険", "学費", "保育", "管理費", "修繕", "サブスク"]
    if any(k in name for k in fixed_keywords):
        return "🏠 固定費"
    return "🛍️ 変動費"

# 文字列の数値を float に変換するヘルパー関数
def clean_num(val):
    if not val:
        return 0.0
    s = str(val).replace(",", "").replace("¥", "").replace("￥", "").replace("-", "0").strip()
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

# --- サイドバー設定 ---
st.sidebar.header("⚙️ ダッシュボード設定")
selected_sheet = st.sidebar.selectbox("表示年度（シート）", sheet_names, index=0)

try:
    data = load_raw_sheet_data(selected_sheet)
    
    if len(data) >= 2:
        title_row = data[0]  # 1行目（年・月）
        header_row = data[1] # 2行目（費目・実行日・口座名）
        body_rows = data[2:] # 3行目以降（データ）

        # 月リストの抽出（「4月」「5月」など）
        months = []
        month_col_indices = {} # 月ごとに対応する列インデックスリスト
        current_m = ""
        for idx, cell in enumerate(title_row):
            m_clean = cell.replace("[merged]", "").strip()
            if m_clean and ("月" in m_clean or m_clean in ["合計", "平均"]):
                current_m = m_clean
            if current_m and "月" in current_m:
                if current_m not in months:
                    months.append(current_m)
                    month_col_indices[current_m] = []
                month_col_indices[current_m].append(idx)

        # サイドバーで対象月を選択
        selected_month = st.sidebar.selectbox("分析対象月を選択", months, index=0)

        # 集計計算
        month_indices = month_col_indices.get(selected_month, [])
        total_income = 0.0
        total_invest = 0.0
        total_fixed = 0.0
        total_variable = 0.0

        monthly_trend = {m: {"収入": 0.0, "固定費": 0.0, "変動費": 0.0, "投資・貯蓄": 0.0} for m in months}

        categorized_rows = []
        for row in body_rows:
            if not any(row):
                continue
            item_name = row[0]
            cat = classify_item(item_name)
            categorized_rows.append((cat, row))

            # 当月および年間全月の集計
            for m in months:
                for c_idx in month_col_indices[m]:
                    if c_idx < len(row):
                        val = clean_num(row[c_idx])
                        if cat == "💰 収入":
                            monthly_trend[m]["収入"] += val
                        elif cat == "📈 投資・貯蓄":
                            monthly_trend[m]["投資・貯蓄"] += val
                        elif cat == "🏠 固定費":
                            monthly_trend[m]["固定費"] += val
                        elif cat == "🛍️ 変動費":
                            monthly_trend[m]["変動費"] += val

        total_income = monthly_trend[selected_month]["収入"]
        total_invest = monthly_trend[selected_month]["投資・貯蓄"]
        total_fixed = monthly_trend[selected_month]["固定費"]
        total_variable = monthly_trend[selected_month]["変動費"]
        total_expense = total_fixed + total_variable
        net_balance = total_income - total_expense - total_invest

        # HEADER & TITLE
        st.title(f"📊 家計簿ダッシュボード ({selected_sheet})")
        st.markdown(f"### 📍 【{selected_month}】 収支サマリー")

        # ----------------------------------------------------
        # 1. サマリーセクション (KPI Cards)
        # ----------------------------------------------------
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("💰 収入", f"¥{total_income:,.0f}")
        kpi2.metric("🏠 固定費", f"¥{total_fixed:,.0f}")
        kpi3.metric("🛍️ 変動費", f"¥{total_variable:,.0f}")
        kpi4.metric("📈 投資・貯蓄", f"¥{total_invest:,.0f}")
        kpi5.metric("⚖️ 収支差額", f"¥{net_balance:,.0f}", delta=f"{'黒字' if net_balance >= 0 else '赤字'}", delta_color="normal" if net_balance >= 0 else "inverse")

        st.markdown("---")

        # ----------------------------------------------------
        # 2. 可視化セクション (Charts)
        # ----------------------------------------------------
        col_chart1, col_chart2 = st.columns([6, 4])

        with col_chart1:
            st.markdown("#### 📈 年間収支推移 (月別)")
            trend_df = pd.DataFrame.from_dict(monthly_trend, orient="index").reset_index()
            trend_df.rename(columns={"index": "月"}, inplace=True)
            
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["収入"], name="収入", marker_color="#28a745"))
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["固定費"], name="固定費", marker_color="#ffc107"))
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["変動費"], name="変動費", marker_color="#dc3545"))
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["投資・貯蓄"], name="投資・貯蓄", marker_color="#17a2b8"))
            
            fig_bar.update_layout(barmode="group", height=320, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_chart2:
            st.markdown(f"#### 🥧 {selected_month} 支出・投資内訳")
            pie_data = {
                "区分": ["固定費", "変動費", "投資・貯蓄"],
                "金額": [total_fixed, total_variable, total_invest]
            }
            pie_df = pd.DataFrame(pie_data)
            pie_df = pie_df[pie_df["金額"] > 0]
            
            if not pie_df.empty:
                fig_pie = px.pie(
                    pie_df, values="金額", names="区分",
                    hole=0.4,
                    color="区分",
                    color_discrete_map={"固定費": "#ffc107", "変動費": "#dc3545", "投資・貯蓄": "#17a2b8"}
                )
                fig_pie.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("選択された月の支出・投資データがありません。")

        st.markdown("---")

        # ----------------------------------------------------
        # 3. 明細データセクション (Table)
        # ----------------------------------------------------
        st.markdown("#### 📋 明細データテーブル (スプレッドシート連動)")

        # 1行目の結合セルを展開解析
        header_groups = [("区分", 1)]
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

        # HTML テーブル構築
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

        for val, span in header_groups:
            html += f'<th colspan="{span}">{val}</th>'
        html += "</tr><tr><th>区分</th>"

        for idx, col in enumerate(header_row):
            sticky_class = ' class="sticky-col"' if idx == 0 else ''
            html += f'<th{sticky_class}>{col}</th>'
        html += "</tr></thead><tbody>"

        for cat, row in categorized_rows:
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

        st.components.v1.html(html, height=600, scrolling=True)

    else:
        st.warning("シートに十分なデータがありません。")

except Exception as e:
    st.error(f"データ取得・描画エラー: {e}")
