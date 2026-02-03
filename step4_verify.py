import time
import re
import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# --- CONFIG ---
CONFIRM_KEYWORDS = [
    # English
    "password has been changed",
    "password changed",
    "your instagram password has been changed",
    # Vietnamese
    "mật khẩu đã được thay đổi",
    "bạn vừa thay đổi mật khẩu",
    "mật khẩu instagram của bạn đã được thay đổi",
    "bạn đã thay đổi mật khẩu instagram",
    "bạn vừa đổi mật khẩu instagram",
    "bạn vừa đổi mật khẩu",
]
SENDER_NAME = "instagram"
MAIL_FRAME_ID = "thirdPartyFrame_mail"
MAIL_ITEMS_JS = """
const listHost =
  document.querySelector("#list > mail-list-container") ||
  document.querySelector("mail-list-container");
if (!listHost || !listHost.shadowRoot) return [];
let listMailList = listHost.shadowRoot.querySelector(
  "div > div.webmailer-mail-list__list-container > list-mail-list"
);
if (!listMailList) {
  listMailList = listHost.shadowRoot.querySelector("list-mail-list");
}
if (!listMailList || !listMailList.shadowRoot) return [];
let list = listMailList.shadowRoot.querySelector("div > div.list-mail-list");
if (!list) {
  list = listMailList.shadowRoot.querySelector("div.list-mail-list");
}
if (!list) {
  list = listMailList.shadowRoot;
}
return Array.from(list.querySelectorAll("list-mail-item"));
"""
IMAP_ENABLED = True
IMAP_ONLY = True
IMAP_HOST_DEFAULT = "imap.gmx.net"
IMAP_PORT = 993
IMAP_FOLDER = "INBOX"
IMAP_POLL_TIMEOUT = 25
IMAP_POLL_INTERVAL = 1.0
IMAP_MAX_FETCH = 15


def _find_element_in_frames(driver, by, value, depth=0, max_depth=3):
    try:
        return driver.find_element(by, value)
    except Exception:
        pass

    if depth >= max_depth:
        return None

    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            found = _find_element_in_frames(driver, by, value, depth + 1, max_depth)
            if found:
                return found
            driver.switch_to.parent_frame()
        except Exception:
            try:
                driver.switch_to.parent_frame()
            except Exception:
                pass
    return None


def _find_elements_in_frames(driver, by, value, depth=0, max_depth=3):
    try:
        elements = driver.find_elements(by, value)
        if elements:
            return elements
    except Exception:
        pass

    if depth >= max_depth:
        return []

    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            elements = _find_elements_in_frames(driver, by, value, depth + 1, max_depth)
            if elements:
                return elements
            driver.switch_to.parent_frame()
        except Exception:
            try:
                driver.switch_to.parent_frame()
            except Exception:
                pass
    return []


def _safe_call(label, func, default=None):
    try:
        return func()
    except Exception as exc:
        print(f"?? [{label}] {exc}")
        return default


def _decode_mime_words(value):
    if not value:
        return ""
    decoded = ""
    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            try:
                decoded += part.decode(encoding or "utf-8", errors="replace")
            except Exception:
                decoded += part.decode("utf-8", errors="replace")
        else:
            decoded += part
    return decoded


