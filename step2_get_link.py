import time
import re
import html
import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# --- CONFIG ---
FAST_MODE = True
MAIL_WAIT_PAGE_TIMEOUT = 12 if FAST_MODE else 20
MAIL_WAIT_FRAME_TIMEOUT = 12 if FAST_MODE else 20
MAIL_WAIT_LIST_TIMEOUT = 12 if FAST_MODE else 20
MAIL_WAIT_DETAIL_TIMEOUT = 10 if FAST_MODE else 20
MAIL_FAST_POLL_TIMEOUT = 3 if FAST_MODE else 0
MAIL_FAST_POLL_INTERVAL = 0.3 if FAST_MODE else 0.5
MAIL_MAX_RETRIES = 4 if FAST_MODE else 5
MAIL_RETRY_SLEEP = 1.5 if FAST_MODE else 3
MAIL_REFRESH_EVERY = 2 if FAST_MODE else 1
DEBUG_DUMP_MAIL = False if FAST_MODE else True
IMAP_ENABLED = True
IMAP_ONLY = True
IMAP_HOST_DEFAULT = "imap.gmx.net"
IMAP_PORT = 993
IMAP_FOLDER = "INBOX"
IMAP_POLL_TIMEOUT = 18 if FAST_MODE else 25
IMAP_POLL_INTERVAL = 1.0
IMAP_MAX_FETCH = 15

RESET_KEYWORDS = [
    # English
    "reset your password",
    "easy to get back on instagram",
    "trouble logging into instagram",
    "we've made it easy",
    "get back on instagram",
    # Vietnamese
    "đặt lại mật khẩu",
    "khôi phục mật khẩu",
    "lấy lại mật khẩu instagram",
    "đặt lại mật khẩu instagram",
    "khó đăng nhập vào instagram",
    "chúng tôi đã giúp bạn dễ dàng hơn",
    "lấy lại quyền truy cập instagram",
]
SENDER_NAME = "instagram"
RESET_LINK_XPATH = (
    "//a[contains(., 'Reset your password') or contains(., 'Reset Password') or "
    "contains(., 'Passwort')]"
)
RESET_LINK_DEEP_XPATH = (
    "/html/body/table/tbody/tr/td/table/tbody/tr[4]/td/table/tbody/tr/td/"
    "table/tbody/tr[4]/td[2]/a"
)
RESET_LINK_DEEP_XPATH_ALT = (
    "/html/body/table/tbody/tr/td/table/tbody/tr[4]/td/table/tbody/tr/td/"
    "table/tbody/tr[5]/td[2]/table/tbody/tr/td/table/tbody/tr/td[1]/"
    "table/tbody/tr[3]/td/a"
)
RESET_LINK_TEXT_XPATH = (
    "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset') and "
    "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]/ancestor::a[1]"
)
RESET_LINK_TEXT_EXACT = "reset your password"
RESET_LINK_TEXT_EXACT_XPATH = (
    "//a[normalize-space(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))="
    "'reset your password']"
)
RESET_LINK_HREF_XPATH = (
    "//a[contains(translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'instagram') and "
    "contains(translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset')]"
)
RESET_LINK_COLOR_CSS = (
    "td[style*='rgb(71,162,234)'] a, td[style*='rgb(71, 162, 234)'] a"
)
RESET_LINK_HREF_HINTS = [
    "instagram.com/accounts/password/reset/confirm",
    "instagram.com/accounts/password/reset",
    "password/reset/confirm",
    "one_click_login_email",
    "deref-gmx.net/mail/client",
    "redirecturl=",
]
MAIL_LIST_XPATH = (
    "/html/body/div/div[1]/div[1]/webmailer-mail-list/mail-list-container"
    "//div/div[1]/list-mail-list//div/div[2]"
)
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
MAIL_FIND_TARGET_JS = """
const listHost =
  document.querySelector("#list > mail-list-container") ||
  document.querySelector("mail-list-container");
if (!listHost || !listHost.shadowRoot) return null;
let listMailList = listHost.shadowRoot.querySelector(
  "div > div.webmailer-mail-list__list-container > list-mail-list"
);
if (!listMailList) {
  listMailList = listHost.shadowRoot.querySelector("list-mail-list");
}
if (!listMailList || !listMailList.shadowRoot) return null;
let list = listMailList.shadowRoot.querySelector("div > div.list-mail-list");
if (!list) {
  list = listMailList.shadowRoot.querySelector("div.list-mail-list");
}
if (!list) {
  list = listMailList.shadowRoot;
}
const items = Array.from(list.querySelectorAll("list-mail-item"));
const keywords = (arguments[0] || []).map(k => (k || "").toLowerCase());
const sender = (arguments[1] || "").toLowerCase();
const matches = (txt) => {
  if (!txt) return false;
  const t = txt.toLowerCase();
  if (sender && !t.includes(sender)) return false;
  return keywords.some(k => k && t.includes(k));
};
const getTs = (item) => {
  try {
    const label = item.querySelector("list-date-label");
    if (label) {
      const raw = label.getAttribute("date-in-ms") || label.getAttribute("dateInMs") || "";
      const value = parseInt(raw, 10);
      if (!Number.isNaN(value)) return value;
    }
  } catch (e) {}
  return 0;
};
let best = null;
let bestTs = -1;
let bestIdx = 1e9;
for (let idx = 0; idx < items.length; idx++) {
  const item = items[idx];
  const text = (item.innerText || item.textContent || "").toLowerCase();
  if (!matches(text)) continue;
  const ts = getTs(item);
  if (ts > 0) {
    if (ts > bestTs || (ts === bestTs && idx < bestIdx)) {
      best = item;
      bestTs = ts;
      bestIdx = idx;
    }
    continue;
  }
  if (bestTs <= 0 && idx < bestIdx) {
    best = item;
    bestIdx = idx;
  }
}
return best;
"""
MAIL_DETAIL_USER_SELECTOR = (
    "#email_content > table > tbody > tr:nth-child(4) > td > table > tbody > tr > td > "
    "table > tbody > tr:nth-child(1) > td:nth-child(2) > p:nth-child(1)"
)
MAIL_DETAIL_RESET_SELECTORS = [
    "#email_content > table > tbody > tr:nth-child(4) > td > table > tbody > tr > td > "
    "table > tbody > tr:nth-child(5) > td:nth-child(2) > table > tbody > tr > td > "
    "table > tbody > tr > td:nth-child(1) > table > tbody > tr:nth-child(3) > td > "
    "a > table > tbody > tr > td > a",
    "#email_content > table > tbody > tr:nth-child(4) > td > table > tbody > tr > td > "
    "table > tbody > tr:nth-child(5) > td:nth-child(2) > table > tbody > tr > td > "
    "table > tbody > tr > td:nth-child(1) > table > tbody > tr:nth-child(3) > td > "
    "a > table > tbody > tr > td",
]
RESET_BUTTON_XPATHS = [
    RESET_LINK_TEXT_EXACT_XPATH,
    RESET_LINK_TEXT_XPATH,
    RESET_LINK_HREF_XPATH,
]
MAIL_DETAIL_RESET_XPATHS = [
    RESET_LINK_DEEP_XPATH,
    RESET_LINK_DEEP_XPATH_ALT,
    RESET_LINK_TEXT_EXACT_XPATH,
    RESET_LINK_TEXT_XPATH,
    RESET_LINK_HREF_XPATH,
]

