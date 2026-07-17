import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 1. 系統設定與網頁配置
st.set_page_config(page_title="個人智慧投資紀錄簿", layout="wide", initial_sidebar_state="expanded")

# 建立 Google Sheets 連結物件
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. 線上即時股價抓取
@st.cache_data(ttl=3600)
def fetch_realtime_prices(tickers):
    prices = {}
    for ticker in tickers:
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
    return prices

# 3. 側邊導覽列
st.sidebar.title("🧭 投資導覽控制台")
menu = st.sidebar.radio("請選擇操作功能：", ["📊 投資總覽儀表板", "✍️ 每日資產動態輸入", "⚙️ 投資標的持股管理"])

# 功能一：📊 投資總覽儀表板
if menu == "📊 投資總覽儀表板":
    st.title("📊 個人即時投資動態儀表板 (Google Sheets 同步)")
    
    try:
        df_history = conn.read(worksheet="daily_asset_history", ttl=0)
        df_portfolio = conn.read(worksheet="portfolio_config", ttl=0)
    except Exception as e:
        st.error(f"❌ 無法讀取 Google Sheets！請確認 secrets 設定！ 錯誤訊息: {e}")
        st.stop()
        
    df_history = df_history.dropna(subset=["日期"])
    df_portfolio = df_portfolio.dropna(subset=["標的名稱"])
    
    with st.spinner('正在獲取最新即時報價...'):
        current_prices = fetch_realtime_prices(df_portfolio['Yahoo代號'].tolist())
    
    df_portfolio['單位現價'] = df_portfolio['Yahoo代號'].map(current_prices)
    df_portfolio['當前市值'] = df_portfolio['單位現價'] * df_portfolio['持有數量']
    
    total_market_value = df_portfolio['當前市值'].sum()
    total_cost = df_portfolio['投資成本'].sum()
    total_profit = total_market_value - total_cost
    total_roi = (total_profit / total_cost) if total_cost > 0 else 0

    # ⚡️ 手動立即更新按鈕
    st.markdown("### ⚡️ 快速同步控制區")
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        sync_clicked = st.button("🔄 立即同步最新資產至 Google 雲端", use_container_width=True)
    with col_info:
        st.info("💡 雖然系統會定時自動抓取，但你可以隨時點擊按鈕，即時更新今日最新的資產紀錄！")
        
    if sync_clicked:
        today_str = datetime.now().strftime("%Y-%m-%d")
        df_history['日期'] = df_history['日期'].astype(str)
        
        if not df_history.empty:
            last_amount = float(df_history['總資產金額'].iloc[-1])
            daily_diff = total_market_value - last_amount
        else:
            daily_diff = 0.0
            
        new_data = {
            "日期": today_str,
            "總資產金額": float(total_market_value),
            "每日增額": float(daily_diff),
            "每日報酬率": 0.0
        }
        
        if today_str in df_history['日期'].values:
            df_history.loc[df_history['日期'] == today_str, ["總資產金額", "每日增額"]] = [float(total_market_value), float(daily_diff)]
        else:
            df_history = pd.concat([df_history, pd.DataFrame([new_data])], ignore_index=True)
            
        with st.spinner('正在寫入 Google Sheets...'):
            conn.update(worksheet="daily_asset_history", data=df_history)
        st.success(f"🎉 成功同步！今日 ({today_str}) 資產已更新。請重新整理網頁！")
                
    st.markdown("---")
    
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
    
    # 歷史總資產趨勢追蹤 (時間篩選優化)
    st.subheader("📈 歷史總資產趨勢追蹤")
    if not df_history.empty:
        df_history['日期'] = pd.to_datetime(df_history['日期'])
        df_history = df_history.sort_values(by="日期")
        
        time_option = st.radio(
            "選擇顯示的時間區間：",
            ["近 7 天", "近 30 天", "近 180 天", "今年以來 (YTD)", "全部顯示", "自訂日期範圍"],
            horizontal=True
        )
        
        today = datetime.now()
        df_filtered = df_history.copy()
        
        if time_option == "近 7 天":
            start_date = today - timedelta(days=7)
            df_filtered = df_history[df_history['日期'] >= pd.to_datetime(start_date)]
        elif time_option == "近 30 天":
            start_date = today - timedelta(days=30)
            df_filtered = df_history[df_history['日期'] >= pd.to_datetime(start_date)]
        elif time_option == "近 180 天":
            start_date = today - timedelta(days=180)
            df_filtered = df_history[df_history['日期'] >= pd.to_datetime(start_date)]
        elif time_option == "今年以來 (YTD)":
            start_date = datetime(today.year, 1, 1)
            df_filtered = df_history[df_history['日期'] >= pd.to_datetime(start_date)]
        elif time_option == "自訂日期範圍":
            col_date1, col_date2 = st.columns(2)
            with col_date1:
                start_date_input = st.date_input("開始日期：", today - timedelta(days=30))
            with col_date2:
                end_date_input = st.date_input("結束日期：", today)
            df_filtered = df_history[(df_history['日期'] >= pd.to_datetime(start_date_input)) & (df_history['日期'] <= pd.to_datetime(end_date_input))]
        
        if not df_filtered.empty:
            fig = px.line(df_filtered, x="日期", y="總資產金額", title=f"資產總額成長曲線 ({time_option})", markers=True)
            st.plotly_chart(fig, use_container_width=True)

