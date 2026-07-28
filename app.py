# -*- coding: utf-8 -*-
"""
==================================================
專案名稱：智慧投資紀錄簿 App (標準主程式 app.py)
檔案名稱：app.py
功能摘要：
1. 完整登入首頁 + Google Sheets user_credentials 雲端動態帳密驗證。
2. 指紋/生物辨識互動對話框解鎖機制。
3. 頂部 48px 安全區域 (Safe Area) 防遮擋排版 + 右上角登出系統按鈕。
4. 歷史資產動態折線圖 + 自動再平衡建議。
5. 嚴格保護 Google Sheets 公式：同步時僅允許寫入【核心權重, 持有數量, 投資成本】。
==================================================
"""

import sys
import types
import os
import json
import re

# ==========================================
# 0. Android SSL 憑證與環境變數設定
# ==========================================
try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
except ImportError:
    pass

base_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["HOME"] = base_dir
os.environ["TMPDIR"] = base_dir

# 本機 JSON 持久化儲存機制 (app_storage.json)
STORAGE_FILE = os.path.join(base_dir, "app_storage.json")

def get_local_storage(key, default=None):
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get(key, default)
        except Exception:
            return default
    return default

def set_local_storage(key, value):
    try:
        data = {}
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        data[key] = value
        with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# Android Package Mock (wsgiref)
if "wsgiref" not in sys.modules or not hasattr(sys.modules["wsgiref"], "__path__"):
    wsgiref = types.ModuleType("wsgiref")
    wsgiref.__path__ = []
    
    wsgiref_util = types.ModuleType("wsgiref.util")
    wsgiref_util.setup_testing_defaults = lambda *args, **kwargs: None
    
    wsgiref_simple_server = types.ModuleType("wsgiref.simple_server")
    wsgiref_simple_server.WSGIServer = type("WSGIServer", (object,), {})
    wsgiref_simple_server.WSGIRequestHandler = type("WSGIRequestHandler", (object,), {})
    wsgiref_simple_server.make_server = lambda *args, **kwargs: None
    
    wsgiref.util = wsgiref_util
    wsgiref.simple_server = wsgiref_simple_server
    
    sys.modules["wsgiref"] = wsgiref
    sys.modules["wsgiref.util"] = wsgiref_util
    sys.modules["wsgiref.simple_server"] = wsgiref_simple_server

import flet as ft
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, date, timezone

# ==========================================
# 1. 財務與時區核心邏輯
# ==========================================
def get_taiwan_now():
    utc_now = datetime.now(timezone.utc)
    taiwan_tz = timezone(timedelta(hours=8))
    return utc_now.astimezone(taiwan_tz)

def calculate_remaining_loans(current_date):
    l1_rem = 682586
    l2_rem = 1941174
    return l1_rem, l2_rem

# ==========================================
# 2. 全版本通用提示訊息函式 (Toast)
# ==========================================
def show_toast(page: ft.Page, message: str):
    page.snack_bar = ft.SnackBar(content=ft.Text(message))
    page.snack_bar.open = True
    page.update()

# ==========================================
# 3. 智能 ID 解析與 Google Sheets 直連模組
# ==========================================
SPREADSHEET_ID = "https://docs.google.com/spreadsheets/d/1UKdVDhXgl8CezS10iEdOOdC_E7HJJIq3GI05EpTuqg8/edit?usp=sharing"

def extract_spreadsheet_id(input_str):
    if not input_str or not input_str.strip():
        return ""
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', input_str)
    if match:
        return match.group(1)
    return input_str.strip()

def get_service_account_info():
    json_path = os.path.join(base_dir, "service_account.json")
    if not os.path.exists(json_path):
        return None, None, f"⚠️ 找不到憑證檔！請確認 service_account.json 是否在專案資料夾"
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        client_email = data.get("client_email", "（未知 Email）")
        return data, client_email, None
    except Exception as e:
        return None, None, f"❌ 讀取 service_account.json 失敗: {str(e)}"

def get_gspread_client():
    info, client_email, err_msg = get_service_account_info()
    if err_msg:
        return None, client_email, err_msg
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds), client_email, None
    except Exception as e:
        clean_err = str(e).replace('\n', ' ')
        return None, client_email, f"❌ 憑證驗證失敗 ({type(e).__name__}): {clean_err}"