MAIL_DETAIL_CONTENT_JS = """
const listHost =
  document.querySelector("#list > mail-list-container") ||
  document.querySelector("mail-list-container");
if (!listHost) return ["", ""];
let detailHost = null;
if (listHost.shadowRoot) {
  const details = listHost.shadowRoot.querySelector("div > div.list-mail-details");
  if (details) {
    const slot = details.querySelector("slot");
    if (slot && slot.assignedElements) {
      const assigned = slot.assignedElements();
      detailHost = assigned.find(
        el => el.tagName && el.tagName.toLowerCase() === "webmailer-mail-detail"
      );
    }
  }
}
if (!detailHost) {
  detailHost = listHost.querySelector("webmailer-mail-detail");
}
if (!detailHost || !detailHost.shadowRoot) return ["", ""];
const root = detailHost.shadowRoot.querySelector("div");
if (!root) return ["", ""];
let email = root.querySelector("#email_content");
if (!email) {
  const iframe =
    root.querySelector("iframe[name='detail-body-iframe']") ||
    root.querySelector("iframe");
  if (iframe) {
    try {
      const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
      if (doc) {
        email = doc.querySelector("#email_content") || doc.body;
      }
    } catch (e) {}
  }
}
if (!email) return ["", ""];
let text = "";
try {
  text = (email.textContent || "").replace(/\s+/g, " ").trim();
} catch (e) {}
let html = "";
if (!text) {
  try {
    html = email.innerHTML || "";
  } catch (e) {}
}
return [text, html];
"""



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


def wait_element_any_frame(driver, by, value, timeout=10, max_depth=3):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        el = _find_element_in_frames(driver, by, value, max_depth=max_depth)
        if el:
            try:
                if el.is_displayed():
                    return el
            except Exception:
                return el
        time.sleep(0.5)
    return None


