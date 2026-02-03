import imaplib
import email
from email.header import decode_header
import re
import time

# --- CẤU HÌNH ---
IMAP_PORT = 993
SEZNAM_HOST = "imap.seznam.cz"
SENDER_FILTER = "Instagram"
# Chuỗi subject bắt buộc phải có (viết thường để so sánh không phân biệt hoa thường)
TARGET_SUBJECT = "we've made it easy to get back on instagram"

# --- REGEX ---
RE_USER_HI = re.compile(r'Hi\s+([a-zA-Z0-9_.]+),', re.IGNORECASE)
RE_UID_LINK = re.compile(r'uid=([0-9]{6,30})')

def _decode_header_fast(header_value):
    """Giải mã header nhanh."""
    if not header_value: return ""
    try:
        decoded_list = decode_header(header_value)
        result = []
        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                result.append(content.decode(encoding or "utf-8", errors="ignore"))
            else:
                result.append(str(content))
        return "".join(result)
    except:
        return str(header_value)

def _get_body_fast(msg):
    """Lấy body nhanh."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ["text/html", "text/plain"]:
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except: pass
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except: pass
    return ""

def verify_account_live(email_login, password):
    """
    Luồng xử lý: Connect -> Loop 30s -> Filter FROM -> Filter SUBJECT -> Fetch BODY -> Extract
    """
    mail = None
    try:
        # 1. KẾT NỐI
        mail = imaplib.IMAP4_SSL(SEZNAM_HOST, IMAP_PORT)
        try:
            mail.login(email_login, password)
        except Exception as e:
            return f"Login Mail Failed: {str(e)}"
            
        # [QUAN TRỌNG] readonly=True là lớp bảo vệ đầu tiên để không set Unread -> Read
        mail.select("INBOX", readonly=True) 

        # --- SETUP LOOP 30s ---
        start_time = time.time()
        timeout = 30
        
        found_data = None # Biến lưu kết quả tìm được

        while time.time() - start_time < timeout:
            try:
                # BƯỚC 1: QUÉT FROM (Lọc tầng 1)
                # Chỉ tìm mail từ Instagram.
                status, messages = mail.search(None, f'(FROM "{SENDER_FILTER}")')
                
                if status != "OK" or not messages[0]:
                    time.sleep(2) # Không thấy mail từ Instagram, nghỉ 2s rồi quét lại
                    continue

                # Lấy 5 mail mới nhất để xử lý cho nhanh
                mail_ids = messages[0].split()
                recent_ids = mail_ids[-5:] 
                
                for mid in reversed(recent_ids):
                    # BƯỚC 2: QUÉT SUBJECT (Lọc tầng 2)
                    # Dùng BODY.PEEK để KHÔNG đánh dấu đã đọc
                    _, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
                    
                    raw_header = data[0][1]
                    msg_header = email.message_from_bytes(raw_header)
                    subject = _decode_header_fast(msg_header["Subject"]).lower()

                    # [LOGIC CỐT LÕI] Chỉ khi Subject khớp chính xác cụm từ này mới đi tiếp
                    if TARGET_SUBJECT not in subject:
                        continue # Bỏ qua ngay, sang mail tiếp theo
                    
                    # BƯỚC 3: XÉT NỘI DUNG (Khi bước 1 và 2 đã đúng)
                    # Vẫn dùng BODY.PEEK
                    _, data_body = mail.fetch(mid, "(BODY.PEEK[])")
                    msg_body = email.message_from_bytes(data_body[0][1])
                    body_content = _get_body_fast(msg_body)
                    
                    # Trích xuất dữ liệu
                    user_extracted = ""
                    uid_extracted = ""
                    
                    m_user = RE_USER_HI.search(body_content)
                    if m_user: user_extracted = m_user.group(1).lower()
                    
                    m_uid = RE_UID_LINK.search(body_content)
                    if m_uid: uid_extracted = m_uid.group(1)
                    
                    if user_extracted or uid_extracted:
                        found_data = f"success|USER={user_extracted}|UID={uid_extracted}"
                        break # Break vòng for loop mail ID
                
                if found_data:
                    break # Break vòng while loop 30s
                
                # Nếu chưa thấy, nghỉ ngơi 1.5s rồi quét lại
                time.sleep(1.5)
                mail.noop() # Giữ kết nối

            except Exception:
                time.sleep(1)
                continue

        # Clean up
        try: mail.logout()
        except: pass

        if found_data:
            return found_data
             
        return "Fail: Timeout 30s - Mail not found"

    except Exception as e:
        return f"Error System: {str(e)}"