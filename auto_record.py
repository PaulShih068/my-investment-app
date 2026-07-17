import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import yfinance as yf
from datetime import datetime
import json
import os

# ==========================================
# 1. 讀取安全金鑰
# ==========================================
creds_json = os.environ.get("G_SECRETS_JSON")
spreadsheet_url = os.environ.get("SPREADSHEET_URL")

if not creds_json or not spreadsheet_url:
    print("❌ 錯誤：找不到雲端安全金鑰，請確認 GitHub Secrets 設定！")
    exit(1)

# ==========================================
# 2. 登入 Google Sheets
# ==========================================
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
gc = gspread.authorize(creds)

sh = gc.open_by_url(spreadsheet_url)
hist_ws = sh.worksheet("daily_asset_history")
port_ws = sh.worksheet("portfolio_config")

# ==========================================
# 3. 讀取持股設定並計算當前市值
# ==========================================
port_data = port_ws.get_all_records()
df_portfolio = pd.DataFrame(port_data)
df_portfolio = df_portfolio.dropna(subset=["標的名稱"])

total_cost = float(df_portfolio['投資成本'].sum())

# 抓取即時匯率 (USD/TWD)
try:
    rate_stock = yf.Ticker("USDTWD=X")
    rate_data = rate_stock.history(period='1d')
    usd_twd_rate = round(rate_data['Close'].iloc[-1], 4) if not rate_data.empty else 32.5
except Exception:
    usd_twd_rate = 32.5

prices = {}
for ticker in df_portfolio['Yahoo代號'].tolist():
    if not ticker:
        continue
    try:
        stock = yf.Ticker(ticker)
        todays_data = stock.history(period='1d')
        if not todays_data.empty:
            prices[ticker] = round(todays_data['Close'].iloc[-1], 2)
        else:
            prices[ticker] = 0.0
    except Exception:
        prices[ticker] = 0.0

# 計算總市值 (含匯率轉換)
df_portfolio['單位現價'] = df_portfolio['Yahoo代號'].map(prices)

def calculate_twd_market_value(row):
    ticker = str(row['Yahoo代號'])
    price = float(row['單位現價'])
    qty = float(row['持有數量'])
    if ticker.endswith('.TW') or ticker == '現金':
        return price * qty
    else:
        return price * qty * usd_twd_rate

df_portfolio['當前市值'] = df_portfolio.apply(calculate_twd_market_value, axis=1)
total_market_value = float(df_portfolio['當前市值'].sum())

# ==========================================
# 4. 寫入或更新今日紀錄 (4欄位自動化計算 + 🎯四捨五入整數化)
# ==========================================
hist_data = hist_ws.get_all_records()
df_history = pd.DataFrame(hist_data)

today_str = datetime.now().strftime("%Y-%m-%d")

# 排序並過濾，找出昨日之總資產金額
if not df_history.empty:
    df_history['日期'] = df_history['日期'].astype(str)
    df_history_temp = df_history.copy()
    df_history_temp['日期'] = pd.to_datetime(df_history_temp['日期'])
    df_history_temp = df_history_temp.sort_values(by="日期")
    df_history_temp['日期'] = df_history_temp['日期'].dt.strftime("%Y-%m-%d")
    
    df_yesterday = df_history_temp[df_history_temp['日期'] < today_str]
    if not df_yesterday.empty:
        last_amount = float(df_yesterday['總資產金額'].iloc[-1])
        daily_diff = total_market_value - last_amount
    else:
        daily_diff = 0.0
else:
    daily_diff = 0.0

# 🎯 優化：自動記帳寫入前全面四捨五入並強轉整數 (Integer)
total_market_value_rounded = int(round(total_market_value))
daily_diff_rounded = int(round(daily_diff))

# 自動算出當日報酬率
daily_roi = round((total_market_value - total_cost) / total_cost, 4) if total_cost > 0 else 0.0

# 寫入 Google Sheets
if not df_history.empty and today_str in df_history['日期'].values:
    # 找到那一行並更新 3 個欄位 (gspread 索引從 1 開始，且有標題列，故索引 + 2)
    row_idx = df_history[df_history['日期'] == today_str].index[0] + 2
    hist_ws.update_cell(row_idx, 2, total_market_value_rounded)
    hist_ws.update_cell(row_idx, 3, daily_diff_rounded)
    hist_ws.update_cell(row_idx, 4, daily_roi)
    print(f"🔄 [自動記帳] 已更新今日 ({today_str}) 4 欄位資料。市值: {total_market_value_rounded} | 增額: {daily_diff_rounded} | 報酬率: {daily_roi:.2%}")
else:
    # 新增一行
    hist_ws.append_row([today_str, total_market_value_rounded, daily_diff_rounded, daily_roi])
    print(f"🚀 [自動記帳] 已新增今日 ({today_str}) 4 欄位資料。市值: {total_market_value_rounded} | 增額: {daily_diff_rounded} | 報酬率: {daily_roi:.2%}")