def _wait_for_new_window(driver, previous_handles, timeout=10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            handles = driver.window_handles
        except Exception:
            handles = []
        for handle in handles:
            if handle not in previous_handles:
                return handle
        time.sleep(0.3)
    return None


def _get_window_url(driver, handle, timeout=5):
    try:
        driver.switch_to.window(handle)
    except Exception:
        return ""
    end_time = time.time() + timeout
    url = ""
    while time.time() < end_time:
        try:
            url = driver.current_url or ""
        except Exception:
            url = ""
        if url and url != "about:blank":
            return url
        time.sleep(0.3)
    return url


def _cache_reset_target(driver, handle="", url=""):
    try:
        if handle:
            driver.reset_handle = handle
        if url:
            driver.reset_url = url
    except Exception:
        pass


def _open_reset_link_in_new_tab(driver, url, timeout=10):
    if not url:
        return ""
    previous_handles = set(driver.window_handles)
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", url)
    except Exception:
        try:
            driver.execute_script("window.open('about:blank', '_blank');")
        except Exception:
            return ""
    new_handle = _wait_for_new_window(driver, previous_handles, timeout=timeout)
    if new_handle:
        try:
            driver.switch_to.window(new_handle)
            current_url = ""
            try:
                current_url = driver.current_url or ""
            except Exception:
                current_url = ""
            if url and (not current_url or current_url == "about:blank"):
                driver.get(url)
        except Exception:
            pass
        _cache_reset_target(driver, handle=new_handle, url=url)
        return new_handle
    return ""


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


def _imap_find_reset_link(email_addr, password, timeout=IMAP_POLL_TIMEOUT):
    if not email_addr or not password:
        return "", "", ""
    host = _imap_host_for_email(email_addr)
    try:
        imap_conn = imaplib.IMAP4_SSL(host, IMAP_PORT)
    except Exception as exc:
        print(f"?? [IMAP] Connect failed: {exc}")
        return "", "", ""

    try:
        imap_conn.login(email_addr, password)
    except Exception as exc:
        print(f"?? [IMAP] Login failed: {exc}")
        try:
            imap_conn.logout()
        except Exception:
            pass
        return "", "", ""

    try:
        status, _ = imap_conn.select(IMAP_FOLDER)
        if status != "OK":
            print("?? [IMAP] Select inbox failed.")
            return "", "", ""

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
                subject_low = subject.lower()
                header_blob = f"{from_addr} {subject_low}"
                if "instagram" not in header_blob and not any(
                    kw in subject_low for kw in RESET_KEYWORDS
                ):
                    continue
                html_part, text_part = _imap_collect_message_parts(message)
                link = ""
                if html_part:
                    link = _extract_reset_link_from_html(html_part)
                if not link and text_part:
                    link = _extract_reset_link_from_html(text_part)
                if not link and html_part and text_part:
                    link = _extract_reset_link_from_html(html_part + "\n" + text_part)
                if link:
                    text_out = text_part or _html_to_text(html_part)
                    return link, text_out, subject

            if time.time() >= end_time:
                break
            time.sleep(IMAP_POLL_INTERVAL)
    finally:
        try:
            imap_conn.logout()
        except Exception:
            pass
    return "", "", ""


def _safe_call(label, func, default=None):
    try:
        return func()
    except Exception as exc:
        print(f"?? [{label}] {exc}")
        return default


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


def _find_target_mail_fast(driver):
    if not _switch_to_mail_frame(driver):
        return None
    try:
        keywords = [kw.lower() for kw in RESET_KEYWORDS]
        return driver.execute_script(MAIL_FIND_TARGET_JS, keywords, SENDER_NAME.lower())
    except Exception:
        return None


def _poll_for_target_mail(driver, timeout=MAIL_FAST_POLL_TIMEOUT, interval=MAIL_FAST_POLL_INTERVAL):
    if not timeout or timeout <= 0:
        return _find_target_mail_fast(driver)
    end_time = time.time() + timeout
    while time.time() < end_time:
        target = _find_target_mail_fast(driver)
        if target:
            return target
        time.sleep(interval)
    return None


def _get_mail_detail_user(driver):
    if not _switch_to_mail_frame(driver):
        return ""
    try:
        raw_text = driver.execute_script(
            """
const listHost =
  document.querySelector("#list > mail-list-container") ||
  document.querySelector("mail-list-container");
if (!listHost) return "";
let detailHost = null;
if (listHost.shadowRoot) {
  const details = listHost.shadowRoot.querySelector("div > div.list-mail-details");
  if (details) {
    const slot = details.querySelector("slot");
    if (slot && slot.assignedElements) {
      const assigned = slot.assignedElements();
      detailHost = assigned.find(
        el => el.tagName && el.tagName.toLowerCase() === "webmailer-mail-detail"
      );
    }
  }
}
if (!detailHost) {
  detailHost = listHost.querySelector("webmailer-mail-detail");
}
if (!detailHost || !detailHost.shadowRoot) return "";
const root = detailHost.shadowRoot.querySelector("div");
if (!root) return "";
let email = root.querySelector("#email_content");
if (!email) {
  const iframe =
    root.querySelector("iframe[name='detail-body-iframe']") ||
    root.querySelector("iframe");
  if (iframe) {
    try {
      const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
      if (doc) {
        email = doc.querySelector("#email_content");
      }
    } catch (e) {}
  }
}
if (!email) return "";
const el = email.querySelector(arguments[0]);
return el ? el.textContent.trim() : "";
""",
            MAIL_DETAIL_USER_SELECTOR,
        )
        text = (raw_text or "").strip()
        if text.lower().startswith("hi "):
            text = text[3:].strip()
        if text.endswith(","):
            text = text[:-1].strip()
        if " " in text:
            text = text.split()[0].strip()
        return text
    except Exception:
        return ""


def _click_reset_in_detail_current_frame(driver):
    try:
        return driver.execute_script(
            """
const listHost =
  document.querySelector("#list > mail-list-container") ||
  document.querySelector("mail-list-container");
if (!listHost) return false;
let detail = null;
if (listHost.shadowRoot) {
  const details = listHost.shadowRoot.querySelector("div > div.list-mail-details");
  if (details) {
    const slot = details.querySelector("slot");
    if (slot && slot.assignedElements) {
      const assigned = slot.assignedElements();
      detail = assigned.find(
        el => el.tagName && el.tagName.toLowerCase() === "webmailer-mail-detail"
      );
    }
  }
}
if (!detail) {
  try {
    detail = listHost.querySelector("webmailer-mail-detail");
  } catch (e) {}
}
if (!detail || !detail.shadowRoot) return false;
const root = detail.shadowRoot.querySelector("div");
if (!root) return false;
let email = root.querySelector("#email_content");
if (!email) {
  const iframe =
    root.querySelector("iframe[name='detail-body-iframe']") ||
    root.querySelector("iframe");
  if (iframe) {
    try {
      const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
      if (doc) {
        email = doc.querySelector("#email_content");
      }
    } catch (e) {}
  }
}
if (!email) return false;
const selectors = arguments[0] || [];
const xpaths = arguments[1] || [];
for (const xp of xpaths) {
  if (!xp) continue;
  let rel = xp;
  if (rel.startsWith("/html/body/")) {
    rel = ".//" + rel.slice(11);
  } else if (rel.startsWith("/")) {
    rel = "." + rel;
  }
  try {
    const node = document.evaluate(
      rel,
      email,
      null,
      XPathResult.FIRST_ORDERED_NODE_TYPE,
      null
    ).singleNodeValue;
    if (node) {
      const link = node.closest("a") || node;
      link.click();
      return true;
    }
  } catch (e) {}
}
for (const sel of selectors) {
  const el = email.querySelector(sel);
  if (!el) continue;
  const link = el.closest("a") || el;
  link.click();
  return true;
}
const anchors = Array.from(email.querySelectorAll("a"));
const keywords = ["reset your password", "reset password", "passwort"];
const hrefHints = [
  "instagram.com/accounts/password/reset",
  "password/reset/confirm",
  "one_click_login_email",
  "reset"
];
for (const a of anchors) {
  const text = (a.textContent || "").trim().toLowerCase();
  const href = (a.getAttribute("href") || "").toLowerCase();
  if (keywords.some(k => text.includes(k)) || hrefHints.some(h => href.includes(h))) {
    a.click();
    return true;
  }
}
const colorAnchors = email.querySelectorAll(
  "td[style*='rgb(71,162,234)'] a, td[style*='rgb(71, 162, 234)'] a"
);
if (colorAnchors.length) {
  let chosen = null;
  for (const a of colorAnchors) {
    const text = (a.textContent || "").trim().toLowerCase();
    if (text.includes("reset")) {
      chosen = a;
      break;
    }
  }
  if (!chosen) {
    chosen = colorAnchors.length > 1 ? colorAnchors[1] : colorAnchors[0];
  }
  chosen.click();
  return true;
}
return false;
""",
            MAIL_DETAIL_RESET_SELECTORS,
            MAIL_DETAIL_RESET_XPATHS,
        )
    except Exception:
        return False


def _click_reset_in_detail(driver):
    if not _switch_to_mail_frame(driver):
        return False
    return _click_reset_in_detail_current_frame(driver)


def _click_reset_deep_xpath_any_frame(driver, timeout=10, max_depth=4):
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    for xpath in MAIL_DETAIL_RESET_XPATHS:
        if not xpath:
            continue
        target = wait_element_any_frame(
            driver, By.XPATH, xpath, timeout=timeout, max_depth=max_depth
        )
        if not target:
            continue
        try:
            target.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", target)
            except Exception:
                return False
        return True
    return False


def _normalize_href(href):
    if not href:
        return ""
    return html.unescape(href).strip()


def _normalize_anchor_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip().lower()


def _is_reset_href(href):
    if not href:
        return False
    href_low = href.lower()
    if "reset" not in href_low and "password" not in href_low and "one_click_login_email" not in href_low:
        return False
    return any(hint in href_low for hint in RESET_LINK_HREF_HINTS)


def _extract_reset_link_from_html(raw_html):
    if not raw_html:
        return ""
    raw_html = html.unescape(raw_html)
    for match in re.finditer(
        r'(?:href|data-href|data-url)\s*=\s*["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    ):
        href = _normalize_href(match.group(1))
        if _is_reset_href(href):
            return href
    for match in re.finditer(r"https?://[^\s\"'>]+", raw_html, re.IGNORECASE):
        href = _normalize_href(match.group(0))
        if _is_reset_href(href):
            return href
    return ""


def _extract_reset_link_from_elements(elements):
    for el in elements:
        try:
            text = _normalize_anchor_text(el.text or "")
        except Exception:
            continue
        if text != RESET_LINK_TEXT_EXACT:
            continue
        try:
            href = _normalize_href(el.get_attribute("href") or "")
        except Exception:
            href = ""
        if href:
            return href

    for el in elements:
        try:
            href = _normalize_href(el.get_attribute("href") or "")
        except Exception:
            continue
        if not href:
            continue
        text = (el.text or "").lower()
        if "reset" in text and "password" in text:
            return href
        if _is_reset_href(href):
            return href
    for el in elements:
        try:
            href = _normalize_href(el.get_attribute("href") or "")
        except Exception:
            continue
        if href:
            return href
    return ""


def _collect_reset_links_by_text_in_dom(driver):
    try:
        email = driver.find_element(By.ID, "email_content")
    except Exception:
        return []
    try:
        anchors = email.find_elements(By.TAG_NAME, "a")
    except Exception:
        return []
    matches = []
    for el in anchors:
        try:
            text = _normalize_anchor_text(el.text or "")
        except Exception:
            continue
        if text != RESET_LINK_TEXT_EXACT:
            continue
        try:
            href = _normalize_href(el.get_attribute("href") or "")
        except Exception:
            href = ""
        if href:
            matches.append(href)
    return matches


def _collect_reset_links_by_text_in_detail_iframe(driver):
    frame = _get_detail_body_iframe_element(driver)
    if not frame:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        return []
    try:
        driver.switch_to.frame(frame)
        return _collect_reset_links_by_text_in_dom(driver)
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass


def _extract_reset_link_from_email_content_dom(driver):
    try:
        email = driver.find_element(By.ID, "email_content")
    except Exception:
        return ""
    try:
        anchors = email.find_elements(By.TAG_NAME, "a")
    except Exception:
        anchors = []
    reset_links = _collect_reset_links_by_text_in_dom(driver)
    if reset_links:
        return reset_links[0]
    link = _extract_reset_link_from_elements(anchors)
    if link:
        return link
    try:
        raw_html = email.get_attribute("innerHTML")
    except Exception:
        raw_html = ""
    return _extract_reset_link_from_html(raw_html)


def _extract_reset_link_shadow_detail(driver):
    if not _switch_to_mail_frame(driver):
        return ""
    try:
        href = driver.execute_script(
            """
const listHost =
  document.querySelector("#list > mail-list-container") ||
  document.querySelector("mail-list-container");
if (!listHost) return "";
let detailHost = null;
if (listHost.shadowRoot) {
  const details = listHost.shadowRoot.querySelector("div > div.list-mail-details");
  if (details) {
    const slot = details.querySelector("slot");
    if (slot && slot.assignedElements) {
      const assigned = slot.assignedElements();
      detailHost = assigned.find(
        el => el.tagName && el.tagName.toLowerCase() === "webmailer-mail-detail"
      );
    }
  }
}
if (!detailHost) {
  detailHost = listHost.querySelector("webmailer-mail-detail");
}
if (!detailHost || !detailHost.shadowRoot) return "";
const root = detailHost.shadowRoot.querySelector("div");
if (!root) return "";
const iframe =
  root.querySelector("iframe[name='detail-body-iframe']") ||
  root.querySelector("iframe");
if (!iframe) return "";
let doc = null;
try {
  doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
} catch (e) {
  return "";
}
if (!doc) return "";
const email = doc.querySelector("#email_content");
if (!email) return "";
const anchors = Array.from(email.querySelectorAll("a"));
const hints = arguments[0] || [];
for (const a of anchors) {
  const href = (a.getAttribute("href") || "").trim();
  const text = (a.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
  if (!href) continue;
  const hrefLow = href.toLowerCase();
  if (text === "reset your password") return href;
  if (text.includes("reset") && text.includes("password")) return href;
  if (hints.some(h => hrefLow.includes(h))) return href;
}
for (const a of anchors) {
  const href = (a.getAttribute("href") || "").trim();
  if (href) return href;
}
return "";
""",
            RESET_LINK_HREF_HINTS,
        )
        return _normalize_href(href)
    except Exception:
        return ""
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass


def _get_detail_body_iframe_element(driver):
    if not _switch_to_mail_frame(driver):
        return None
    try:
        return driver.execute_script(
            """
const listHost =
  document.querySelector("#list > mail-list-container") ||
  document.querySelector("mail-list-container");
if (!listHost) return null;
let detailHost = null;
if (listHost.shadowRoot) {
  const details = listHost.shadowRoot.querySelector("div > div.list-mail-details");
  if (details) {
    const slot = details.querySelector("slot");
    if (slot && slot.assignedElements) {
      const assigned = slot.assignedElements();
      detailHost = assigned.find(
        el => el.tagName && el.tagName.toLowerCase() === "webmailer-mail-detail"
      );
    }
  }
}
if (!detailHost) {
  detailHost = listHost.querySelector("webmailer-mail-detail");
}
if (!detailHost || !detailHost.shadowRoot) return null;
const root = detailHost.shadowRoot.querySelector("div");
if (!root) return null;
return (
  root.querySelector("iframe[name='detail-body-iframe']") ||
  root.querySelector("iframe")
);
"""
        )
    except Exception:
        return None


def _extract_reset_link_from_detail_iframe(driver):
    frame = _get_detail_body_iframe_element(driver)
    if not frame:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        return ""

    link = ""
    try:
        driver.switch_to.frame(frame)
        link = _extract_reset_link_from_email_content_dom(driver)
        if not link:
            try:
                body_html = driver.page_source
                link = _extract_reset_link_from_html(body_html)
            except Exception:
                pass
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
    return link


def _click_reset_in_detail_body_iframe(driver, timeout=15):
    frame = _get_detail_body_iframe_element(driver)
    if not frame:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        return False

    clicked = False
    try:
        driver.switch_to.frame(frame)
        end_time = time.time() + timeout
        while time.time() < end_time:
            if driver.find_elements(By.ID, "email_content"):
                break
            time.sleep(0.3)

        if _click_anchor_by_text_in_dom(driver, RESET_LINK_TEXT_EXACT):
            return True

        btn = _find_reset_button_in_dom(driver)
        if not btn:
            try:
                btn = driver.find_element(By.XPATH, RESET_LINK_TEXT_EXACT_XPATH)
            except Exception:
                btn = None

        if not btn:
            return False

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                btn,
            )
            time.sleep(0.3)
        except Exception:
            pass

        try:
            btn.click()
            clicked = True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
            except Exception:
                clicked = False
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
    return clicked


def _get_mail_content_fast(driver):
    if not _switch_to_mail_frame(driver):
        return "", ""
    text = ""
    html_src = ""
    try:
        result = driver.execute_script(MAIL_DETAIL_CONTENT_JS)
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            text = (result[0] or "").strip()
            html_src = result[1] or ""
    except Exception:
        pass
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
    return text, html_src


def _dump_mail_content(driver, max_chars=4000, pre_text="", pre_html=""):
    text = pre_text or ""
    html_src = pre_html or ""
    if not text and not html_src:
        text, html_src = _get_mail_content_fast(driver)
    if not text and not html_src:
        frame = _get_detail_body_iframe_element(driver)
        if frame:
            try:
                driver.switch_to.frame(frame)
                try:
                    email = driver.find_element(By.ID, "email_content")
                    text = email.text or ""
                    html_src = email.get_attribute("innerHTML") or ""
                except Exception:
                    try:
                        body = driver.find_element(By.TAG_NAME, "body")
                        text = body.text or ""
                        html_src = body.get_attribute("innerHTML") or ""
                    except Exception:
                        pass
            finally:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
    if not text and not html_src:
        try:
            email = driver.find_element(By.ID, "email_content")
            text = email.text or ""
            html_src = email.get_attribute("innerHTML") or ""
        except Exception:
            pass
    if not text and html_src:
        text = re.sub(r"<[^>]+>", " ", html_src)
        text = re.sub(r"\s+", " ", text).strip()

    if text:
        preview = text[:max_chars]
        print("----- [MAIL CONTENT TEXT] -----")
        print(preview)
        if len(text) > max_chars:
            print("----- [MAIL CONTENT TEXT TRUNCATED] -----")
    elif html_src:
        preview = html_src[:max_chars]
        print("----- [MAIL CONTENT HTML] -----")
        print(preview)
        if len(html_src) > max_chars:
            print("----- [MAIL CONTENT HTML TRUNCATED] -----")
    else:
        print("----- [MAIL CONTENT EMPTY] -----")


def _extract_reset_link_recursive(driver, depth=0, max_depth=4):
    if depth == 0:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        link = _extract_reset_link_shadow_detail(driver)
        if link:
            return link
        link = _extract_reset_link_from_detail_iframe(driver)
        if link:
            return link
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    link = _extract_reset_link_from_email_content_dom(driver)
    if link:
        return link
    try:
        btn = _find_reset_button_in_dom(driver)
    except Exception:
        btn = None
    if btn:
        try:
            href = _normalize_href(btn.get_attribute("href") or "")
        except Exception:
            href = ""
        if href:
            return href
    try:
        body_html = driver.find_element(By.TAG_NAME, "body").get_attribute("innerHTML")
        link = _extract_reset_link_from_html(body_html)
    except Exception:
        link = ""
    if link:
        return link

    if depth >= max_depth:
        return ""

    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            link = _extract_reset_link_recursive(driver, depth + 1, max_depth=max_depth)
            if link:
                driver.switch_to.parent_frame()
                return link
            driver.switch_to.parent_frame()
        except Exception:
            try:
                driver.switch_to.parent_frame()
            except Exception:
                pass
    return ""


def _find_reset_button_in_dom(driver):
    candidates = []
    for xpath in RESET_BUTTON_XPATHS:
        try:
            candidates = driver.find_elements(By.XPATH, xpath)
        except Exception:
            candidates = []
        if candidates:
            break
    if not candidates:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, RESET_LINK_COLOR_CSS)
        except Exception:
            candidates = []
    if not candidates:
        return None
    for btn in candidates:
        try:
            text = _normalize_anchor_text(btn.text or "")
            if text == RESET_LINK_TEXT_EXACT:
                return btn
            if "reset" in text:
                return btn
        except Exception:
            continue
    if len(candidates) >= 2:
        return candidates[1]
    return candidates[0]


