# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, date, time
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
# 🛡️ 流量防護盾：實體化全域快取函數
# ==========================================
@st.cache_data(ttl=120)  
def cached_read_sheets(worksheet_name):
    try:
        return conn.read(worksheet=worksheet_name, ttl=120)
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 🏦 自動化：動態貸款餘額扣除計算函式
# ==========================================
def calculate_remaining_loans(current_date):
    l1_base = 1039721
    l1_day = 20
    l1_pay = 12797
    l1_base_date = date(2024, 4, 20)
    
    l2_base = 2016662
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
            
    l1_rem = max(0, l1_base - (l1_payments * l1_pay))
    l2_rem = max(0, l2_base - (l2_payments * l2_pay))
    
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
                try:
                    df_creds = cached_read_sheets("user_credentials")
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
                        st.error("❌ 無法讀取認證資料表。")
                except Exception as e:
                    st.error(f"❌ 驗證失敗。 錯誤: {e}")
    st.stop()

# ==========================================
# 2. 線上即時股價抓取
# ==========================================
def fetch_realtime_prices(tickers):
    prices = {}
    cash_keywords = ['現金', '台幣現金', '美金現金', 'TAIBI', 'CASH']
    valid_tickers = list(set([str(t).strip() for t in tickers if t and str(t).strip() not in cash_keywords and str(t).strip().lower() != 'nan']))
    
    fallback_prices = {
        "00631L.TW": 32.17,
        "00685L.TW": 10.54,
        "00662.TW": 118.85,
        "QQQM": 290.68,
        "00865B.TW": 49.25
    }
    
    if not valid_tickers:
        return prices
        
    try:
        import yfinance as yf
        data = yf.download(valid_tickers, period='5d', group_by='ticker', progress=False)
        if not data.empty:
            has_zero = False
            for ticker in valid_tickers:
                try:
                    clean_yf_ticker = ticker.split(':')[-1] if ':' in ticker else ticker
                    df_ticker = data if len(valid_tickers) == 1 else data[clean_yf_ticker]
                    if 'Close' in df_ticker.columns:
                        closes = df_ticker['Close'].dropna()
                        if not closes.empty and float(closes.iloc[-1]) > 0:
                            prices[ticker] = round(float(closes.iloc[-1]), 2)
                        else:
                            prices[ticker] = fallback_prices.get(ticker, 0.0)
                            has_zero = True
                    else:
                        prices[ticker] = fallback_prices.get(ticker, 0.0)
                        has_zero = True
                except:
                    prices[ticker] = fallback_prices.get(ticker, 0.0)
                    has_zero = True
            st.session_state["is_api_blocked"] = has_zero
        else:
            st.session_state["is_api_blocked"] = True
            for ticker in valid_tickers:
                prices[ticker] = fallback_prices.get(ticker, 0.0)
    except Exception:
        st.session_state["is_api_blocked"] = True
        for ticker in valid_tickers:
            prices[ticker] = fallback_prices.get(ticker, 0.0)
            
    for ticker in valid_tickers:
        if prices.get(ticker, 0.0) <= 0:
            prices[ticker] = fallback_prices.get(ticker, 10.0)
            
    return prices

@st.cache_data(ttl=60)
def get_usd_twd_rate():
    try:
        import yfinance as yf
        data = yf.download("USDTWD=X", period='5d', progress=False)
        if not data.empty and 'Close' in data.columns:
            closes = data['Close'].dropna()
            if not closes.empty Sea float(closes.iloc[-1]) > 0:
                return round(float(closes.iloc[-1]), 4)
        return 32.5
    except Exception:
        return 32.5