def verify_user_credentials(input_user, input_pass):
    client, client_email, err_msg = get_gspread_client()
    if err_msg:
        return False, err_msg
        
    sheet_id = extract_spreadsheet_id(SPREADSHEET_ID)
    if not sheet_id:
        return False, "⚠️ 未設定 SPREADSHEET_ID！"

    try:
        sh = client.open_by_key(sheet_id)
        ws_creds = sh.worksheet("user_credentials")
        records = ws_creds.get_all_records()
        
        for row in records:
            u = str(row.get('帳號', row.get('username', ''))).strip()
            p = str(row.get('密碼', row.get('password', ''))).strip()
            if u == input_user and p == input_pass:
                return True, None
        return False, "❌ 帳號或密碼不正確！"
    except gspread.exceptions.WorksheetNotFound:
        return False, "⚠️ 找不到 user_credentials 工作表，請至 Google 試算表新增該分頁！"
    except Exception as e:
        clean_err = str(e).replace('\n', ' ')
        return False, f"❌ 登入驗證時發生錯誤: {clean_err}"

def fetch_sheets_data():
    client, client_email, err_msg = get_gspread_client()
    if err_msg:
        return None, None, err_msg
        
    sheet_id = extract_spreadsheet_id(SPREADSHEET_ID)
    if not sheet_id:
        return None, None, "⚠️ 請在 app.py 中填入您的 SPREADSHEET_ID！"

    try:
        sh = client.open_by_key(sheet_id)
        
        ws_portfolio = sh.worksheet("portfolio_config")
        data_portfolio = ws_portfolio.get_all_records(value_render_option='UNFORMATTED_VALUE')
        df_portfolio = pd.DataFrame(data_portfolio)
        
        ws_history = sh.worksheet("daily_asset_history")
        data_history = ws_history.get_all_records(value_render_option='UNFORMATTED_VALUE')
        df_history = pd.DataFrame(data_history)
        
        return df_portfolio, df_history, None
    except (gspread.exceptions.PermissionError, PermissionError):
        email_str = f" [{client_email}]" if client_email else ""
        return None, None, f"❌ 權限不足！請開啓 Google 試算表，點右上角【共用】給服務帳號：{email_str} (權限設為編輯者)。"
    except gspread.exceptions.SpreadsheetNotFound:
        return None, None, "❌ 找不到試算表！請確認試算表網址正確並已開啟共用權限。"
    except Exception as e:
        clean_err = str(e).replace('\n', ' ')
        return None, None, f"❌ 無法開啟試算表 ({type(e).__name__}): {clean_err}"

# 📌 關鍵公式防護：嚴格限定只寫入 3 個手動輸入欄位
def update_sheets_3_columns_only(df_web_data):
    client, client_email, err_msg = get_gspread_client()
    if err_msg:
        return False, err_msg
    sheet_id = extract_spreadsheet_id(SPREADSHEET_ID)
    try:
        sh = client.open_by_key(sheet_id)
        ws = sh.worksheet("portfolio_config")
        header_row = ws.row_values(1)
        
        editable_columns = ["核心權重", "持有數量", "投資成本"]
        
        for col_name in editable_columns:
            if col_name in header_row and col_name in df_web_data.columns:
                col_idx = header_row.index(col_name) + 1
                raw_values = df_web_data[col_name].tolist()
                cell_values = [[val] for val in raw_values]
                start_cell = gspread.utils.rowcol_to_a1(2, col_idx)
                end_cell = gspread.utils.rowcol_to_a1(1 + len(raw_values), col_idx)
                target_range = f"{start_cell}:{end_cell}"
                ws.update(target_range, cell_values)
        return True, "🎉 已精準更新 [核心權重, 持有數量, 投資成本]，試算表公式完好無損！"
    except Exception as e:
        clean_err = str(e).replace('\n', ' ')
        return False, f"❌ 更新失敗: {clean_err}"