def _click_anchor_by_text_in_dom(driver, target_text):
    if not target_text:
        return False
    target_norm = _normalize_anchor_text(target_text)
    try:
        anchors = driver.find_elements(By.TAG_NAME, "a")
    except Exception:
        return False
    for a in anchors:
        try:
            text = _normalize_anchor_text(a.text or "")
        except Exception:
            continue
        if text != target_norm:
            continue
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                a,
            )
            time.sleep(0.3)
        except Exception:
            pass
        try:
            a.click()
            return True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", a)
                return True
            except Exception:
                return False
    return False


def _click_reset_in_mail_content_recursive(driver, depth=0, max_depth=4):
    if depth == 0:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    if _click_reset_in_detail_current_frame(driver):
        return True

    for xpath in MAIL_DETAIL_RESET_XPATHS:
        if not xpath:
            continue
        try:
            target = driver.find_element(By.XPATH, xpath)
        except Exception:
            target = None
        if not target:
            continue
        clicked = False
        try:
            target.click()
            clicked = True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", target)
                clicked = True
            except Exception:
                pass
        if clicked:
            return True

    btn = _find_reset_button_in_dom(driver)
    if btn:
        clicked = False
        try:
            btn.click()
            clicked = True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
            except Exception:
                pass
        if clicked:
            return True

    if depth >= max_depth:
        return False

    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            if _click_reset_in_mail_content_recursive(
                driver, depth + 1, max_depth=max_depth
            ):
                driver.switch_to.parent_frame()
                return True
            driver.switch_to.parent_frame()
        except Exception:
            try:
                driver.switch_to.parent_frame()
            except Exception:
                pass
    return False


