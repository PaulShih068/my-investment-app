import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import yfinance as yf
from datetime import datetime
import os

# ==========================================
# 1. 系統初始化設定與頁面配置
# ==========================================
st.set_page_config(page_title="個人智慧投資紀錄簿", layout="wide", initial_sidebar_state="expanded")

ASSET_HISTORY_FILE = "daily_asset_history.csv"
PORTFOLIO_FILE = "portfolio_config.csv"

# 初始化預設資料
if not os.path.exists(ASSET_HISTORY_FILE):
    df_init = pd.DataFrame(columns=["日期", "總資產金額", "每日增額", "每日報酬率"])
    df_init.loc[0] = ["2026-07-11", 13088555.0, 449187.0, 0.4237]
    df_init.to_csv(ASSET_HISTORY_FILE, index=False, encoding='utf-8-sig')

if not os.path.exists(PORTFOLIO_FILE):
    df_port = pd.DataFrame([
        {"標的名稱": "00631L (正二)", "Yahoo代號": "00631L.TW", "核心權重": 0.60, "持有數量": 257400, "投資成本": 4063194},
        {"標的名稱": "00662", "Yahoo代號": "00662.TW", "核心權重": 0.10, "持有數量": 12000, "投資成本": 882166},
    ])
    df_port.to_csv(PORTFOLIO_FILE, index=False, encoding='utf-8-sig')

# ==========================================
# 2. 自動化功能：線上即時股價抓取
# ==========================================
@st.cache_data(ttl=3600)
def fetch_realtime_prices(tickers):
    prices = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            todays_data = stock.history(period='1d')
            if not todays_data.empty:
                prices[ticker] = round(todays_data['Close'].iloc[-1], 2)
            else:
                prices[ticker] = 0.0
        except Exception:
            prices[ticker] = 0.0
    return prices

# ==========================================
# 3. 側邊導覽列與【重要】雲端備份功能
# ==========================================
st.sidebar.title("🧭 投資導覽控制台")
menu = st.sidebar.radio("請選擇操作功能：", ["📊 投資總覽儀表板", "✍️ 每日資產動態輸入", "⚙️ 投資標的持股管理"])

st.sidebar.markdown("---")
st.sidebar.subheader("💾 雲端資料備份與還原")
st.sidebar.write("因免費雲端空間重啟時資料會重置，建議定期在此下載備份。")

# 讀取當前資料以供下載
df_history_download = pd.read_csv(ASSET_HISTORY_FILE)
df_portfolio_download = pd.read_csv(PORTFOLIO_FILE)

# 備份下載按鈕
csv_history = df_history_download.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
st.sidebar.download_button(
    label="📥 下載資產歷史備份 (CSV)",
    data=csv_history,
    file_name="daily_asset_history_backup.csv",
    mime="text/csv"
)

csv_portfolio = df_portfolio_download.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
st.sidebar.download_button(
    label="📥 下載持股設定備份 (CSV)",
    data=csv_portfolio,
    file_name="portfolio_config_backup.csv",
    mime="text/csv"
)

