import streamlit as st
import sqlite3
import os
import base64
import pandas as pd

# --- 系統設定與初始化 ---
UPLOAD_DIR = "scanned_invoices"
DB_NAME = "invoice_system.db"

# 確保 PDF 存放目錄存在
os.makedirs(UPLOAD_DIR, exist_ok=True)

def init_db():
    """初始化 SQLite 資料庫與資料表"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_num TEXT PRIMARY KEY,
            vendor_name TEXT,
            vendor_nickname TEXT,
            vendor_tax_id TEXT,
            amount REAL,
            payable_amount REAL,
            billing_month TEXT,
            agent TEXT,
            remark TEXT,
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 輔助函式 ---
def check_invoice_exists(invoice_num):
    """檢查發票號碼是否已存在"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM invoices WHERE invoice_num = ?", (invoice_num,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def show_pdf(file_path):
    """安全地在網頁中預覽 PDF，並提供備用下載按鈕"""
    try:
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
            base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # 備案：下載按鈕 (當瀏覽器阻擋 iframe 預覽時可以使用)
        st.download_button(
            label="📥 下載此 PDF 檔案",
            data=pdf_bytes,
            file_name=os.path.basename(file_path),
            mime="application/pdf"
        )
        st.write("") # 排版留白
        
        # 線上預覽
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"⚠️ 無法讀取 PDF 檔案: {e}")

# --- 網頁主視覺與架構 ---
st.set_page_config(page_title="AP 發票管理系統", page_icon="🧾", layout="wide")
st.title("🧾 雲端發票掃描與查詢系統")
st.caption("版本：v2.0 強化版 | 提供防呆機制與動態資料表查詢")

# 使用 Tabs 建立現代化切換介面
tab_entry, tab_search = st.tabs(["📝 發票登錄與掃描上傳", "🔍 發票全欄位查詢與預覽"])

# ==================== 頁籤一：發票登錄與上傳 ====================
with tab_entry:
    st.subheader("新增發票與帳務基本資料")
    
    with st.form("invoice_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            invoice_num = st.text_input("發票號碼 * (必填，將作為唯一識別碼)", placeholder="例如：AB12345678").strip()
            vendor_name = st.text_input("廠商名稱 * (必填)").strip()
            vendor_nickname = st.text_input("廠商暱稱").strip()
            vendor_tax_id = st.text_input("廠商統編").strip()
            billing_month = st.text_input("款項月份", placeholder="例如：2026-07").strip()

        with col2:
            amount = st.number_input("發票金額", min_value=0.0, step=100.0, value=0.0)
            payable_amount = st.number_input("應付金額", min_value=0.0, step=100.0, value=0.0)
            agent = st.text_input("經辦人 * (必填)").strip()
            remark = st.text_area("備註", height=100).strip()
        
        st.markdown("---")
        uploaded_file = st.file_uploader("📎 選擇或拖放發票 PDF 掃描檔 *", type=["pdf"])
        
        submit_btn = st.form_submit_button("💾 儲存發票與歸檔", use_container_width=True)
        
        # 表單送出後的邏輯處理
        if submit_btn:
            if not invoice_num or not vendor_name or not agent:
                st.error("❌ 儲存失敗：『發票號碼』、『廠商名稱』與『經辦人』為必填欄位！")
            elif not uploaded_file:
                st.error("❌ 儲存失敗：請上傳發票 PDF 檔案！")
            elif check_invoice_exists(invoice_num):
                st.error(f"❌ 儲存失敗：發票號碼「{invoice_num}」已存在於系統中，請確認是否重複報帳！")
            else:
                # 儲存實體檔案
                file_name = f"{invoice_num}.pdf"
                save_path = os.path.join(UPLOAD_DIR, file_name)
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # 寫入資料庫
                try:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO invoices 
                        (invoice_num, vendor_name, vendor_nickname, vendor_tax_id, amount, payable_amount, billing_month, agent, remark, file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (invoice_num, vendor_name, vendor_nickname, vendor_tax_id, amount, payable_amount, billing_month, agent, remark, save_path))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"🎉 成功！發票 `{invoice_num}` 已歸檔完成。")
                except Exception as e:
                    st.error(f"❌ 資料庫寫入異常: {e}")

# ==================== 頁籤二：萬用欄位查詢 ====================
with tab_search:
    st.subheader("發票資料庫查詢")
    
    # 搜尋列
    search_query = st.text_input("🔍 請輸入關鍵字（廠商、發票號碼、經辦人、統編等...）", placeholder="留空則顯示全部資料").strip()
    
    # 從資料庫讀取資料 (直接使用 pandas 讀取，方便後續轉為動態表格)
    conn = sqlite3.connect(DB_NAME)
    
    if search_query:
        sql_query = '''
            SELECT 
                invoice_num AS '發票號碼', 
                vendor_name AS '廠商名稱', 
                vendor_tax_id AS '統編', 
                amount AS '發票金額', 
                payable_amount AS '應付金額', 
                billing_month AS '款項月份', 
                agent AS '經辦人',
                remark AS '備註',
                file_path
            FROM invoices 
            WHERE invoice_num LIKE ? OR vendor_name LIKE ? OR vendor_nickname LIKE ? 
               OR vendor_tax_id LIKE ? OR billing_month LIKE ? OR agent LIKE ? OR remark LIKE ?
            ORDER BY created_at DESC
        '''
        like_param = f"%{search_query}%"
        df = pd.read_sql_query(sql_query, conn, params=(like_param,)*7)
    else:
        sql_query = '''
            SELECT 
                invoice_num AS '發票號碼', vendor_name AS '廠商名稱', vendor_tax_id AS '統編', 
                amount AS '發票金額', payable_amount AS '應付金額', billing_month AS '款項月份', 
                agent AS '經辦人', remark AS '備註', file_path
            FROM invoices ORDER BY created_at DESC
        '''
        df = pd.read_sql_query(sql_query, conn)
    
    conn.close()
    
    # 顯示查詢結果
    if not df.empty:
        st.write(f"📊 共找到 **{len(df)}** 筆發票紀錄：")
        
        # 隱藏前端不需要顯示的 file_path 欄位來呈現漂亮的表格
        display_df = df.drop(columns=['file_path'])
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("👁️ 調閱發票掃描檔")
        
        # 讓使用者選擇要調閱哪一張發票 (防呆：只列出搜尋結果中有的發票)
        selected_invoice = st.selectbox(
            "請選擇要查看的發票號碼：", 
            df['發票號碼'].tolist(),
            index=None,
            placeholder="點此選擇發票..."
        )
        
        if selected_invoice:
            # 抓出選取發票的檔案路徑
            selected_row = df[df['發票號碼'] == selected_invoice].iloc[0]
            target_file = selected_row['file_path']
            
            st.write(f"**正在檢視：** `{selected_invoice}` | **廠商：** `{selected_row['廠商名稱']}`")
            
            if pd.notna(target_file) and os.path.exists(target_file):
                show_pdf(target_file)
            else:
                st.warning("⚠️ 系統找不到這張發票對應的實體 PDF 掃描檔，可能檔案已被移動或刪除。")
    else:
        st.info("💡 查無符合條件的發票資料。")