def wait_page_ready(driver, timeout=15):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass


def wait_mail_detail_loaded(driver, timeout=15):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if not _switch_to_mail_frame(driver):
            time.sleep(0.5)
            continue
        try:
            ready = driver.execute_script(
                """
const listHost = document.querySelector("#list > mail-list-container");
if (!listHost || !listHost.shadowRoot) return false;
const details = listHost.shadowRoot.querySelector("div > div.list-mail-details");
if (!details) return false;
const detailHost = details.querySelector("webmailer-mail-detail");
if (!detailHost || !detailHost.shadowRoot) return false;
const root = detailHost.shadowRoot.querySelector("div");
if (!root) return false;
if (root.querySelector("#email_content")) return true;
const iframe =
  root.querySelector("iframe[name='detail-body-iframe']") ||
  root.querySelector("iframe");
if (!iframe) return false;
try {
  const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
  if (!doc) return false;
  return !!doc.querySelector("#email_content");
} catch (e) {
  return false;
}
"""
            )
            if ready:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def wait_mail_list_loaded(driver, timeout=15):
    if not wait_mail_frame_ready(driver, timeout=min(8, timeout)):
        return False
    end_time = time.time() + timeout
    while time.time() < end_time:
        items = _get_mail_items_shadow(driver)
        if items:
            return True
        if _switch_to_mail_frame(driver):
            items = driver.find_elements(By.CSS_SELECTOR, "list-mail-item")
            if items:
                return True
        container = _find_mail_list_container(driver)
        if container:
            items = container.find_elements(By.CSS_SELECTOR, "list-mail-item")
            if items:
                return True
        time.sleep(0.5)
    return False


