import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import yfinance as yf
from datetime import datetime
import json
import os

# 1. 讀取安全金鑰
creds_json = os.environ.get("G_SECRETS_JSON")
spreadsheet_url = os.environ.get("SPREADSHEET_URL")

if not creds_json or not spreadsheet_url:
    print("❌ 錯誤：找不到雲端安全金鑰，請確認 GitHub Secrets 設定！")
    exit(1)

# 2. 登入 Google Sheets
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
gc = gspread.authorize(creds)

sh = gc.open_by_url(spreadsheet_url)
hist_ws = sh.worksheet("daily_asset_history")
port_ws = sh.worksheet("portfolio_config")

# 3. 讀取持股設定並抓取股價
port_data = port_ws.get_all_records()
df_portfolio = pd.DataFrame(port_data)
df_portfolio = df_portfolio.dropna(subset=["標的名稱"])

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

# 計算總市值
df_portfolio['單位現價'] = df_portfolio['Yahoo代號'].map(prices)
df_portfolio['當前市值'] = df_portfolio['單位現價'] * df_portfolio['持有數量']
total_market_value = float(df_portfolio['當前市值'].sum())

# 4. 寫入或更新今日紀錄
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
    print(f"🔄 已更新今日 ({today_str}) 紀錄：${total_market_value:,.2f}")
else:
    hist_ws.append_row([today_str, total_market_value, daily_diff, 0.0])
    print(f"🚀 已成功新增今日 ({today_str}) 紀錄：${total_market_value:,.2f}")