# ==========================================
# 🔄 系統核心引擎：完美 Upsert 日期判斷與公式保護
# ==========================================
def execute_system_wide_sync(custom_connection=None):
    try:
        active_conn = custom_connection if custom_connection else conn
        
        # 1. 讀取最新雲端配置 (強制作廢快取讀取即時狀態)
        df_history_sync = active_conn.read(worksheet="daily_asset_history", ttl=0)
        df_portfolio_sync = active_conn.read(worksheet="portfolio_config", ttl=0)
        
        df_history_sync = df_history_sync.dropna(subset=["日期"])
        df_portfolio_sync = df_portfolio_sync.dropna(subset=["標的名稱"])
        
        # 🎯 核心修復防線：將歷史資料庫中的日期欄位全數轉換成標準字串 (YYYY-MM-DD)
        df_history_sync['日期'] = pd.to_datetime(df_history_sync['日期']).dt.strftime("%Y-%m-%d")
        
        # 2. 獲取報價與匯率並進行清算
        prices_map = fetch_realtime_prices(df_portfolio_sync['Yahoo代號'].tolist())
        usd_rate = get_usd_twd_rate()
        
        target_price_col = '個股現價'
        if target_price_col in df_portfolio_sync.columns:
            df_portfolio_sync['單位現價'] = pd.to_numeric(df_portfolio_sync[target_price_col], errors='coerce').fillna(0.0)
        else:
            df_portfolio_sync['單位現價'] = df_portfolio_sync['Yahoo代號'].map(prices_map).fillna(0.0)
            
        df_portfolio_sync['Yahoo代號_clean'] = df_portfolio_sync['Yahoo代號'].fillna('').astype(str).str.strip()
        df_portfolio_sync['標的名稱_clean'] = df_portfolio_sync['標的名稱'].fillna('').astype(str).str.strip()
        
        for idx, row in df_portfolio_sync.iterrows():
            ticker = row['Yahoo代號_clean']
            name = row['標的名稱_clean']
            if any(k in ticker for k in ['台幣', '美金', '現金']) or any(k in name for k in ['台幣', '美金', '現金']):
                sheet_cash_val = 0.0
                if target_price_col in df_portfolio_sync.columns:
                    sheet_cash_val = pd.to_numeric(row[target_price_col], errors='coerce')
                df_portfolio_sync.loc[idx, '單位現價'] = sheet_cash_val if (not np.isnan(sheet_cash_val) and sheet_cash_val > 0) else 1.0

        def calc_mv(row):
            t = str(row['Yahoo代號_clean']).strip()
            n = str(row['標的名稱_clean']).strip()
            p = float(row['單位現價'])
            q = float(row['持有數量'])
            if '台幣' in t or '現金' in t or '台幣' in n or '現金' in n or t.endswith('.TW') or t.endswith('.tw') or t == '':
                return p * q
            return p * q * usd_rate

        df_portfolio_sync['當前市值'] = df_portfolio_sync.apply(calc_mv, axis=1)
        total_mv_calculated = df_portfolio_sync['當前市值'].sum()
        total_cost_calculated = df_portfolio_sync['投資成本'].sum()
        
        # 3. 根據當天日期判定執行「產生新資料列」或「精準就地更新」
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 計算相對於昨天的增額
        df_history_sorted = df_history_sync.copy()
        df_history_sorted['日期'] = pd.to_datetime(df_history_sorted['日期'])
        df_history_sorted = df_history_sorted.sort_values(by="日期")
        df_history_sorted['日期'] = df_history_sorted['日期'].dt.strftime("%Y-%m-%d")
        df_yesterday = df_history_sorted[df_history_sorted['日期'] < today_str]
        
        daily_diff = total_mv_calculated - float(df_yesterday['總資產金額'].iloc[-1]) if not df_yesterday.empty else 0.0
        daily_roi = round((total_mv_calculated - total_cost_calculated) / total_cost_calculated, 4) if total_cost_calculated > 0 else 0.0
        
        # 🎯 核心日期分流邏輯
        if today_str in df_history_sync['日期'].values:
            # ✅ 當天紀錄已存在 ➜ 精準就地更新，絕對不增加新行或覆蓋別人
            df_history_sync.loc[df_history_sync['日期'] == today_str, ["總資產金額", "每日增額", "每日報酬率"]] = [
                int(round(total_mv_calculated)), int(round(daily_diff)), float(daily_roi)
            ]
        else:
            # ✅ 當天紀錄不存在 ➜ 根據當天日期產生一筆全新的歷史數據追加於末端
            new_row_data = {
                "日期": today_str,
                "總資產金額": int(round(total_mv_calculated)),
                "每日增額": int(round(daily_diff)),
                "每日報酬率": float(daily_roi)
            }
            df_history_sync = pd.concat([df_history_sync, pd.DataFrame([new_row_data])], ignore_index=True)
            
        # 4. 多維度公式智慧還原再注入防禦網
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
            columns=['單位現價', '當前市值', '目前投資占比', '偏離度 (Diff)', '買賣建議', 'Yahoo代號_clean', '標的名稱_clean'], 
            errors='ignore'
        )
        
        # 5. 安全回寫雲端雙工作表
        active_conn.update(worksheet="daily_asset_history", data=df_history_sync)
        active_conn.update(worksheet="portfolio_config", data=final_upload_df)
        return True
    except Exception:
        return False