# 功能二：✍️ 每日資產動態輸入
elif menu == "✍️ 每日資產動態輸入":
    st.title("✍️ 每日資產金額輕鬆記")
    try:
        df_history = conn.read(worksheet="daily_asset_history", ttl=0)
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        st.stop()
        
    df_history = df_history.dropna(subset=["日期"])
    
    with st.form("daily_input_form", clear_on_submit=True):
        input_date = st.date_input("選擇紀錄日期：", datetime.now())
        input_amount = st.number_input("今日結算總資產金額 (TWD)：", min_value=0.0, step=1000.0, format="%.2f")
        submit_button = st.form_submit_button(label="🚀 提交並儲存至 Google Sheets")
        
        if submit_button:
            date_str = str(input_date)
            df_history['日期'] = df_history['日期'].astype(str)
            
            if not df_history.empty:
                df_history_temp = df_history.copy()
                df_history_temp['日期'] = pd.to_datetime(df_history_temp['日期'])
                df_history_temp = df_history_temp.sort_values(by="日期")
                last_amount = float(df_history_temp['總資產金額'].iloc[-1])
                daily_diff = input_amount - last_amount
            else:
                daily_diff = 0.0
                
            new_data = {
                "日期": date_str,
                "總資產金額": float(input_amount),
                "每日增額": float(daily_diff),
                "每日報酬率": 0.0
            }
            
            if date_str in df_history['日期'].values:
                df_history.loc[df_history['日期'] == date_str, ["總資產金額", "每日增額"]] = [float(input_amount), float(daily_diff)]
            else:
                df_history = pd.concat([df_history, pd.DataFrame([new_data])], ignore_index=True)
            
            with st.spinner('正在寫入...'):
                conn.update(worksheet="daily_asset_history", data=df_history)
            st.success("🎉 成功同步至雲端試算表！")
            
    st.subheader("📋 最近輸入的資產紀錄歷史")
    if not df_history.empty:
        df_history['日期'] = pd.to_datetime(df_history['日期'])
        st.dataframe(df_history.tail(5).sort_values(by="日期", ascending=False))

# 功能三：⚙️ 投資標的持股管理
elif menu == "⚙️ 投資標的持股管理":
    st.title("⚙️ 投資標的與持股數量管理")
    try:
        df_portfolio = conn.read(worksheet="portfolio_config", ttl=0)
    except Exception as e:
        st.error(f"❌ 讀取失敗: {e}")
        st.stop()
        
    df_portfolio = df_portfolio.dropna(subset=["標的名稱"])
    st.subheader("✏️ 線上編輯持股資訊")
    edited_df = st.data_editor(df_portfolio, num_rows="dynamic")
    
    if st.button("💾 儲存並同步至 Google Sheets"):
        with st.spinner('正在儲存...'):
            conn.update(worksheet="portfolio_config", data=edited_df)
        st.success("💾 修改已同步！")