# 還原上傳欄位
st.sidebar.write("如有重置，請在此上傳備份還原：")
uploaded_history = st.sidebar.file_uploader("還原資產歷史：", type="csv", key="upload_hist")
if uploaded_history is not None:
    df_uploaded = pd.read_csv(uploaded_history)
    df_uploaded.to_csv(ASSET_HISTORY_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("✅ 資產歷史還原成功！請重新整理網頁。")

uploaded_portfolio = st.sidebar.file_uploader("還原持股設定：", type="csv", key="upload_port")
if uploaded_portfolio is not None:
    df_uploaded_port = pd.read_csv(uploaded_portfolio)
    df_uploaded_port.to_csv(PORTFOLIO_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("✅ 持股設定還原成功！請重新整理網頁。")

# ==========================================
# 功能一：📊 投資總覽儀表板
# ==========================================
if menu == "📊 投資總覽儀表板":
    st.title("📊 個人即時投資動態儀表板")
    
    df_history = pd.read_csv(ASSET_HISTORY_FILE)
    df_portfolio = pd.read_csv(PORTFOLIO_FILE)
    
    with st.spinner('正在獲取最新即時報價...'):
        current_prices = fetch_realtime_prices(df_portfolio['Yahoo代號'].tolist())
    
    df_portfolio['單位現價'] = df_portfolio['Yahoo代號'].map(current_prices)
    df_portfolio['當前市值'] = df_portfolio['單位現價'] * df_portfolio['持有數量']
    
    total_market_value = df_portfolio['當前市值'].sum()
    total_cost = df_portfolio['投資成本'].sum()
    total_profit = total_market_value - total_cost
    total_roi = (total_profit / total_cost) if total_cost > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("當前總市值 (TWD)", f"${total_market_value:,.2f}")
    col2.metric("投資總成本", f"${total_cost:,.2f}")
    col3.metric("累積投資獲利", f"${total_profit:,.2f}", delta=f"{total_roi*100:.2f}% 報酬率")
    
    mock_loan = 2650197
    maintenance_rate = (total_market_value / mock_loan) if mock_loan > 0 else 0
    col4.metric("質押維持率", f"{maintenance_rate*100:.2f}%", delta="✅ 水位強韌" if maintenance_rate > 1.6 else "⚠️ 需注意風險")
    
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
    
    st.dataframe(df_portfolio[['標的名稱', '核心權重', '單位現價', '持有數量', '當前市值', '目前投資占比', '偏離度 (Diff)', '買賣建議']].style.format({
        '核心權重': '{:.1%}', '單位現價': '${:,.2f}', '當前市值': '${:,.2f}', '目前投資占比': '{:.1%}', '偏離度 (Diff)': '{:+.1%}'
    }))
    
    st.markdown("---")
    
    st.subheader("📈 歷史總資產趨勢追蹤")
    if not df_history.empty:
        df_history = df_history.sort_values(by="日期")
        fig = px.line(df_history, x="日期", y="總資產金額", title="每日資產總餘額成長曲線", markers=True)
        st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 功能二：✍️ 每日資產動態輸入
# ==========================================
elif menu == "✍️ 每日資產動態輸入":
    st.title("✍️ 每日資產金額輕鬆記")
    df_history = pd.read_csv(ASSET_HISTORY_FILE)
    
    with st.form("daily_input_form", clear_on_submit=True):
        input_date = st.date_input("選擇紀錄日期：", datetime.now())
        input_amount = st.number_input("今日結算總資產金額 (TWD)：", min_value=0.0, step=1000.0, format="%.2f")
        submit_button = st.form_submit_button(label="🚀 提交今日紀錄並自動計算")
        
        if submit_button:
            if not df_history.empty:
                df_history = df_history.sort_values(by="日期")
                last_amount = df_history['總資產金額'].iloc[-1]
                daily_diff = input_amount - last_amount
            else:
                daily_diff = 0.0
                
            new_data = {
                "日期": str(input_date),
                "總資產金額": input_amount,
                "每日增額": daily_diff,
                "每日報酬率": 0.0
            }
            
            if str(input_date) in df_history['日期'].values:
                df_history.loc[df_history['日期'] == str(input_date), ["總資產金額", "每日增額"]] = [input_amount, daily_diff]
            else:
                df_history = pd.concat([df_history, pd.DataFrame([new_data])], ignore_index=True)
                
            df_history.to_csv(ASSET_HISTORY_FILE, index=False, encoding='utf-8-sig')
            st.success(f"🎉 成功紀錄！ 日期: {input_date} | 總資產: ${input_amount:,.2f}")
            
    st.subheader("📋 最近輸入的資產紀錄歷史")
    st.dataframe(df_history.tail(5).sort_values(by="日期", ascending=False))

# ==========================================
# 功能三：⚙️ 投資標的持股管理
# ==========================================
elif menu == "⚙️ 投資標的持股管理":
    st.title("⚙️ 投資標的與持股數量管理")
    df_portfolio = pd.read_csv(PORTFOLIO_FILE)
    
    st.subheader("✏️ 線上直覺式編輯持股資訊")
    edited_df = st.data_editor(df_portfolio, num_rows="dynamic")
    
    if st.button("💾 儲存修改內容"):
        edited_df.to_csv(PORTFOLIO_FILE, index=False, encoding='utf-8-sig')
        st.success("💾 修改已成功同步！")