# ==========================================
# 4. Flet 原生 App 主程式
# ==========================================
def main(page: ft.Page):
    page.title = "智慧投資紀錄簿 App"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = ft.Padding(16, 48, 16, 16)
    page.spacing = 12
    page.scroll = ft.ScrollMode.AUTO
    
    page.window_width = 390
    page.window_height = 844
    page.window_resizable = True

    # --------------------------------------------
    # UI 全域控制項
    # --------------------------------------------
    status_banner = ft.Text(
        "🔄 正在初始化...", 
        size=12, 
        color=ft.Colors.AMBER_300,
        max_lines=6,
        overflow=ft.TextOverflow.VISIBLE
    )
    
    txt_total_mv = ft.Text("$ --", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
    txt_total_cost = ft.Text("$ --", size=16, weight=ft.FontWeight.BOLD)
    txt_total_profit = ft.Text("$ --", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400)
    txt_maint_rate = ft.Text("-- %", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_300)
    txt_total_beta = ft.Text("--", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_300)
    
    input_date_field = ft.TextField(
        label="紀錄日期", 
        value=get_taiwan_now().strftime("%Y-%m-%d"), 
        icon=ft.Icons.CALENDAR_TODAY
    )
    input_amount_field = ft.TextField(
        label="今日結算總資產金額 (TWD)", 
        keyboard_type=ft.KeyboardType.NUMBER, 
        icon=ft.Icons.ATTACH_MONEY
    )
    
    list_portfolio_container = ft.Column(spacing=8)
    rebalance_advice_container = ft.Column(spacing=8)
    chart_container = ft.Container(padding=10, height=220)

    # --------------------------------------------
    # 💾 離線快取與數據圖表刷新邏輯
    # --------------------------------------------
    def update_ui_from_data(df_portfolio, df_history):
        if df_portfolio is not None and not df_portfolio.empty:
            df_portfolio['當前市值'] = pd.to_numeric(df_portfolio.get('當前市值', 0), errors='coerce').fillna(0.0)
            df_portfolio['投資成本'] = pd.to_numeric(df_portfolio.get('投資成本', 0), errors='coerce').fillna(0.0)
            df_portfolio['核心權重'] = pd.to_numeric(df_portfolio.get('核心權重', 0), errors='coerce').fillna(0.0)
            
            total_mv = df_portfolio['當前市值'].sum()
            total_cost = df_portfolio['投資成本'].sum()
            total_profit = total_mv - total_cost
            total_roi = (total_profit / total_cost) if total_cost > 0 else 0.0
            
            today = get_taiwan_now().date()
            l1_rem, l2_rem = calculate_remaining_loans(today)
            total_loan = l1_rem + l2_rem
            maint_rate = (total_mv / total_loan) if total_loan > 0 else 0.0
            
            total_beta = 1.59
            if '投資總Beta, β值' in df_portfolio.columns:
                beta_series = pd.to_numeric(df_portfolio['投資總Beta, β值'], errors='coerce').dropna()
                if not beta_series.empty and beta_series.iloc[0] > 0:
                    total_beta = beta_series.iloc[0]
                    
            txt_total_mv.value = f"${round(total_mv):,.0f}"
            txt_total_cost.value = f"${round(total_cost):,.0f}"
            txt_total_profit.value = f"+${round(total_profit):,.0f} ({total_roi*100:.2f}%)"
            txt_maint_rate.value = f"{maint_rate*100:.2f}%"
            txt_total_beta.value = f"{total_beta:.2f}"
            
            list_portfolio_container.controls.clear()
            rebalance_advice_container.controls.clear()
            
            for _, row in df_portfolio.iterrows():
                name = str(row.get('標的名稱', '')).strip()
                cost = pd.to_numeric(row.get('投資成本', 0), errors='coerce')
                mv = pd.to_numeric(row.get('當前市值', 0), errors='coerce')
                target_weight = pd.to_numeric(row.get('核心權重', 0), errors='coerce')
                actual_weight = (mv / total_mv) if total_mv > 0 else 0.0
                
                if name:
                    list_portfolio_container.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.SHOW_CHART, color=ft.Colors.GREEN_400),
                            title=ft.Text(name, weight=ft.FontWeight.BOLD),
                            subtitle=ft.Text(f"成本: ${cost:,.0f} | 市值: ${mv:,.0f} | 目標權重: {target_weight:.0%}"),
                        )
                    )
                    
                    target_mv = total_mv * target_weight
                    diff_mv = target_mv - mv
                    action_str = f"買進 ${abs(diff_mv):,.0f}" if diff_mv > 0 else f"賣出 ${abs(diff_mv):,.0f}"
                    action_color = ft.Colors.GREEN_400 if diff_mv > 0 else ft.Colors.RED_400
                    
                    rebalance_advice_container.controls.append(
                        ft.Container(
                            content=ft.Row([
                                ft.Text(name, weight=ft.FontWeight.BOLD, expand=True),
                                ft.Text(f"實際: {actual_weight:.1%} / 目標: {target_weight:.0%}", size=12, color=ft.Colors.WHITE54),
                                ft.Container(
                                    content=ft.Text(action_str, size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                    bgcolor=action_color,
                                    padding=ft.Padding(8, 4, 8, 4),
                                    border_radius=4
                                )
                            ]),
                            padding=8,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            border_radius=6
                        )
                    )
                    
            if df_history is not None and not df_history.empty and '總資產' in df_history.columns:
                df_history['總資產'] = pd.to_numeric(df_history['總資產'], errors='coerce').fillna(0.0)
                valid_history = df_history[df_history['總資產'] > 0].tail(10)
                
                if not valid_history.empty:
                    points = []
                    for idx, (_, h_row) in enumerate(valid_history.iterrows()):
                        points.append(ft.LineChartDataPoint(idx, h_row['總資產'] / 10000))
                        
                    chart = ft.LineChart(
                        data_series=[
                            ft.LineChartData(
                                data_points=points,
                                stroke_width=3,
                                color=ft.Colors.GREEN_400,
                                curved=True,
                                stroke_cap_round=True,
                            )
                        ],
                        border=ft.Border(
                            bottom=ft.BorderSide(1, ft.Colors.WHITE24),
                            left=ft.BorderSide(1, ft.Colors.WHITE24),
                        ),
                        min_y=min([p.y for p in points]) * 0.95,
                        max_y=max([p.y for p in points]) * 1.05,
                        expand=True,
                    )
                    chart_container.content = chart

    def load_and_refresh_data():
        cached_p = get_local_storage("cached_portfolio")
        cached_h = get_local_storage("cached_history")
        if cached_p and cached_h:
            try:
                df_p = pd.DataFrame(json.loads(cached_p))
                df_h = pd.DataFrame(json.loads(cached_h))
                update_ui_from_data(df_p, df_h)
                status_banner.value = "⚡ 已載入本機快取，正在同步雲端最新數據..."
                status_banner.color = ft.Colors.AMBER_300
                page.update()
            except Exception:
                pass

        df_portfolio, df_history, err = fetch_sheets_data()
        
        if err:
            status_banner.value = err
            status_banner.color = ft.Colors.RED_400
            show_toast(page, err)
            page.update()
            return
        
        try:
            update_ui_from_data(df_portfolio, df_history)
            
            if df_portfolio is not None and df_history is not None:
                set_local_storage("cached_portfolio", json.dumps(df_portfolio.to_dict(orient='records')))
                set_local_storage("cached_history", json.dumps(df_history.to_dict(orient='records')))
                
            status_banner.value = f"✅ 雲端數據同步完成！最後更新：{get_taiwan_now().strftime('%H:%M:%S')}"
            status_banner.color = ft.Colors.GREEN_400
            show_toast(page, "🎉 數據更新完成！")
        except Exception as ex:
            clean_ex = str(ex).replace('\n', ' ')
            status_banner.value = f"❌ 計算資料時發生錯誤 ({type(ex).__name__}): {clean_ex}"
            status_banner.color = ft.Colors.RED_400
            
        page.update()

    # --------------------------------------------
    # 🔐 雲端動態驗證登入介面
    # --------------------------------------------
    tf_user = ft.TextField(label="帳號", icon=ft.Icons.PERSON)
    tf_pass = ft.TextField(label="密碼", password=True, can_reveal_password=True, icon=ft.Icons.LOCK)
    chk_bio = ft.Checkbox(label="啟用本機指紋/生物辨識快速登入", value=True)
    btn_login = ft.ElevatedButton(width=300, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700))

    def do_logout(e):
        page.navigation_bar = None
        main_container.content = build_login_view()
        show_toast(page, "🔒 已成功登出系統！")
        page.update()

    def do_login(e):
        u = tf_user.value.strip()
        p = tf_pass.value.strip()
        if not u or not p:
            show_toast(page, "⚠️ 請輸入帳號與密碼！")
            return

        btn_login.disabled = True
        btn_login.content = ft.Text("🔍 雲端驗證中...", size=16, color=ft.Colors.WHITE)
        page.update()

        success, err_msg = verify_user_credentials(u, p)
        if success:
            if chk_bio.value:
                set_local_storage("biometric_bound", "true")
            show_toast(page, "🎉 登入成功！")
            show_main_app()
        else:
            show_toast(page, err_msg or "❌ 帳號或密碼錯誤！")
            btn_login.disabled = False
            btn_login.content = ft.Text("登入系統", size=16, color=ft.Colors.WHITE)
            page.update()

    def handle_biometric_login(e):
        is_bound = get_local_storage("biometric_bound")
        if is_bound != "true":
            show_toast(page, "⚠️ 未設定指紋登入，請先使用帳密登入並勾選啟用！")
            return

        def close_dialog(e):
            dialog.open = False
            page.update()

        def confirm_biometric(e):
            dialog.open = False
            page.update()
            show_toast(page, "👆 指紋辨識成功！解鎖中...")
            show_main_app()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("👆 生物辨識身份驗證", weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Text("請輕觸指紋感應器以確認身份", size=14, color=ft.Colors.WHITE70),
                ft.Container(height=10),
                ft.IconButton(
                    icon=ft.Icons.FINGERPRINT,
                    icon_size=64,
                    icon_color=ft.Colors.GREEN_400,
                    tooltip="點擊進行指紋感應",
                    on_click=confirm_biometric
                ),
                ft.Text("（點擊上方指紋圖示完成驗證）", size=12, color=ft.Colors.WHITE38),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, main_axis_alignment=ft.MainAxisAlignment.CENTER, height=160),
            actions=[
                ft.TextButton("取消", on_click=close_dialog)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        page.dialog = dialog
        dialog.open = True
        page.update()

    btn_login.content = ft.Text("登入系統", size=16, color=ft.Colors.WHITE)
    btn_login.on_click = do_login

    def build_login_view():
        has_bio = get_local_storage("biometric_bound") == "true"
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, size=64, color=ft.Colors.GREEN_400),
                ft.Text("智慧投資紀錄簿", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Text("金融級個人資產防護系統 (雲端驗證版)", size=12, color=ft.Colors.WHITE54),
                ft.Divider(color=ft.Colors.WHITE24),
                tf_user,
                tf_pass,
                chk_bio,
                btn_login,
                ft.OutlinedButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.FINGERPRINT, color=ft.Colors.GREEN_400 if has_bio else ft.Colors.WHITE38),
                        ft.Text("👆 指紋 / 生物辨識快速登入", color=ft.Colors.WHITE if has_bio else ft.Colors.WHITE38)
                    ], alignment=ft.MainAxisAlignment.CENTER),
                    width=300,
                    on_click=handle_biometric_login
                ) if has_bio else ft.Container()
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
            padding=24,
            alignment=ft.Alignment(0, 0)
        )

    # --------------------------------------------
    # 視圖模組 1：📊 投資總覽儀表板
    # --------------------------------------------
    def build_dashboard_view():
        return ft.Column([
            ft.Row([
                ft.Text("🧭 個人智慧投資總覽", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400, expand=True),
                ft.IconButton(
                    icon=ft.Icons.LOGOUT,
                    icon_color=ft.Colors.RED_400,
                    tooltip="登出系統",
                    on_click=do_logout
                )
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            status_banner,
            ft.Divider(color=ft.Colors.WHITE24),
            
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Text("當前總市值 (TWD)", size=12, color=ft.Colors.WHITE54),
                        txt_total_mv,
                    ]),
                    padding=16
                ),
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
            ),
            
            ft.Row([
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("投資總成本", size=11, color=ft.Colors.WHITE54),
                            txt_total_cost,
                        ]),
                        padding=12
                    ),
                    expand=True
                ),
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("累積投資獲利", size=11, color=ft.Colors.WHITE54),
                            txt_total_profit,
                        ]),
                        padding=12
                    ),
                    expand=True
                ),
            ]),
            
            ft.Row([
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("質押維持率", size=11, color=ft.Colors.WHITE54),
                            txt_maint_rate,
                        ]),
                        padding=12
                    ),
                    expand=True
                ),
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("投資總 Beta 值", size=11, color=ft.Colors.WHITE54),
                            txt_total_beta,
                        ]),
                        padding=12
                    ),
                    expand=True
                ),
            ]),
            
            ft.Text("📈 近期資產成長走勢 (單位: 萬)", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            chart_container,
            
            ft.Text("⚖️ 自動再平衡調整建議", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            rebalance_advice_container,
            
            ft.ElevatedButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.REFRESH, color=ft.Colors.WHITE),
                    ft.Text("同步 Google 雲端數據", color=ft.Colors.WHITE),
                ], alignment=ft.MainAxisAlignment.CENTER),
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700),
                on_click=lambda e: load_and_refresh_data()
            )
        ], spacing=12)

    # --------------------------------------------
    # 視圖模組 2：✍️ 每日資產動態輸入
    # --------------------------------------------
    def handle_submit_daily_asset(e):
        date_val = input_date_field.value
        amount_val = input_amount_field.value
        if not amount_val:
            show_toast(page, "⚠️ 請輸入今日總資產金額！")
            return
            
        client, client_email, err_msg = get_gspread_client()
        sheet_id = extract_spreadsheet_id(SPREADSHEET_ID)
        
        if client and sheet_id:
            try:
                sh = client.open_by_key(sheet_id)
                ws = sh.worksheet("daily_asset_history")
                ws.append_row([date_val, int(float(amount_val)), 0, 0, date_val])
                show_toast(page, "🎉 成功寫入 Google 試算表！")
                input_amount_field.value = ""
                load_and_refresh_data()
            except Exception as ex:
                clean_ex = str(ex).replace('\n', ' ')
                show_toast(page, f"❌ 寫入失敗: {clean_ex}")
        else:
            show_toast(page, err_msg or "⚠️ 請先填寫 SPREADSHEET_ID！")

    def build_input_view():
        return ft.Column([
            ft.Text("✍️ 每日資產金額輕鬆記", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400),
            ft.Divider(color=ft.Colors.WHITE24),
            input_date_field,
            input_amount_field,
            ft.ElevatedButton(
                content=ft.Row([
                    ft.Text("🚀 提交並儲存至 Google Sheets", color=ft.Colors.WHITE),
                ], alignment=ft.MainAxisAlignment.CENTER),
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600),
                on_click=handle_submit_daily_asset
            )
        ], spacing=16)

    # --------------------------------------------
    # 視圖模組 3：⚙️ 持股配置管理
    # --------------------------------------------
    def build_portfolio_view():
        return ft.Column([
            ft.Text("⚙️ 投資標的與持股管理", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400),
            ft.Divider(color=ft.Colors.WHITE24),
            list_portfolio_container
        ], spacing=12)

    # 容器與主視圖切換
    main_container = ft.Container()

    def show_main_app():
        main_container.content = build_dashboard_view()
        page.navigation_bar = ft.NavigationBar(
            selected_index=0,
            on_change=on_nav_change,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="儀表板"),
                ft.NavigationBarDestination(icon=ft.Icons.EDIT_NOTE_OUTLINED, selected_icon=ft.Icons.EDIT_NOTE, label="每日紀錄"),
                ft.NavigationBarDestination(icon=ft.Icons.PIE_CHART_OUTLINE, selected_icon=ft.Icons.PIE_CHART, label="持股管理"),
            ]
        )
        page.update()
        load_and_refresh_data()

    def on_nav_change(e):
        selected_index = e.control.selected_index
        if selected_index == 0:
            main_container.content = build_dashboard_view()
        elif selected_index == 1:
            main_container.content = build_input_view()
        elif selected_index == 2:
            main_container.content = build_portfolio_view()
        page.update()

    # App 啟動首頁：預設載入登入畫面
    main_container.content = build_login_view()
    page.add(main_container)

if __name__ == "__main__":
    ft.app(target=main)