def find_elements_any_frame(driver, by, value):
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    return _find_elements_in_frames(driver, by, value)


def _safe_text(root, selector):
    try:
        return root.find_element(By.CSS_SELECTOR, selector).text.strip().lower()
    except Exception:
        return ""


def _is_unread(item):
    class_attr = (item.get_attribute("class") or "").lower()
    return "list-mail-item--unread" in class_attr


def _get_item_timestamp(item):
    selectors = [
        "list-date-label",
        "div.list-mail-item__date list-date-label",
        ".list-mail-item__date list-date-label",
    ]
    for sel in selectors:
        try:
            label = item.find_element(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        try:
            raw = label.get_attribute("date-in-ms") or label.get_attribute("dateInMs")
        except Exception:
            raw = ""
        try:
            return int(raw)
        except Exception:
            continue
    return 0


def _matches_reset(item):
    sender = _safe_text(item, "div.list-mail-item__sender-trusted-text")
    subject = _safe_text(item, "div.list-mail-item__subject")
    full_text = (sender + " " + subject).strip()
    if SENDER_NAME not in full_text:
        full_text = (item.text or "").lower()
        if SENDER_NAME not in full_text:
            return False
    keywords = [kw.lower() for kw in RESET_KEYWORDS]
    return any(kw in full_text for kw in keywords)


def _get_item_subject(item):
    for sel in [
        "div.list-mail-item__subject",
        "div.list-inbox-ad-item__subject",
        ".list-mail-item__subject",
        ".list-inbox-ad-item__subject",
    ]:
        try:
            text = item.find_element(By.CSS_SELECTOR, sel).text.strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def _extract_user_from_subject(text):
    subject = (text or "").strip()
    if not subject:
        return ""
    if "," in subject:
        subject = subject.split(",", 1)[0].strip()
    if " " in subject:
        subject = subject.split()[0].strip()
    return subject


def _extract_user_from_mail_text(text):
    if not text:
        return ""
    cleaned = text.strip()
    match = re.match(r"(?i)^hi\s+([^\s,]+)", cleaned)
    if match:
        return match.group(1).strip()
    match = re.search(r"(?i)\bhi\s+([^\s,]+)", cleaned)
    if match:
        return match.group(1).strip()
    return ""


def _extract_user_from_item(item):
    subject = _get_item_subject(item)
    user = _extract_user_from_subject(subject)
    if user:
        return user
    raw = (item.text or "").strip()
    if raw:
        first_line = raw.splitlines()[0].strip()
        return _extract_user_from_subject(first_line)
    return ""


def _find_mail_list_container(driver):
    if _switch_to_mail_frame(driver):
        try:
            container = driver.find_element(By.XPATH, MAIL_LIST_XPATH)
            if container:
                return container
        except Exception:
            pass
        try:
            container = driver.find_element(By.CSS_SELECTOR, "div.list-mail-list")
            if container:
                return container
        except Exception:
            pass
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    container = _find_element_in_frames(driver, By.XPATH, MAIL_LIST_XPATH)
    if container:
        return container
    container = _find_element_in_frames(driver, By.CSS_SELECTOR, "div.list-mail-list")
    return container


def scan_mail_items(driver):
    _switch_to_mail_frame(driver)
    items = _get_mail_items_shadow(driver)
    if items:
        print(f"   [Mail Scan] Found {len(items)} mail items via shadow DOM.")
        return items
    container = _find_mail_list_container(driver)
    if container:
        items = container.find_elements(By.CSS_SELECTOR, "list-mail-item")
        if items:
            print(f"   [Mail Scan] Found {len(items)} mail items in list container.")
            return items

    items = find_elements_any_frame(driver, By.TAG_NAME, "list-mail-item")
    if items:
        print(f"   [Mail Scan] Found {len(items)} mail items via frame scan.")
        return items
    return []


def _click_mail_item(driver, item):
    clicked = False
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", item
        )
        time.sleep(0.5)
    except Exception:
        pass

    target = item
    try:
        target = item.find_element(By.CSS_SELECTOR, "div.list-mail-item__lines-container")
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", target)
        clicked = True
    except Exception:
        try:
            target.click()
            clicked = True
        except Exception:
            pass
    return clicked


