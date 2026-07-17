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
# 3. 讀取持股並獲取最新股價與即時匯率
# ==========================================
port_data = port_ws.get_all_records()
df_portfolio = pd.DataFrame(port_data)
df_portfolio = df_portfolio.dropna(subset=["標的名稱"])

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

# 計算總市值 (含匯率轉換機制)
df_portfolio['單位現價'] = df_portfolio['Yahoo代號'].map(prices)

def calculate_twd_market_value(row):
    ticker = str(row['Yahoo代號'])
    price = float(row['單位現價'])
    qty = float(row['持有數量'])
    
    # 匯率轉換判定邏輯
    if ticker.endswith('.TW') or ticker == '現金':
        return price * qty
    else:
        return price * qty * usd_twd_rate

df_portfolio['當前市值'] = df_portfolio.apply(calculate_twd_market_value, axis=1)
total_market_value = float(df_portfolio['當前市值'].sum())

# ==========================================
# 4. 寫入或更新今日紀錄
# ==========================================
hist_data = hist_ws.get_all_records()
df_history = pd.DataFrame(hist_data)

today_str = datetime.now().strftime("%Y-%m-%d")

if not df_history.empty:
    df_history['日期'] = df_history['日期'].astype(str)
    last_amount = float(df_history['總資產金額'].iloc[-1])
    daily_diff = total_market_value - last_amount
else:
    daily_diff = 0.0

if not df_history.empty and today_str in df_history['日期'].values:
    row_idx = df_history[df_history['日期'] == today_str].index[0] + 2
    hist_ws.update_cell(row_idx, 2, total_market_value)
    hist_ws.update_cell(row_idx, 3, daily_diff)
    print(f"🔄 [自動記帳] 已更新今日 ({today_str}) 紀錄：${total_market_value:,.2f} | 匯率基準: ${usd_twd_rate}")
else:
    hist_ws.append_row([today_str, total_market_value, daily_diff, 0.0])
    print(f"🚀 [自動記帳] 已新增今日 ({today_str}) 紀錄：${total_market_value:,.2f} | 匯率基準: ${usd_twd_rate}")