def _decode_payload(payload, charset):
    if payload is None:
        return ""
    try:
        return payload.decode(charset or "utf-8", errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


def _html_to_text(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    return re.sub(r"\s+", " ", text).strip()


def _imap_host_for_email(email_addr):
    if not email_addr or "@" not in email_addr:
        return IMAP_HOST_DEFAULT
    domain = email_addr.split("@", 1)[1].lower().strip()
    if domain.endswith("gmx.com"):
        return "imap.gmx.com"
    if domain.endswith("gmx.net") or domain.endswith("gmx.de"):
        return "imap.gmx.net"
    if domain.endswith("mail.com"):
        return "imap.mail.com"
    return IMAP_HOST_DEFAULT


def _imap_collect_message_parts(message):
    html_parts = []
    text_parts = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = _decode_payload(payload, part.get_content_charset())
            if content_type == "text/html":
                html_parts.append(text)
            elif content_type == "text/plain":
                text_parts.append(text)
    else:
        payload = message.get_payload(decode=True)
        if payload:
            text = _decode_payload(payload, message.get_content_charset())
            if message.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                text_parts.append(text)
    return "\n".join(html_parts), "\n".join(text_parts)


def _imap_fetch_message(imap_conn, msg_id):
    try:
        status, data = imap_conn.fetch(msg_id, "(BODY.PEEK[])")
    except Exception:
        return None
    if status != "OK" or not data:
        return None
    for item in data:
        if isinstance(item, tuple) and item[1]:
            try:
                return email.message_from_bytes(item[1])
            except Exception:
                return None
    return None


def _imap_search_ids(imap_conn, unseen_first=True):
    criteria_sets = [("UNSEEN",)] if unseen_first else []
    criteria_sets.append(("ALL",))
    for criteria in criteria_sets:
        try:
            status, data = imap_conn.search(None, *criteria)
        except Exception:
            continue
        if status != "OK" or not data:
            continue
        raw = data[0] or b""
        ids = raw.split()
        if ids:
            return ids
    return []


def _text_contains_confirm(text, ig_user=None):
    if not text:
        return False
    text_low = text.lower()
    if ig_user:
        ig_user_low = ig_user.strip().lower()
        if ig_user_low and ig_user_low not in text_low:
            return False
    return any(kw in text_low for kw in CONFIRM_KEYWORDS)


def _imap_find_confirm(email_addr, password, ig_user=None, timeout=IMAP_POLL_TIMEOUT):
    if not email_addr or not password:
        return False
    host = _imap_host_for_email(email_addr)
    try:
        imap_conn = imaplib.IMAP4_SSL(host, IMAP_PORT)
    except Exception as exc:
        print(f"?? [IMAP] Connect failed: {exc}")
        return False

    try:
        imap_conn.login(email_addr, password)
    except Exception as exc:
        print(f"?? [IMAP] Login failed: {exc}")
        try:
            imap_conn.logout()
        except Exception:
            pass
        return False

    try:
        status, _ = imap_conn.select(IMAP_FOLDER)
        if status != "OK":
            print("?? [IMAP] Select inbox failed.")
            return False

        end_time = time.time() + timeout
        while True:
            ids = _imap_search_ids(imap_conn, unseen_first=True)
            if ids:
                ids = ids[-IMAP_MAX_FETCH:]
            for msg_id in reversed(ids):
                message = _imap_fetch_message(imap_conn, msg_id)
                if not message:
                    continue
                subject = _decode_mime_words(message.get("Subject", "")).strip()
                from_addr = parseaddr(message.get("From", ""))[1].lower()
                html_part, text_part = _imap_collect_message_parts(message)
                body_text = text_part or _html_to_text(html_part)
                subject_low = subject.lower()
                body_low = body_text.lower()
                if (
                    SENDER_NAME not in from_addr
                    and SENDER_NAME not in subject_low
                    and SENDER_NAME not in body_low
                ):
                    continue
                if _text_contains_confirm(subject_low, ig_user) or _text_contains_confirm(body_low, ig_user):
                    return True
            if time.time() >= end_time:
                break
            time.sleep(IMAP_POLL_INTERVAL)
    finally:
        try:
            imap_conn.logout()
        except Exception:
            pass
    return False


def _safe_text(root, selector):
    try:
        return root.find_element(By.CSS_SELECTOR, selector).text.strip().lower()
    except Exception:
        return ""


def _is_unread(item):
    class_attr = (item.get_attribute("class") or "").lower()
    return "list-mail-item--unread" in class_attr


def _matches_confirm(item, ig_user=None):
    sender = _safe_text(item, "div.list-mail-item__sender-trusted-text")
    subject = _safe_text(item, "div.list-mail-item__subject")
    full_text = (sender + " " + subject).strip()
    if SENDER_NAME not in full_text:
        full_text = (item.text or "").lower()
        if not full_text:
            try:
                full_text = (item.get_attribute("innerText") or "").lower()
            except Exception:
                full_text = ""
        if SENDER_NAME not in full_text:
            return False
    if ig_user:
        ig_user_low = ig_user.strip().lower()
        if ig_user_low and ig_user_low not in full_text:
            return False
    keywords = [kw.lower() for kw in CONFIRM_KEYWORDS]
    return any(kw in full_text for kw in keywords)


def _switch_to_mail_frame(driver):
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    frame = None
    try:
        frame = driver.find_element(By.ID, MAIL_FRAME_ID)
    except Exception:
        pass
    if not frame:
        try:
            frame = driver.find_element(
                By.CSS_SELECTOR, "#thirdPartyFrame_mail, iframe[name='mail']"
            )
        except Exception:
            return False
    try:
        driver.switch_to.frame(frame)
        return True
    except Exception:
        return False


def wait_mail_frame_ready(driver, timeout=15):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if not _switch_to_mail_frame(driver):
            time.sleep(0.5)
            continue
        try:
            ready = driver.execute_script(
                "return !!document.querySelector('#list > mail-list-container');"
            )
            if ready:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _get_mail_items_shadow(driver):
    if not _switch_to_mail_frame(driver):
        return []
    try:
        items = driver.execute_script(MAIL_ITEMS_JS)
        return items or []
    except Exception:
        return []


def wait_page_ready(driver, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass


def wait_mail_list_loaded(driver, timeout=15):
    if not wait_mail_frame_ready(driver, timeout=min(8, timeout)):
        return False
    end_time = time.time() + timeout
    while time.time() < end_time:
        items = _get_mail_items_shadow(driver)
        if items:
            return True
        container = _find_mail_list_container(driver)
        if container:
            items = container.find_elements(By.CSS_SELECTOR, "list-mail-item")
            if items:
                return True
        time.sleep(0.5)
    return False


def _find_mail_list_container(driver):
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    container = _find_element_in_frames(driver, By.CSS_SELECTOR, "div.list-mail-list")
    return container


def scan_mail_items(driver):
    items = _get_mail_items_shadow(driver)
    if items:
        return items
    container = _find_mail_list_container(driver)
    if container:
        items = container.find_elements(By.CSS_SELECTOR, "list-mail-item")
        if items:
            return items
    return _find_elements_in_frames(driver, By.TAG_NAME, "list-mail-item")


def execute_step4(driver, email="", password="", ig_user=None):
    print("--- [STEP 4] VERIFY CONFIRM MAIL ---")

    if IMAP_ONLY and not IMAP_ENABLED:
        print("?? IMAP-only mode but IMAP is disabled.")
        return False

    if IMAP_ENABLED and email and password:
        print("-> IMAP: polling confirm mail...")
        found = _safe_call(
            "ImapConfirm", lambda: _imap_find_confirm(email, password, ig_user), False
        )
        if found:
            print("? [SUCCESS] Confirm mail found via IMAP.")
            return True
        if IMAP_ONLY:
            print("? [FAIL] IMAP confirm mail not found.")
            return False
    elif IMAP_ENABLED and IMAP_ONLY:
        print("-> IMAP: skipped (missing credentials).")
        return False
    elif IMAP_ENABLED:
        print("-> IMAP: skipped (missing credentials).")

    _safe_call("PageReady", lambda: wait_page_ready(driver, timeout=15))
    _safe_call("MailFrameReady", lambda: wait_mail_frame_ready(driver, timeout=15))
    _safe_call("MailListReady", lambda: wait_mail_list_loaded(driver, timeout=15))

    max_retries = 4
    for i in range(max_retries):
        print(f"   -> Check {i+1}/{max_retries}...")
        _safe_call("Refresh", driver.refresh)
        _safe_call("PageReady", lambda: wait_page_ready(driver, timeout=15))
        _safe_call("MailFrameReady", lambda: wait_mail_frame_ready(driver, timeout=15))
        _safe_call("MailListReady", lambda: wait_mail_list_loaded(driver, timeout=15))

        mail_items = _safe_call("ScanMail", lambda: scan_mail_items(driver), [])
        if not mail_items:
            print("   ... Mail list not loaded, retry.")
            continue

        found = False
        for item in mail_items:
            try:
                if _is_unread(item) and _matches_confirm(item, ig_user):
                    print(f"? [SUCCESS] Confirm mail found: {(item.text or '')[:60]}...")
                    found = True
                    break
            except Exception:
                continue

        if found:
            return True

        print("   ... Not found yet, wait 10s.")
        time.sleep(10)

    print("? [FAIL] Timeout waiting for confirm mail.")
    return False


if __name__ == "__main__":
    print("Run after Step 1-3 are done.")