def execute_step2(driver, email="", password=""):
    print("--- [STEP 2] FIND MAIL AND CLICK RESET LINK ---")

    user_from_mail = ""
    subject_user = ""

    if IMAP_ONLY and not IMAP_ENABLED:
        print("?? IMAP-only mode but IMAP is disabled.")
        return False, user_from_mail

    if IMAP_ENABLED and email and password:
        print("-> IMAP: polling reset mail...")
        link, imap_text, imap_subject = _safe_call(
            "ImapResetLink", lambda: _imap_find_reset_link(email, password), ("", "", "")
        )
        if link:
            if imap_text:
                user_from_mail = _extract_user_from_mail_text(imap_text)
            if not user_from_mail and imap_subject:
                subject_user = _extract_user_from_subject(imap_subject)
                user_from_mail = subject_user
            print(f"? Reset link via IMAP: {link[:120]}...")
            new_handle = _open_reset_link_in_new_tab(driver, link, timeout=10)
            if not new_handle:
                _cache_reset_target(driver, url=link)
            return True, user_from_mail
        if IMAP_ONLY:
            print("? IMAP-only mode: reset link not found.")
            return False, user_from_mail
    elif IMAP_ENABLED and IMAP_ONLY:
        print("-> IMAP: skipped (missing credentials).")
        return False, user_from_mail
    elif IMAP_ENABLED:
        print("-> IMAP: skipped (missing credentials).")

    _safe_call("PageReady", lambda: wait_page_ready(driver, timeout=MAIL_WAIT_PAGE_TIMEOUT))
    _safe_call("MailFrameReady", lambda: wait_mail_frame_ready(driver, timeout=MAIL_WAIT_FRAME_TIMEOUT))
    _safe_call("MailListReady", lambda: wait_mail_list_loaded(driver, timeout=MAIL_WAIT_LIST_TIMEOUT))

    max_retries = MAIL_MAX_RETRIES
    mail_items = []
    target_mail = None

    try:
        for attempt in range(max_retries):
            print(f"-> [Attempt {attempt+1}/{max_retries}] Scanning mail list...")

            attempt_num = attempt + 1
            if attempt_num > 1 and (
                MAIL_REFRESH_EVERY <= 1 or attempt_num % MAIL_REFRESH_EVERY == 0
            ):
                print("   Refreshing page...")
                _safe_call("Refresh", driver.refresh)
                _safe_call(
                    "PageReady", lambda: wait_page_ready(driver, timeout=MAIL_WAIT_PAGE_TIMEOUT)
                )
                _safe_call(
                    "MailFrameReady",
                    lambda: wait_mail_frame_ready(driver, timeout=MAIL_WAIT_FRAME_TIMEOUT),
                )
                _safe_call(
                    "MailListReady",
                    lambda: wait_mail_list_loaded(driver, timeout=MAIL_WAIT_LIST_TIMEOUT),
                )

            target_mail = _safe_call(
                "FastFindMail", lambda: _poll_for_target_mail(driver), None
            )
            if target_mail:
                break

            mail_items = _safe_call("ScanMail", lambda: scan_mail_items(driver), [])
            if mail_items:
                break
            print("   No mail items yet, retry soon...")
            time.sleep(MAIL_RETRY_SLEEP)
    except Exception as exc:
        print(f"?? [Step2] Scan error: {exc}")

    if not target_mail and not mail_items:
        print("?? No mail list after retries.")
        return False, user_from_mail

    print(f"-> Filtering {len(mail_items)} mail items...")
    if target_mail:
        preview = _safe_call(
            "MailPreview", lambda: (target_mail.text or "")[:60], ""
        )
        unread = _safe_call("IsUnread", lambda: _is_unread(target_mail), False)
        state = "unread" if unread else "read"
        print(f"? Found target mail (fast {state}): {preview}...")
        subject_user = _safe_call(
            "SubjectUser", lambda: _extract_user_from_item(target_mail), ""
        )
    else:
        match_candidates = []
        for idx, item in enumerate(mail_items):
            match = _safe_call("FilterMail", lambda: _matches_reset(item), False)
            if not match:
                continue
            ts = _safe_call("MailTimestamp", lambda: _get_item_timestamp(item), 0)
            match_candidates.append((ts, idx, item))

        best_item = None
        best_ts = -1
        best_idx = 10**9
        for ts, idx, item in match_candidates:
            if ts > 0:
                if ts > best_ts or (ts == best_ts and idx < best_idx):
                    best_item = item
                    best_ts = ts
                    best_idx = idx
            elif best_ts <= 0 and idx < best_idx:
                best_item = item
                best_idx = idx

        if best_item:
            target_mail = best_item
            preview = _safe_call(
                "MailPreview", lambda: (target_mail.text or "")[:60], ""
            )
            print(f"? Found target mail (newest): {preview}...")
        if target_mail:
            subject_user = _safe_call(
                "SubjectUser", lambda: _extract_user_from_item(target_mail), ""
            )

    if not target_mail:
        print("? No Instagram reset mail found.")
        return False, user_from_mail

    print("-> Opening mail...")
    _safe_call("OpenMail", lambda: _click_mail_item(driver, target_mail), False)
    time.sleep(0.3)
    _safe_call(
        "MailDetailReady", lambda: wait_mail_detail_loaded(driver, timeout=MAIL_WAIT_DETAIL_TIMEOUT)
    )

    mail_text = ""
    mail_html = ""
    content = _safe_call("MailContentFast", lambda: _get_mail_content_fast(driver), ("", ""))
    if isinstance(content, (list, tuple)) and len(content) >= 2:
        mail_text = content[0] or ""
        mail_html = content[1] or ""

    user_from_mail = _safe_call("ExtractUser", lambda: _get_mail_detail_user(driver), "")
    if user_from_mail:
        print(f"-> Extracted IG user: {user_from_mail}")
    else:
        mail_user = _extract_user_from_mail_text(mail_text)
        if mail_user:
            user_from_mail = mail_user
            print(f"-> IG user from mail text: {user_from_mail}")
        elif subject_user:
            user_from_mail = subject_user
            print(f"-> IG user from subject: {user_from_mail}")
        else:
            print("-> IG user not found in mail detail.")

    if DEBUG_DUMP_MAIL:
        _safe_call(
            "DumpMailContent",
            lambda: _dump_mail_content(driver, pre_text=mail_text, pre_html=mail_html),
            None,
        )

    if not user_from_mail and subject_user:
        user_from_mail = subject_user
        print(f"-> IG user from subject: {user_from_mail}")

    print("-> Finding reset link...")
    mail_handle = driver.current_window_handle
    handles_before = set(driver.window_handles)
    if _safe_call(
        "ClickResetDetailIframe",
        lambda: _click_reset_in_detail_body_iframe(driver, timeout=15),
        False,
    ):
        new_handle = _wait_for_new_window(driver, handles_before, timeout=10)
        if new_handle:
            url = _get_window_url(driver, new_handle, timeout=5)
            if _is_reset_href(url):
                print(f"? Reset tab opened via detail-body-iframe: {url}")
                _cache_reset_target(driver, handle=new_handle, url=url)
                return True, user_from_mail
            print(f"? New tab opened but not reset url: {url or 'blank'}")
            reset_links_by_text = _safe_call(
                "FilterResetLinksByText",
                lambda: _collect_reset_links_by_text_in_detail_iframe(driver),
                [],
            )
            if reset_links_by_text:
                try:
                    driver.switch_to.window(new_handle)
                    driver.get(reset_links_by_text[0])
                    print("? Reset tab navigated from filtered anchors.")
                    _cache_reset_target(
                        driver, handle=new_handle, url=reset_links_by_text[0]
                    )
                    return True, user_from_mail
                except Exception:
                    pass
        else:
            try:
                driver.switch_to.window(mail_handle)
            except Exception:
                pass
    reset_links_by_text = _safe_call(
        "FilterResetLinksByText",
        lambda: _collect_reset_links_by_text_in_detail_iframe(driver),
        [],
    )
    if reset_links_by_text:
        print(
            f"? Reset links (text='{RESET_LINK_TEXT_EXACT}') found: "
            f"{reset_links_by_text[:2]}..."
        )
        new_handle = _open_reset_link_in_new_tab(
            driver, reset_links_by_text[0], timeout=10
        )
        if new_handle:
            print("? Reset tab opened from filtered anchors.")
            return True, user_from_mail
    reset_link = _safe_call(
        "ExtractResetLink", lambda: _extract_reset_link_recursive(driver), ""
    )
    if reset_link:
        print(f"? Reset link extracted: {reset_link[:120]}...")
        new_handle = _open_reset_link_in_new_tab(driver, reset_link, timeout=10)
        if new_handle:
            return True, user_from_mail
    if _safe_call(
        "ClickResetRecursive",
        lambda: _click_reset_in_mail_content_recursive(driver),
        False,
    ):
        new_handle = _wait_for_new_window(driver, handles_before, timeout=10)
        if new_handle:
            url = _get_window_url(driver, new_handle, timeout=5)
            if url:
                _cache_reset_target(driver, handle=new_handle, url=url)
            print("? Reset tab opened via recursive mail content search.")
            return True, user_from_mail
    if _safe_call(
        "ClickResetDeepXpath", lambda: _click_reset_deep_xpath_any_frame(driver), False
    ):
        new_handle = _wait_for_new_window(driver, handles_before, timeout=10)
        if new_handle:
            url = _get_window_url(driver, new_handle, timeout=5)
            if url:
                _cache_reset_target(driver, handle=new_handle, url=url)
            print("? Reset tab opened via deep xpath.")
            return True, user_from_mail

    reset_btn = _safe_call(
        "FindResetLink", lambda: wait_element_any_frame(driver, By.XPATH, RESET_LINK_XPATH, timeout=10)
    )
    if not reset_btn:
        links = _safe_call(
            "FindResetLinks",
            lambda: find_elements_any_frame(driver, By.CSS_SELECTOR, "#email_content a"),
            [],
        )
        for link in links:
            try:
                href = (link.get_attribute("href") or "").lower()
                if "reset" in href:
                    reset_btn = link
                    break
            except Exception:
                continue

    if reset_btn:
        print(f"? Click Reset Link: {reset_btn.text}")
        handles_before = set(driver.window_handles)
        try:
            reset_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", reset_btn)
        new_handle = _wait_for_new_window(driver, handles_before, timeout=10)
        if new_handle:
            url = _get_window_url(driver, new_handle, timeout=5)
            if url:
                _cache_reset_target(driver, handle=new_handle, url=url)
            return True, user_from_mail
        try:
            href = reset_btn.get_attribute("href") or ""
        except Exception:
            href = ""
        if href:
            new_handle = _open_reset_link_in_new_tab(driver, href, timeout=10)
            if new_handle:
                return True, user_from_mail

    print("? Reset link not found in mail content.")
    return False, user_from_mail


if __name__ == "__main__":
    from gmx_core import get_driver

    TEST_EMAIL = "revolverbanking4@gmx.de"
    TEST_PASS = "mlwhfov6Q"

    driver = get_driver(headless=False)
    try:
        ok, user = execute_step2(driver, email=TEST_EMAIL, password=TEST_PASS)
        print(f"Step2 result: {ok}, user={user}")
    except Exception as e:
        print(f"Main Error: {e}")
        time.sleep(60)
