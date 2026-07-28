# -*- coding: utf-8 -*-
"""
==================================================
專案名稱：智慧投資紀錄簿 Web App - 3 欄精準寫入同步模組
功能說明：只允許寫入【核心權重、持有數量、投資成本】，其他欄位完全維持試算表內設定與公式
==================================================
"""

import gspread
import pandas as pd

def save_and_sync_to_sheets(client, sheet_id, df_web_data):
    """
    將網頁編輯後的數據同步回 Google Sheets，嚴格限定僅更新 3 個指定欄位。
    
    參數說明：
    - client: 已通過授權的 gspread client 物件
    - sheet_id: Google 試算表 ID 或完整網址
    - df_web_data: 網頁上當前修改後的 Pandas DataFrame 資料
    """
    try:
        sh = client.open_by_key(sheet_id)
        ws = sh.worksheet("portfolio_config")
        
        # 1. 取得 Google Sheets 目前第一列的所有標題欄位
        header_row = ws.row_values(1)
        
        # 2. 嚴格限制：僅允許以下 3 個欄位寫入 Google Sheets
        editable_columns = [
            "核心權重",
            "持有數量",
            "投資成本"
        ]
        
        # 3. 逐一針對這 3 個許可欄位進行精準區域寫入
        updated_cols = []
        for col_name in editable_columns:
            if col_name in header_row and col_name in df_web_data.columns:
                # 找出該欄位在 Google Sheets 中的直欄索引 (從 1 開始)
                col_idx = header_row.index(col_name) + 1
                
                # 取得網頁上的資料陣列
                raw_values = df_web_data[col_name].tolist()
                
                # 轉成 gspread update 所需的二維陣列格式 [[val1], [val2], ...]
                cell_values = [[val] for val in raw_values]
                
                # 計算寫入範圍 (例如：從 C2 到 C8)
                start_cell = gspread.utils.rowcol_to_a1(2, col_idx)
                end_cell = gspread.utils.rowcol_to_a1(1 + len(raw_values), col_idx)
                target_range = f"{start_cell}:{end_cell}"
                
                # 寫入單一欄位
                ws.update(target_range, cell_values)
                updated_cols.append(col_name)
                
        return True, f"🎉 數據同步成功！已精準更新：{', '.join(updated_cols)}。其他欄位與公式均完整保留。"
        
    except Exception as e:
        clean_err = str(e).replace('\n', ' ')
        return False, f"❌ 同步至 Google Sheets 失敗: {clean_err}"


def load_sheets_data_safely(client, sheet_id):
    """
    從 Google Sheets 讀取完整資料（包含公式計算後的結果），供網頁端渲染展示
    """
    try:
        sh = client.open_by_key(sheet_id)
        ws = sh.worksheet("portfolio_config")
        
        # 使用 UNFORMATTED_VALUE 讀取公式運算後的數值，避免抓到公式原始碼字串
        records = ws.get_all_records(value_render_option='UNFORMATTED_VALUE')
        df = pd.DataFrame(records)
        return df, None
    except Exception as e:
        clean_err = str(e).replace('\n', ' ')
        return None, f"❌ 讀取資料失敗: {clean_err}"