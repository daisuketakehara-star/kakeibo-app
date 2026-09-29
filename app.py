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

# --- サイドバー設定 ---
st.sidebar.header("⚙️ ダッシュボード設定")
selected_sheet = st.sidebar.selectbox("表示年度（シート）", sheet_names, index=0)

try:
    data = load_raw_sheet_data(selected_sheet)
    
    if len(data) >= 2:
        title_row = data[0]  # 1行目（年・月）
        header_row = data[1] # 2行目（費目・実行日・口座名）
        body_rows = data[2:] # 3行目以降（データ）

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

        # 二重計算を防ぐための集計・小計・調整行キーワード
        exclude_keywords = [
            "合計", "小計", "平均", "預入合計", "引落合計", "口座別", "調整", "残高", "差引", "移動"
        ]

        # 収入・固定費・変動費・投資の分類関数
        def categorize_row(item_name):
            name = str(item_name).strip()
            # 集計行か判定
            if any(k in name for k in exclude_keywords):
                return "IGNORE"
            
            # 1. 収入
            income_keywords = ["給料", "給与", "賞与", "ボーナス", "児童手当", "手当", "還付", "年末調整", "利息", "雑収入"]
            if any(k in name for k in income_keywords):
                return "💰 収入"
                
            # 2. 投資・貯蓄
            invest_keywords = ["NISA", "iDeCo", "投資", "積立", "貯蓄", "投信", "株", "LOBO", "CRAFT"]
            if any(k in name for k in invest_keywords):
                return "📈 投資・貯蓄"
                
            # 3. 固定費
            fixed_keywords = ["ローン", "家賃", "電気", "ガス", "水道", "通信", "携帯", "スマホ", "保険", "学費", "保育", "管理費", "修繕", "新聞", "NHK"]
            if any(k in name for k in fixed_keywords):
                return "🏠 固定費"
                
            # 4. その他は変動費（カード引き落とし等を含む）
            return "🛍️ 変動費"

        # 年間トレンドと当月集計の計算
        monthly_trend = {m: {"収入": 0.0, "固定費": 0.0, "変動費": 0.0, "投資・貯蓄": 0.0} for m in months}
        categorized_rows = []

        for row in body_rows:
            if not any(row):
                continue
            item_name = row[0].strip()
            if not item_name:
                continue

            cat = categorize_row(item_name)
            if cat == "IGNORE":
                continue  # 二重計算防止のため集計行はスキップ
                
            categorized_rows.append((cat, row))

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

        # 当月の正確な数値
        cur_income = monthly_trend[selected_month]["収入"]
        cur_fixed = monthly_trend[selected_month]["固定費"]
        cur_variable = monthly_trend[selected_month]["変動費"]
        cur_invest = monthly_trend[selected_month]["投資・貯蓄"]
        cur_expense = cur_fixed + cur_variable
        cur_balance = cur_income - cur_expense - cur_invest

        # タイトル & サマリー
        st.title(f"📊 家計簿ダッシュボード ({selected_sheet})")
        st.markdown(f"### 📍 【{selected_month}】 収支サマリー")

        # ----------------------------------------------------
        # 1. サマリーセクション (KPI Cards)
        # ----------------------------------------------------
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("💰 収入", f"¥{cur_income:,.0f}")
        k2.metric("🏠 固定費", f"¥{cur_fixed:,.0f}")
        k3.metric("🛍️ 変動費・カード", f"¥{cur_variable:,.0f}")
        k4.metric("📈 投資・貯蓄", f"¥{cur_invest:,.0f}")
        k5.metric("⚖️ 収支差額", f"¥{cur_balance:,.0f}", 
                  delta="黒字" if cur_balance >= 0 else "赤字", 
                  delta_color="normal" if cur_balance >= 0 else "inverse")

        st.markdown("---")

        # ----------------------------------------------------
        # 2. 可視化セクション (Charts)
        # ----------------------------------------------------
        col_c1, col_c2 = st.columns([6, 4])

        with col_c1:
            st.markdown("#### 📈 年間収支推移 (月別)")
            trend_df = pd.DataFrame.from_dict(monthly_trend, orient="index").reset_index()
            trend_df.rename(columns={"index": "月"}, inplace=True)
            
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["収入"], name="収入", marker_color="#28a745"))
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["固定費"], name="固定費", marker_color="#ffc107"))
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["変動費"], name="変動費・カード", marker_color="#dc3545"))
            fig_bar.add_trace(go.Bar(x=trend_df["月"], y=trend_df["投資・貯蓄"], name="投資・貯蓄", marker_color="#17a2b8"))
            
            fig_bar.update_layout(barmode="group", height=320, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_c2:
            st.markdown(f"#### 🥧 {selected_month} 支出・投資の内訳")
            pie_data = {
                "区分": ["固定費", "変動費・カード", "投資・貯蓄"],
                "金額": [cur_fixed, cur_variable, cur_invest]
            }
            pie_df = pd.DataFrame(pie_data)
            pie_df = pie_df[pie_df["金額"] > 0]
            
            if not pie_df.empty:
                fig_pie = px.pie(
                    pie_df, values="金額", names="区分",
                    hole=0.4,
                    color="区分",
                    color_discrete_map={"固定費": "#ffc107", "変動費・カード": "#dc3545", "投資・貯蓄": "#17a2b8"}
                )
                fig_pie.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("選択された月のデータはありません。")

        st.markdown("---")

        # ----------------------------------------------------
        # 3. 明細データテーブル (スプレッドシート完全再現)
        # ----------------------------------------------------
        st.markdown("#### 📋 明細データテーブル (スプレッドシート連動)")

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

        # 全データ行を表示（区分バッジ付き）
        for row in body_rows:
            if not any(row):
                continue
            item_name = row[0].strip()
            cat = categorize_row(item_name)
            
            badge_html = ""
            if cat == "💰 収入":
                badge_html = '<span class="cat-badge cat-income">💰 収入</span>'
            elif cat == "📈 投資・貯蓄":
                badge_html = '<span class="cat-badge cat-invest">📈 投資</span>'
            elif cat == "🏠 固定費":
                badge_html = '<span class="cat-badge cat-fixed">🏠 固定費</span>'
            elif cat == "🛍️ 変動費":
                badge_html = '<span class="cat-badge cat-variable">🛍️ 変動費</span>'
            else:
                badge_html = '<span class="cat-badge" style="background-color:#e9ecef;color:#495057;">小計・集計</span>'

            html += f'<tr><td>{badge_html}</td>'
            
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
