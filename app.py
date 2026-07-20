# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, date, time, timezone
from streamlit_gsheets import GSheetsConnection
import threading
import time as time_module

# ==========================================
# 1. 系統設定與網頁配置（內嵌行動端手機自適應 CSS 盾牌）
# ==========================================
st.set_page_config(page_title="個人智慧投資紀錄簿", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @media (max-width: 768px) {
        .main h1 { font-size: 1.8rem !important; }
        .main h2 { font-size: 1.4rem !important; }
        .main h3 { font-size: 1.1rem !important; }
        [data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
            gap: 10px !important;
        }
        div[data-testid="stDataFrame"] table {
            font-size: 12px !important;
        }
        div[data-testid="stDataFrame"] td, div[data-testid="stDataFrame"] th {
            padding: 4px 6px !important;
        }
        .stAlert { padding: 10px !important; }
    }
</style>
""", unsafe_allow_html=True)

# 建立 Google Sheets 連結物件
conn = st.connection("gsheets", type=GSheetsConnection)

# 安全檢查
if "connections" not in st.secrets or "gsheets" not in st.secrets["connections"] or "spreadsheet" not in st.secrets["connections"]["gsheets"]:
    st.error("⚠️ 偵測到雲端設定錯誤！請檢查 Streamlit Cloud 控制台中的 Secrets 設定。")
    st.stop()

if "is_api_blocked" not in st.session_state:
    st.session_state["is_api_blocked"] = False

if "last_scheduled_trigger" not in st.session_state:
    st.session_state["last_scheduled_trigger"] = ""

# ==========================================
# 🗺️ 時區防禦核心：強制取得台灣本地時間 (UTC+8)
# ==========================================
def get_taiwan_now():
    utc_now = datetime.now(timezone.utc)
    taiwan_tz = timezone(timedelta(hours=8))
    return utc_now.astimezone(taiwan_tz)

# ==========================================
# 🛡️ 流量防護盾：快取時間歸零（完全即時直連）
# ==========================================
@st.cache_data(ttl=0)  
def cached_read_sheets(worksheet_name):
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        if df is not None and not df.empty:
            df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]
        return df
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 🔒 登入專用：直連雲端帳密讀取函數 (TTL=0)
# ==========================================
def fetch_credentials_live():
    for attempt in range(3):
        try:
            df = conn.read(worksheet="user_credentials", ttl=0)
            if df is not None and not df.empty:
                df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]
                return df
        except Exception:
            time_module.sleep(0.5)
    return pd.DataFrame()

# ==========================================
# 🏦 自動化：動態貸款餘額扣除計算函式
# ==========================================
def calculate_remaining_loans(current_date):
    l1_base = 1000000
    l1_day = 20
    l1_pay = 12797
    l1_base_date = date(2024, 4, 20)
    
    l2_base = 2000000
    l2_day = 10
    l2_pay = 18872
    l2_base_date = date(2026, 4, 10)
    
    l1_payments = 0
    start_yr_1, start_mo_1 = l1_base_date.year, l1_base_date.month
    end_yr, end_mo = current_date.year, current_date.month
    
    current_yr, current_mo = start_yr_1, start_mo_1
    while (current_yr < end_yr) or (current_yr == end_yr and current_mo <= end_mo):
        pay_date_l1 = date(current_yr, current_mo, l1_day)
        if l1_base_date <= pay_date_l1 <= current_date:
            l1_payments += 1
        if current_mo == 12:
            current_mo = 1
            current_yr += 1
        else:
            current_mo += 1
            
    l2_payments = 0
    start_yr_2, start_mo_2 = l2_base_date.year, l2_base_date.month
    
    current_yr, current_mo = start_yr_2, start_mo_2
    while (current_yr < end_yr) or (current_yr == end_yr and current_mo <= end_mo):
        pay_date_l2 = date(current_yr, current_mo, l2_day)
        if l2_base_date <= pay_date_l2 <= current_date:
            l2_payments += 1
        if current_mo == 12:
            current_mo = 1
            current_yr += 1
        else:
            current_mo += 1
            
    l1_rem = 682586
    l2_rem = 1941174
    
    return l1_rem, l2_rem, l1_payments, l2_payments

# ==========================================
# 🔒 系統安全登入驗證機制
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.markdown("<h2 style='text-align: center;'>🔒 智慧投資紀錄簿 - 系統登入</h2>", unsafe_allow_html=True)
    st.write("")
    col_space1, col_login, col_space2 = st.columns([1, 2, 1])
    with col_login:
        with st.form("login_form", clear_on_submit=False):
            username_input = st.text_input("請輸入管理員帳號：")
            password_input = st.text_input("請輸入密碼：", type="password")
            submit_login = st.form_submit_button("🚀 安全登入", use_container_width=True)
            
            if submit_login:
                with st.spinner("正在安全連線至驗證伺服器..."):
                    df_creds = fetch_credentials_live()
                    if not df_creds.empty:
                        df_creds = df_creds.dropna(subset=["帳號", "密碼"])
                        match = df_creds[
                            (df_creds["帳號"].astype(str) == username_input) & 
                            (df_creds["密碼"].astype(str) == password_input)
                        ]
                        if not match.empty:
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = username_input
                            st.success("🎉 登入成功！正在跳轉...")
                            st.rerun()
                        else:
                            st.error("❌ 帳號或密碼錯誤，請重新確認！")
                    else:
                        st.error("❌ 無法讀取認證資料表。請確認網路連線或稍後重試。")
    st.stop()

# ==========================================
# 🎯 核心清算機：直接讀取試算表「當前市值」公式欄位，並過濾清除 Unnamed
# ==========================================
def calculate_absolute_portfolio_mv(df_portfolio_raw):
    df = df_portfolio_raw.copy()
    df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]
    
    df['當前市值'] = pd.to_numeric(df['當前市值'], errors='coerce').fillna(0.0)
    total_mv = df['當前市值'].sum()
    
    return df, total_mv

# ==========================================
# 🔄 系統核心引擎：完美台灣時區 Upsert 與公式保護
# ==========================================
def execute_system_wide_sync(custom_connection=None):
    try:
        active_conn = custom_connection if custom_connection else conn
        
        df_history_sync = active_conn.read(worksheet="daily_asset_history", ttl=0)
        df_portfolio_sync = active_conn.read(worksheet="portfolio_config", ttl=0)
        
        df_history_sync = df_history_sync.dropna(subset=["日期"])
        df_portfolio_sync = df_portfolio_sync.dropna(subset=["標的名稱"])
        
        df_history_sync = df_history_sync.loc[:, ~df_history_sync.columns.astype(str).str.contains('^Unnamed')]
        df_portfolio_sync = df_portfolio_sync.loc[:, ~df_portfolio_sync.columns.astype(str).str.contains('^Unnamed')]
        
        df_history_sync['開時日期'] = pd.to_datetime(df_history_sync['開時日期'] if '開時日期' in df_history_sync.columns else df_history_sync['開時日期'] if '開時日期' in df_history_sync.columns else df_history_sync['日期']).dt.strftime("%Y-%m-%d")
        
        df_portfolio_sync, total_mv_calculated = calculate_absolute_portfolio_mv(df_portfolio_sync)
        total_cost_calculated = pd.to_numeric(df_portfolio_sync['投資成本'], errors='coerce').fillna(0.0).sum()
        
        tw_now = get_taiwan_now()
        today_str = tw_now.strftime("%Y-%m-%d")
        
        df_history_sorted = df_history_sync.copy()
        df_history_sorted['開時日期_temp'] = pd.to_datetime(df_history_sorted['開時日期'] if '開時日期' in df_history_sorted.columns else df_history_sorted['日期']).dt.strftime("%Y-%m-%d")
        df_yesterday = df_history_sorted[df_history_sorted['開時日期_temp'] < today_str]
        
        last_total_asset = float(df_yesterday['總資產金額'].iloc[-1]) if not df_yesterday.empty else total_mv_calculated
        daily_diff = total_mv_calculated - last_total_asset
        daily_roi = round((total_mv_calculated - total_cost_calculated) / total_cost_calculated, 4) if total_cost_calculated > 0 else 0.0
        
        if today_str in df_history_sync['開時日期'].values:
            df_history_sync.loc[df_history_sync['開時日期'] == today_str, ["總資產金額", "每日增額", "每日報酬率"]] = [
                int(round(total_mv_calculated)), int(round(daily_diff)), float(daily_roi)
            ]
            df_history_sync.loc[df_history_sync['開時日期'] == today_str, "日期"] = today_str
        else:
            new_row_data = {
                "日期": today_str,
                "總資產金額": int(round(total_mv_calculated)),
                "每日增額": int(round(daily_diff)),
                "每日報酬率": float(daily_roi)
            }
            df_history_sync = pd.concat([df_history_sync, pd.DataFrame([new_row_data])], ignore_index=True)
            
        if '開時日期' in df_history_sync.columns:
            df_history_sync = df_history_sync.drop(columns=['開時日期'])

        final_upload_df = df_portfolio_sync.copy()
        final_upload_df['個股現價'] = final_upload_df['個股現價'].astype(str)
        
        for idx, row in final_upload_df.iterrows():
            ticker = str(row.get('Yahoo代號', '')).strip()
            name = str(row.get('標的名稱', '')).strip()
            
            if "USDTWD" in ticker.upper() or "CURRENCY" in ticker.upper() or "匯率" in name:
                final_upload_df.at[idx, '個股現價'] = '=GOOGLEFINANCE("CURRENCY:USDTWD")'
            elif any(k in ticker for k in ['台幣', '現金']) or any(k in name for k in ['台幣', '現金']) or ticker == '' or ticker.lower() == 'nan':
                continue
            else:
                if ":" in ticker:
                    final_upload_df.at[idx, '個股現價'] = f'=GOOGLEFINANCE("{ticker}", "price")'
                elif "QQQM" in ticker.upper():
                    final_upload_df.at[idx, '個股現價'] = '=GOOGLEFINANCE("NASDAQ:QQQM", "price")'
                elif ticker.upper().endswith('.TW'):
                    stock_code = ticker.split('.')[0]
                    final_upload_df.at[idx, '個股現價'] = f'=GOOGLEFINANCE("TPE:{stock_code}")'
                else:
                    final_upload_df.at[idx, '個股現價'] = f'=GOOGLEFINANCE("{ticker}")'
                    
        final_upload_df = final_upload_df.drop(
            columns=['單位現價', '目前投資占比', '偏離度 (Diff)', '買賣建議'], 
            errors='ignore'
        )
        final_upload_df = final_upload_df.loc[:, ~final_upload_df.columns.astype(str).str.contains('^Unnamed')]
        df_history_sync = df_history_sync.loc[:, ~df_history_sync.columns.astype(str).str.contains('^Unnamed')]
        
        active_conn.update(worksheet="daily_asset_history", data=df_history_sync)
        active_conn.update(worksheet="portfolio_config", data=final_upload_df)
        return True
    except Exception:
        return False

# ==========================================
# 🔄 執行緒安全之台灣時區自動排程守護引擎
# ==========================================
def background_scheduler(static_times):
    while True:
        try:
            tw_now = get_taiwan_now()
            current_time_str = tw_now.strftime("%H:%M")
            current_date_str = tw_now.strftime("%Y-%m-%d")
            trigger_id = f"{current_date_str}_{current_time_str}"
            
            if current_time_str in static_times:
                if st.session_state.get("last_scheduled_trigger", "") != trigger_id:
                    bg_conn = st.connection("gsheets", type=GSheetsConnection)
                    success = execute_system_wide_sync(custom_connection=bg_conn)
                    if success:
                        st.session_state["last_scheduled_trigger"] = trigger_id
        except Exception:
            pass
        time_module.sleep(30)

# ==========================================
# 3. 側邊導覽列與功能選單配置
# ==========================================
st.sidebar.title("🧭 投資導覽控制台")
st.sidebar.write(f"👤 目前使用者：`{st.session_state['username']}`")

st.sidebar.markdown("---")
st.sidebar.subheader("⏰ 雲端持久化自動排程設定")

df_load_sched = cached_read_sheets("scheduler_config")
if df_load_sched.empty or "觸發時間" not in df_load_sched.columns:
    initial_times = ["14:00"]
else:
    initial_times = df_load_sched["觸發時間"].dropna().astype(str).tolist()

init_count = min(max(len(initial_times), 1), 5)
num_times = st.sidebar.number_input("設定每日定時更新次數 (最多5次)：", min_value=1, max_value=5, value=init_count, step=1)

scheduled_times_list = []
for i in range(int(num_times)):
    if i < len(initial_times):
        try:
            t_parts = list(map(int, initial_times[i].split(":")))
            default_t = time(hour=t_parts[0], minute=t_parts[1])
        except:
            default_t = time(hour=14, minute=0)
    else:
        default_t = time(hour=14, minute=0)
        
    chosen_time = st.sidebar.time_input(f"選擇第 {i+1} 組同步時間點：", default_t, key=f"sched_persist_t_{i}")
    scheduled_times_list.append(chosen_time.strftime("%H:%M"))

if st.sidebar.button("💾 儲存並啟用雲端排程", use_container_width=True):
    df_save_sched = pd.DataFrame({
        "排程順序": [f"第 {x+1} 組" for x in range(len(scheduled_times_list))],
        "觸發時間": scheduled_times_list
    })
    with st.spinner("正在將排程時間寫入 Google Sheets..."):
        conn.update(worksheet="scheduler_config", data=df_save_sched)
    st.sidebar.success("🎉 排程時間成功固化！")
    st.cache_data.clear()
    st.rerun()

if "scheduler_thread_started" not in st.session_state:
    t = threading.Thread(target=background_scheduler, args=(scheduled_times_list,), daemon=True)
    t.start()
    st.session_state["scheduler_thread_started"] = True

menu = st.sidebar.radio("請選擇操作功能：", ["📊 投資總覽儀表板", "✍️ 每日資產動態輸入", "⚙️ 投資標的持股管理"])

st.sidebar.markdown("---")
if st.sidebar.button("🔓 安全登出系統", use_container_width=True):
    st.session_state["logged_in"] = False
    st.session_state["username"] = None
    st.rerun()

# ==========================================
# 功能一：📊 投資總覽儀表板
# ==========================================
if menu == "📊 投資總覽儀表板":
    st.title("📊 個人即時投資動態儀表板 (Google Sheets 同步)")
    
    df_history = cached_read_sheets("daily_asset_history")
    df_portfolio = cached_read_sheets("portfolio_config")
    
    if df_history.empty or df_portfolio.empty:
        st.error("⚠️ 無法載入必要的工作表資料，請稍後再試。")
        st.stop()
        
    # 🏦 信用貸款明細
    tw_today_date = get_taiwan_now().date()
    l1_remain, l2_remain, l1_pay_count, l2_pay_count = calculate_remaining_loans(tw_today_date)
    total_loan_balance = l1_remain + l2_remain
    
    st.markdown("### 🏦 信用貸款與槓桿監控明細")
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        st.info(f"""
        **信貸第一主線 (L1)**
        * 原始借貸本金：`$1,000,000 TWD`
        * 已繳款期數：`{l1_pay_count} 期` (每月20日自動扣繳 `$12,797`)
        * **當前剩餘本金：${l1_remain:,.0f} TWD**
        """)
    with col_l2:
        st.info(f"""
        **信貸第二主線 (L2)**
        * 原始借貸本金：`$2,000,000 TWD`
        * 已繳款期數：`{l2_pay_count} 期` (每月10日自動扣繳 `$18,872`)
        * **當前剩餘本金：${l2_remain:,.0f} TWD**
        """)
        
    # 直連市值清算
    df_portfolio, total_market_value = calculate_absolute_portfolio_mv(df_portfolio)
    total_cost = pd.to_numeric(df_portfolio['投資成本'], errors='coerce').fillna(0.0).sum()
    total_profit = total_market_value - total_cost
    total_roi = (total_profit / total_cost) if total_cost > 0 else 0.0

    st.markdown("### ⚡️ 快速同步控制區")
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        sync_clicked = st.button("🔄 立即同步最新資產至 Google 雲端", use_container_width=True)
    with col_info:
        st.info("💡 雲端優化限流版：排程在無人造訪時採用快取機制保護，杜絕觸發 Google 429 錯誤限流配額。")
        
    if sync_clicked:
        with st.spinner('正在從 Google 試算表直接對齊市值欄位清算...'):
            res = execute_system_wide_sync()
            if res:
                st.success(f"🎉 成功同步！請重新整理網頁！")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ 同步失敗，請稍後再試。")
                
    st.markdown("---")
    
    # 四大 KPI 數據卡片呈現（🎯 已完成四捨五入整數化與 TWD 標籤加註）
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("當前總市值 (TWD)", f"${round(total_market_value):,.0f}")
    col2.metric("投資總成本 (TWD)", f"${round(total_cost):,.0f}")
    col3.metric("累積投資獲利 (TWD)", f"${round(total_profit):,.0f}", delta=f"{total_roi*100:.2f}% 報酬率")
    
    maintenance_rate = (total_market_value / total_loan_balance) if total_loan_balance > 0 else 0
    col4.metric("質押維持率", f"{maintenance_rate*100:.2f}%", delta="✅ 水位強韌" if maintenance_rate > 1.6 else "⚠️ 需注意風險")

    # ==========================================
    # KPI 核心指標深度視覺化圖表區 (瀑布圖 & 風險指針盤)
    # ==========================================
    st.markdown("### 📈 核心資產結構與風險水位視覺化")
    col_v1, col_v2 = st.columns(2)

    with col_v1:
        fig_waterfall = go.Figure(go.Waterfall(
            name="資產結構",
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["投資總成本", "累積投資獲利", "當前總市值"],
            textposition="outside",
            text=[f"${total_cost:,.0f}", f"+${total_profit:,.0f}", f"${total_market_value:,.0f}"],
            y=[total_cost, total_profit, total_market_value],
            connector={"line": {"color": "rgba(100, 100, 100, 0.5)", "width": 1}},
            decreasing={"marker": {"color": "#FF6384"}}, 
            increasing={"marker": {"color": "#2ecc71"}}, 
            totals={"marker": {"color": "#3498db"}}     
        ))
        fig_waterfall.update_layout(
            title={'text': "🎯 資產價值階梯增長圖 (TWD)", 'y': 0.9, 'x': 0.5, 'xanchor': 'center', 'yanchor': 'top'},
            height=320, margin=dict(t=60, b=30, l=40, r=40),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_waterfall, use_container_width=True)

    with col_v2:
        current_rate_pct = maintenance_rate * 100 if maintenance_rate <= 100 else maintenance_rate
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=current_rate_pct,
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [0, 600], 'tickwidth': 1, 'tickcolor': "#888888", 'tickformat': '.0f'},
                'bar': {'color': "#2c3e50", 'thickness': 0.25}, 
                'bgcolor': "rgba(0,0,0,0)", 'borderwidth': 1, 'bordercolor': "#aaaaaa",
                'steps': [
                    {'range': [0, 160], 'color': 'rgba(231, 76, 60, 0.3)'},   
                    {'range': [160, 190], 'color': 'rgba(241, 196, 15, 0.3)'}, 
                    {'range': [190, 600], 'color': 'rgba(46, 204, 113, 0.2)'}  
                ],
                'threshold': {'line': {'color': "#e74c3c", 'width': 3}, 'thickness': 0.75, 'value': 160}
            }
        ))
        fig_gauge.update_layout(
            title={'text': "🛡️ 質押信用維持率風險警示盤", 'y': 0.9, 'x': 0.5, 'xanchor': 'center', 'yanchor': 'top'},
            height=320, margin=dict(t=60, b=30, l=40, r=40), paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    # ==========================================
    # 📊 歷史資產與報酬率歷史趨勢圖
    # ==========================================
    st.markdown("---")
    st.subheader("📈 智慧數據歷史趨勢儀表板")
    
    chart_range_option = st.radio(
        "選擇歷史趨勢圖顯示區間：",
        ["近 7 天", "近 30 天", "近 180 天", "今年以來 (YTD)", "全部顯示"],
        horizontal=True,
        key="dashboard_chart_range"
    )
    
    col_chart1, col_chart2 = st.columns([2, 3])
    
    with col_chart1:
        st.markdown("##### 🎯 1. 核心投資標的市值佔比")
        df_pie_data = df_portfolio[df_portfolio['當前市值'] > 0]
        fig_pie = px.pie(
            df_pie_data, 
            values='當前市值', 
            names='標的名稱',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=350, showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with col_chart2:
        st.markdown("##### 📊 2. 資產規模與每日報酬率歷史趨勢合併圖")
        if not df_history.empty:
            df_chart_hist = df_history.copy()
            df_chart_hist['開設日期_parsed'] = pd.to_datetime(df_chart_hist['日期'])
            df_chart_hist = df_chart_hist.sort_values(by='開設日期_parsed')
            tw_now_chart = get_taiwan_now()
            
            if chart_range_option == "近 7 天":
                start_dt = tw_now_chart - timedelta(days=7)
                df_chart_hist = df_chart_hist[df_chart_hist['開設日期_parsed'] >= pd.to_datetime(start_dt.date())]
            elif chart_range_option == "近 30 天":
                start_dt = tw_now_chart - timedelta(days=30)
                df_chart_hist = df_chart_hist[df_chart_hist['開設日期_parsed'] >= pd.to_datetime(start_dt.date())]
            elif chart_range_option == "近 180 天":
                start_dt = tw_now_chart - timedelta(days=180)
                df_chart_hist = df_chart_hist[df_chart_hist['開設日期_parsed'] >= pd.to_datetime(start_dt.date())]
            elif chart_range_option == "今年以來 (YTD)":
                start_dt = datetime(tw_now_chart.year, 1, 1)
                df_chart_hist = df_chart_hist[df_chart_hist['開設日期_parsed'] >= pd.to_datetime(start_dt)]
            
            fig_combined = make_subplots(specs=[[{"secondary_y": True}]])
            fig_combined.add_trace(
                go.Bar(
                    x=df_chart_hist['日期'], 
                    y=df_chart_hist['開設日期_parsed'].map(lambda x: df_chart_hist.loc[df_chart_hist['開設日期_parsed'] == x, '總資產金額'].values[0]), 
                    name="資產總金額 (元)",
                    marker_color='rgba(100, 149, 237, 0.6)',
                    hovertemplate='日期: %{x}<br>總資產: $%{y:,.0f} TWD'
                ),
                secondary_y=False
            )
            fig_combined.add_trace(
                go.Scatter(
                    x=df_chart_hist['日期'], 
                    y=df_chart_hist['每日報酬率'] * 100, 
                    name="累積報酬率 (%)",
                    mode='lines+markers',
                    line=dict(color='rgb(220, 20, 60)', width=2),
                    marker=dict(size=5),
                    hovertemplate='日期: %{x}<br>報酬率: %{y:.2f}%'
                ),
                secondary_y=True
            )
            fig_combined.update_layout(
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(t=20, b=20, l=10, r=10), height=350, hovermode="x unified"
            )
            fig_combined.update_yaxes(title_text="資產總金額 (TWD)", secondary_y=False, gridcolor='rgba(200,200,200,0.2)')
            fig_combined.update_yaxes(title_text="累積報酬率 (%)", secondary_y=True)
            st.plotly_chart(fig_combined, use_container_width=True)
        else:
            st.info("💡 暫無歷史趨勢數據可供轉換渲染。")

    st.markdown("---")
    st.subheader("🎯 核心資產再平衡與偏離度檢查")
    df_portfolio['目前投資占比'] = df_portfolio['當前市值'] / total_market_value if total_market_value > 0 else 0
    df_portfolio['偏離度 (Diff)'] = df_portfolio['目前投資占比'] - df_portfolio['核心權重']

    def generate_advice(row):
        if row['偏離度 (Diff)'] > 0.05:
            return f"⚠️ 建議減碼 {row['標的名稱']}"
        elif row['偏離度 (Diff)'] < -0.05:
            return f"🛒 建議加碼 {row['標的名稱']}"
        else:
            return "✅ 權重正常"
            
    df_portfolio['買賣建議'] = df_portfolio.apply(generate_advice, axis=1)
    st.dataframe(df_portfolio[['標的名稱', '核心權重', '個股現價', '持有數量', '當前市值', '目前投資占比', '偏離度 (Diff)', '買賣建議']].style.format({
        '核心權重': '{:.1%}', '個股現價': '${:,.2f}', '持有數量': '{:.0f}', '當前市值': '${:,.2f}', '目前投資占比': '{:.1%}', '偏離度 (Diff)': '{:+.1%}'
    }))

# ==========================================
# 功能二：✍️ 每日資產動態輸入
# ==========================================
elif menu == "✍️ 每日資產動態輸入":
    st.title("✍️ 每日資產金額輕鬆記")
    df_history = cached_read_sheets("daily_asset_history")
    df_portfolio = cached_read_sheets("portfolio_config")
    
    if not df_history.empty and not df_portfolio.empty:
        total_cost = pd.to_numeric(df_portfolio['投資成本'], errors='coerce').fillna(0.0).sum()
        
        with st.form("daily_input_form", clear_on_submit=True):
            input_date = st.date_input("選擇紀錄日期：", get_taiwan_now())
            input_amount = st.number_input("今日結算總資產金額 (TWD)：", min_value=0.0, step=1000.0, format="%.2f")
            submit_button = st.form_submit_button(label="🚀 提交並儲存至 Google Sheets")
            
            if submit_button:
                date_str = str(input_date)
                df_history['開時日期'] = pd.to_datetime(df_history['開時日期'] if '開時日期' in df_history.columns else df_history['日期']).dt.strftime("%Y-%m-%d")
                
                df_history_temp = df_history.copy()
                df_yesterday = df_history_temp[df_history_temp['開時日期'] < date_str]
                if not df_yesterday.empty:
                    last_amount = float(df_yesterday['總資產金額'].iloc[-1])
                    daily_diff = input_amount - last_amount
                else:
                    daily_diff = 0.0
                    
                daily_roi = round((input_amount - total_cost) / total_cost, 4) if total_cost > 0 else 0.0
                input_amount_rounded = int(round(input_amount))
                daily_diff_rounded = int(round(daily_diff))
                    
                new_data = {
                    "開時日期": date_str,
                    "總資產金額": input_amount_rounded,
                    "每日增額": daily_diff_rounded,
                    "每日報酬率": float(daily_roi),
                    "日期": date_str
                }
                
                if date_str in df_history['開時日期'].values:
                    df_history.loc[df_history['開時日期'] == date_str, ["總資產金額", "每日增額", "每日報酬率", "日期"]] = [
                        input_amount_rounded, daily_diff_rounded, float(daily_roi), date_str
                    ]
                else:
                    df_history = pd.concat([df_history, pd.DataFrame([new_data])], ignore_index=True)
                
                if '開時日期' in df_history.columns:
                    df_history = df_history.drop(columns=['開時日期'])
                    
                with st.spinner('正在寫入...'):
                    conn.update(worksheet="daily_asset_history", data=df_history)
                st.success("🎉 成功同步至雲端試算表！數值已自動四捨五入為整數。")
                st.cache_data.clear()
                
        st.markdown("---")
        st.subheader("📋 歷史資產紀錄查詢與管理")
        
        search_option = st.radio(
            "選擇歷史紀錄查詢區間：",
            ["近 7 天", "近 30 天", "近 180 天", "今年以來 (YTD)", "全部顯示"],
            horizontal=True
        )
        
        df_display = df_history.copy()
        df_display['開資料日期_parsed'] = pd.to_datetime(df_display['日期'])
        df_display = df_display.sort_values(by="開資料日期_parsed", ascending=False)
        tw_now_display = get_taiwan_now()
        
        if search_option == "近 7 天":
            start_date = tw_now_display - timedelta(days=7)
            df_display = df_display[df_display['開資料日期_parsed'] >= pd.to_datetime(start_date.date())]
        elif search_option == "近 30 天":
            start_date = tw_now_display - timedelta(days=30)
            df_display = df_display[df_display['開資料日期_parsed'] >= pd.to_datetime(start_date.date())]
        elif search_option == "近 180 天":
            start_date = tw_now_display - timedelta(days=180)
            df_display = df_display[df_display['開資料日期_parsed'] >= pd.to_datetime(start_date.date())]
        elif search_option == "今年以來 (YTD)":
            start_date = datetime(tw_now_display.year, 1, 1)
            df_display = df_display[df_display['開資料日期_parsed'] >= pd.to_datetime(start_date)]
            
        df_display['日期'] = df_display['開資料日期_parsed'].dt.strftime("%Y-%m-%d")
        df_display['總資產金額'] = pd.to_numeric(df_display['總資產金額'], errors='coerce').fillna(0).round().astype(int)
        df_display['每日增額'] = pd.to_numeric(df_display['每日增額'], errors='coerce').fillna(0).round().astype(int)
        
        rows_per_page = 10
        total_rows = len(df_display)
        
        if total_rows > 0:
            total_pages = int(np.ceil(total_rows / rows_per_page))
            current_page = st.number_input(f"頁碼 (共 {total_pages} 頁)", min_value=1, max_value=total_pages, value=1, step=1)
            start_idx = (current_page - 1) * rows_per_page
            end_idx = start_idx + rows_per_page
            st.dataframe(df_display[['日期', '總資產金額', '每日增額', '每日報酬率']].iloc[start_idx:end_idx], use_container_width=True)

# ==========================================
# 功能三：⚙️ 投資標的持股管理
# ==========================================
elif menu == "⚙️ 投資標的持股管理":
    st.title("⚙️ 投資標的與持股數量管理")
    
    try:
        df_portfolio_raw = conn.read(worksheet="portfolio_config", ttl=0)
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        st.stop()
        
    st.subheader("✏️ 線上編輯持股資訊")
    st.info("💡 智慧公式保護網已部署：您可以自由修改標的、數量與成本。系統回寫時會全自動過濾並剔除多餘的 Unnamed 空白欄位，捍衛試算表結構！")
    
    df_portfolio_raw = df_portfolio_raw.loc[:, ~df_portfolio_raw.columns.astype(str).str.contains('^Unnamed')]
    edited_df = st.data_editor(df_portfolio_raw, num_rows="dynamic", key="portfolio_safe_editor")
    
    if st.button("💾 儲存並同步至 Google Sheets"):
        with st.spinner('正在重新編譯並還原 Google 試算表公式...'):
            try:
                final_upload_df = edited_df.copy()
                final_upload_df['個股現價'] = final_upload_df['個股現價'].astype(str)
                
                for idx, row in final_upload_df.iterrows():
                    ticker = str(row.get('Yahoo代號', '')).strip()
                    name = str(row.get('標的名稱', '')).strip()
                    
                    if "USDTWD" in ticker.upper() or "CURRENCY" in ticker.upper() or "匯率" in name:
                        final_upload_df.at[idx, '個股現價'] = '=GOOGLEFINANCE("CURRENCY:USDTWD")'
                    elif any(k in ticker for k in ['台幣', '現金']) or any(k in name for k in ['台幣', '現金']) or ticker == '' or ticker.lower() == 'nan':
                        continue
                    else:
                        if ":" in ticker:
                            final_upload_df.at[idx, '個股現價'] = f'=GOOGLEFINANCE("{ticker}", "price")'
                        elif "QQQM" in ticker.upper():
                            final_upload_df.at[idx, '個股現價'] = '=GOOGLEFINANCE("NASDAQ:QQQM", "price")'
                        elif ticker.upper().endswith('.TW'):
                            stock_code = ticker.split('.')[0]
                            final_upload_df.at[idx, '個股現價'] = f'=GOOGLEFINANCE("TPE:{stock_code}")'
                        else:
                            final_upload_df.at[idx, '個股現價'] = f'=GOOGLEFINANCE("{ticker}")'
                
                final_upload_df = final_upload_df.drop(
                    columns=['單位現價', '目前投資占比', '偏離度 (Diff)', '買賣建議'], 
                    errors='ignore'
                )
                final_upload_df = final_upload_df.loc[:, ~final_upload_df.columns.astype(str).str.contains('^Unnamed')]
                
                conn.update(worksheet="portfolio_config", data=final_upload_df)
                st.success("🎉 持股變更已寫入，且雲端公式已全自動補回再激活！")
                st.cache_data.clear()
                st.rerun()
                
            except Exception as ex:
                st.error(f"❌ 同步失敗。錯誤訊息: {ex}")