# ==========================================
# 🔄 執行緒安全之背景排程守護引擎
# ==========================================
def background_scheduler(static_times):
    while True:
        try:
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            current_date_str = now.strftime("%Y-%m-%d")
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

# 激活背景守護執行緒
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
        
    df_history = df_history.dropna(subset=["日期"])
    df_portfolio = df_portfolio.dropna(subset=["標的名稱"])
    
    with st.spinner('正在獲取最新即時報價與匯率...'):
        current_prices = fetch_realtime_prices(df_portfolio['Yahoo代號'].tolist())
        usd_twd_rate = get_usd_twd_rate()
    
    st.sidebar.metric("💵 當前美金匯率 (USD/TWD)", f"${usd_twd_rate:.4f}")
    st.sidebar.success(f"🤖 雲端持久排程監聽中！\n每日觸發時間點：`{', '.join(scheduled_times_list)}`")
    
    today_date = datetime.now().date()
    l1_remain, l2_remain, l1_pay_count, l2_pay_count = calculate_remaining_loans(today_date)
    total_loan_balance = l1_remain + l2_remain
    
    target_price_column = '個股現價' 
    if st.session_state["is_api_blocked"] and target_price_column in df_portfolio.columns:
        df_portfolio['單位現價'] = pd.to_numeric(df_portfolio[target_price_column], errors='coerce').fillna(0.0)
    else:
        df_portfolio['單位現價'] = df_portfolio['Yahoo代號'].map(current_prices).fillna(0.0)
        
    df_portfolio['Yahoo代號_clean'] = df_portfolio['Yahoo代號'].fillna('').astype(str).str.strip()
    df_portfolio['標的名稱_clean'] = df_portfolio['標的名稱'].fillna('').astype(str).str.strip()
    
    for idx, row in df_portfolio.iterrows():
        ticker = row['Yahoo代號_clean']
        name = row['標的名稱_clean']
        if any(k in ticker for k in ['台幣', '美金', '現金']) or any(k in name for k in ['台幣', '美金', '現金']):
            sheet_cash_val = 0.0
            if target_price_column in df_portfolio.columns:
                sheet_cash_val = pd.to_numeric(row[target_price_column], errors='coerce')
            df_portfolio.loc[idx, '單位現價'] = sheet_cash_val if (not np.isnan(sheet_cash_val) and sheet_cash_val > 0) else 1.0
    
    def calculate_twd_market_value(row):
        ticker = str(row['Yahoo代號_clean']).strip()
        name = str(row['標的名稱_clean']).strip()
        price = float(row['單位現價'])
        qty = float(row['持有數量'])
        if '台幣' in ticker or '現金' in ticker or '台幣' in name or '現金' in name or ticker.endswith('.TW') or ticker.endswith('.tw') or ticker == '':
            return price * qty
        return price * qty * usd_twd_rate

    df_portfolio['當前市值'] = df_portfolio.apply(calculate_twd_market_value, axis=1)
    total_market_value = df_portfolio['當前市值'].sum()
    total_cost = df_portfolio['投資成本'].sum()
    
    if not df_history.empty:
        df_history_sorted = df_history.copy()
        df_history_sorted['日期'] = pd.to_datetime(df_history_sorted['日期'])
        df_history_sorted = df_history_sorted.sort_values(by="日期")
        total_market_value = float(df_history_sorted['總資產金額'].iloc[-1])
        total_roi = float(df_history_sorted['每日報酬率'].iloc[-1])
        total_profit = total_market_value - total_cost
    else:
        total_profit = total_market_value - total_cost
        total_roi = (total_profit / total_cost) if total_cost > 0 else 0

    st.markdown("### ⚡️ 快速同步控制區")
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        sync_clicked = st.button("🔄 立即同步最新資產至 Google 雲端", use_container_width=True)
        
    with col_info:
        st.info("💡 雲端優化限流版：排程在無人造訪時採用快取機制保護，杜絕觸發 Google 429 錯誤限流配額。")
        
    if sync_clicked:
        with st.spinner('正在執行全自動資產清算與 Upsert 日期公式防護同步...'):
            res = execute_system_wide_sync()
            if res:
                st.success(f"🎉 成功同步！請重新整理網頁！")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ 同步失敗，請稍後再試。")
                
    st.markdown("---")
    
    # KPI 指標卡片
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("當前總市值 (TWD)", f"${total_market_value:,.2f}")
    col2.metric("投資總成本", f"${total_cost:,.2f}")
    col3.metric("累積投資獲利", f"${total_profit:,.2f}", delta=f"{total_roi*100:.2f}% 報酬率")
    
    maintenance_rate = (total_market_value / total_loan_balance) if total_loan_balance > 0 else 0
    col4.metric("質押維持率", f"{maintenance_rate*100:.2f}%", delta="✅ 水位強韌" if maintenance_rate > 1.6 else "⚠️ 需注意風險")

    st.markdown("---")
    st.subheader("🎯 核心資產再平衡與偏離度檢查")
    df_portfolio['目前投資占比'] = df_portfolio['當前市值'] / total_market_value if total_market_value > 0 else 0
    df_portfolio['偏離度 (Diff)'] = df_portfolio['currently_market_pct'] if 'currently_market_pct' in df_portfolio.columns else (df_portfolio['currently_market_value'] / total_market_value - df_portfolio['核心權重'] if 'currently_market_value' in df_portfolio.columns else df_portfolio['目前投資占比'] - df_portfolio['核心權重'])
    
    if '偏離度 (Diff)' not in df_portfolio.columns or df_portfolio['偏離度 (Diff)'].isna().all():
        df_portfolio['偏離度 (Diff)'] = df_portfolio['currently_market_value'] / total_market_value - df_portfolio['核心權重'] if 'currently_market_value' in df_portfolio.columns else df_portfolio['目前投資占比'] - df_portfolio['核心權重']
        
    if '偏離度 (Diff)' not in df_portfolio.columns or df_portfolio['偏離度 (Diff)'].isna().all():
        df_portfolio['偏離度 (Diff)'] = df_portfolio['目前投資占比'] - df_portfolio['核心權重']

    def generate_advice(row):
        if row['偏離度 (Diff)'] > 0.05:
            return f"⚠️ 建議減碼 {row['標的名稱']}"
        elif row['偏離度 (Diff)'] < -0.05:
            return f"🛒 建議加碼 {row['標的名稱']}"
        else:
            return "✅ 權重正常"
            
    df_portfolio['買賣建議'] = df_portfolio.apply(generate_advice, axis=1)
    st.dataframe(df_portfolio[['標的名稱', '核心權重', '單位現價', '持有數量', '當前市值', '目前投資占比', '偏離度 (Diff)', '買賣建議']].style.format({
        '核心權重': '{:.1%}', '單位現價': '${:,.2f}', '持有數量': '{:.0f}', '當前市值': '${:,.2f}', '目前投資占比': '{:.1%}', '偏離度 (Diff)': '{:+.1%}'
    }))

# ==========================================
# 功能二：✍️ 每日資產動態輸入
# ==========================================
elif menu == "✍️ 每日資產動態輸入":
    st.title("✍️ 每日資產金額輕鬆記")
    df_history = cached_read_sheets("daily_asset_history")
    df_portfolio = cached_read_sheets("portfolio_config")
    
    if not df_history.empty and not df_portfolio.empty:
        df_history = df_history.dropna(subset=["日期"])
        df_portfolio = df_portfolio.dropna(subset=["標的名稱"])
        total_cost = df_portfolio['投資成本'].sum()
        
        with st.form("daily_input_form", clear_on_submit=True):
            input_date = st.date_input("選擇紀錄日期：", datetime.now())
            input_amount = st.number_input("今日結算總資產金額 (TWD)：", min_value=0.0, step=1000.0, format="%.2f")
            submit_button = st.form_submit_button(label="🚀 提交並儲存至 Google Sheets")
            
            if submit_button:
                date_str = str(input_date)
                df_history['日期'] = df_history['日期'].astype(str)
                
                df_history_temp = df_history.copy()
                df_history_temp['日期'] = pd.to_datetime(df_history_temp['日期'])
                df_history_temp = df_history_temp.sort_values(by="日期")
                df_history_temp['日期'] = df_history_temp['日期'].dt.strftime("%Y-%m-%d")
                
                df_yesterday = df_history_temp[df_history_temp['日期'] < date_str]
                if not df_yesterday.empty:
                    last_amount = float(df_yesterday['總資產金額'].iloc[-1])
                    daily_diff = input_amount - last_amount
                else:
                    daily_diff = 0.0
                    
                daily_roi = round((input_amount - total_cost) / total_cost, 4) if total_cost > 0 else 0.0
                input_amount_rounded = int(round(input_amount))
                daily_diff_rounded = int(round(daily_diff))
                    
                new_data = {
                    "日期": date_str,
                    "總資產金額": input_amount_rounded,
                    "每日增額": daily_diff_rounded,
                    "每日報酬率": float(daily_roi)
                }
                
                if date_str in df_history['日期'].values:
                    df_history.loc[df_history['日期'] == date_str, ["總資產金額", "每日增額", "每日報酬率"]] = [
                        input_amount_rounded, daily_diff_rounded, float(daily_roi)
                    ]
                else:
                    df_history = pd.concat([df_history, pd.DataFrame([new_data])], ignore_index=True)
                
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
        df_display['日期'] = pd.to_datetime(df_display['日期'])
        df_display = df_display.sort_values(by="日期", ascending=False)
        today = datetime.now()
        
        if search_option == "近 7 天":
            start_date = today - timedelta(days=7)
            df_display = df_display[df_display['日期'] >= pd.to_datetime(start_date)]
        elif search_option == "近 30 天":
            start_date = today - timedelta(days=30)
            df_display = df_display[df_display['日期'] >= pd.to_datetime(start_date)]
        elif search_option == "近 180 天":
            start_date = today - timedelta(days=180)
            df_display = df_display[df_display['日期'] >= pd.to_datetime(start_date)]
        elif search_option == "今年以來 (YTD)":
            start_date = datetime(today.year, 1, 1)
            df_display = df_display[df_display['日期'] >= pd.to_datetime(start_date)]
            
        df_display['日期'] = df_display['日期'].dt.strftime("%Y-%m-%d")
        df_display['總資產金額'] = pd.to_numeric(df_display['總資產金額'], errors='coerce').fillna(0).round().astype(int)
        df_display['每日增額'] = pd.to_numeric(df_display['每日增額'], errors='coerce').fillna(0).round().astype(int)
        
        rows_per_page = 10
        total_rows = len(df_display)
        
        if total_rows > 0:
            total_pages = int(np.ceil(total_rows / rows_per_page))
            current_page = st.number_input(f"頁碼 (共 {total_pages} 頁)", min_value=1, max_value=total_pages, value=1, step=1)
            start_idx = (current_page - 1) * rows_per_page
            end_idx = start_idx + rows_per_page
            st.dataframe(df_display.iloc[start_idx:end_idx], use_container_width=True)

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
        
    df_portfolio_raw = df_portfolio_raw.dropna(subset=["標的名稱"])
    
    st.subheader("✏️ 線上編輯持股資訊")
    st.info("💡 智慧公式保護網已部署：您可以自由修改標的、權重、數量與成本。當您點擊儲存時，系統將全自動利用『公式還原引擎』將個股現價重新編譯為 GOOGLEFINANCE 公式字串寫回雲端，絕對不破壞試算表的動態股價更新！")
    
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
                    columns=['單位現價', '當前市值', '目前投資占比', '偏離度 (Diff)', '買賣建議', 'Yahoo代號_clean', '標的名稱_clean'], 
                    errors='ignore'
                )
                
                conn.update(worksheet="portfolio_config", data=final_upload_df)
                st.success("🎉 公式防禦任務大成功！持股變更已寫入，且雲端公式已全自動補回再激活！")
                st.cache_data.clear()
                st.rerun()
                
            except Exception as ex:
                st.error(f"❌ 同步失敗。錯誤訊息: {ex}")