import json
import os
import time
from dataclasses import dataclass

from gmx_core import get_driver
from step3_reset_password import execute_step3
import mail_handler

# --- CONFIG FILES ---
INPUT_FILE = "input.txt"
OUTPUT_FILE = "output.txt"
IG_COOKIE_PATH = r"new_Ig.json"  # Đường dẫn đến file cookie Instagram (định dạng JSON)


@dataclass
class Account:
    uid: str
    mail_login: str
    ig_user: str
    mail_pass: str


def append_log(filepath, content):
    """Append result to output file."""
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(content + "\n")


def _clear_reset_cache(driver):
    try:
        driver.reset_handle = ""
        driver.reset_url = ""
    except Exception:
        pass


def _retry_call(label, func, retries=3, delay=2, fatal_exceptions=()):
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            func()
            return True, ""
        except Exception as exc:
            if fatal_exceptions and isinstance(exc, fatal_exceptions):
                return False, str(exc)
            last_err = str(exc)
            print(f"? {label} failed ({attempt}/{retries}): {last_err}")
            if attempt < retries:
                time.sleep(delay)
    return False, last_err


def _retry_step(label, func, retries=3, delay=2, success_check=None):
    last_err = ""
    result = None
    for attempt in range(1, retries + 1):
        try:
            result = func()
            ok = success_check(result) if success_check else bool(result)
            if ok:
                return True, result, ""
            last_err = f"{label} returned falsy"
        except Exception as exc:
            last_err = str(exc)
        print(f"? {label} failed ({attempt}/{retries}): {last_err}")
        if attempt < retries:
            time.sleep(delay)
    return False, result, last_err


def load_instagram_cookies(driver, cookie_path):
    if not os.path.exists(cookie_path):
        raise FileNotFoundError(f"Cookie file not found: {cookie_path}")

    with open(cookie_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    url = data.get("url") or "https://www.instagram.com/"
    driver.get(url)
    time.sleep(2)

    cookies = data.get("cookies", [])
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        payload = {
            "name": name,
            "value": value,
            "domain": cookie.get("domain"),
            "path": cookie.get("path", "/"),
            "secure": cookie.get("secure", False),
            "httpOnly": cookie.get("httpOnly", False),
        }
        if "expirationDate" in cookie:
            try:
                payload["expiry"] = int(cookie["expirationDate"])
            except Exception:
                pass
        payload = {k: v for k, v in payload.items() if v is not None}
        try:
            driver.add_cookie(payload)
        except Exception:
            try:
                payload.pop("domain", None)
                driver.add_cookie(payload)
            except Exception:
                pass

    driver.get(url)
    time.sleep(3)


def process_line(driver, line):
    """
    Run steps for one account line using mail_handler for all mail actions.
    Input: raw line
    Output: (success, message, ig_user)
    """
    line = line.strip()
    if not line:
        return False, "Empty Line", ""

    parts = line.split("\t")
    if len(parts) < 2:
        parts = line.split()

    if len(parts) < 5:
        return False, "Data Error: missing columns", ""

    ig_user = parts[0].strip()
    mail_login = parts[3].strip()
    mail_pass = parts[4].strip()
    current_user = ig_user

    uid = ig_user
    email = mail_login
    password = mail_pass

    print(f"\n? Processing: {uid} | {email}")

    ok, err = _retry_call(
        "Load cookies",
        lambda: load_instagram_cookies(driver, IG_COOKIE_PATH),
        retries=3,
        delay=2,
        fatal_exceptions=(FileNotFoundError,),
    )
    if not ok:
        return False, f"Cookie load failed: {err}", current_user
    _clear_reset_cache(driver)

    # Step 1: Get reset link from mail_handler
    getlink_result = mail_handler.verify_account_live(email, password)
    if not (isinstance(getlink_result, str) and getlink_result.startswith("success")):
        return False, f"Get link fail: {getlink_result}", current_user

    # Parse IG user and link from result
    ig_user = current_user
    link = ""
    for part in getlink_result.split("|"):
        if part.startswith("USER="):
            ig_user = part.split("=", 1)[1]
        if part.startswith("LINK="):
            link = part.split("=", 1)[1]

    if not link:
        return False, "No reset link found in mail", ig_user

    # Step 2: Open link and reset password
    driver.reset_url = link  # Cache the reset URL
    ok, _, err = _retry_step(
        "Step 3 Reset password",
        lambda: execute_step3(driver, link, password),
        retries=3,
        delay=4,
        success_check=lambda r: r is True,
    )
    if not ok:
        return False, f"Step 3 Fail: {err or 'Reset submit failed'}", ig_user

    # Step 3: Verify password changed via mail_handler
    ok = mail_handler.verify_password_changed(email, password, ig_user=ig_user)
    if ok:
        print("?? Verify password changed: OK")
    if not ok:
        return False, "Step 4 Fail: Confirm mail not found", ig_user

    return True, "SUCCESS", ig_user


def _build_line_from_account(account):
    parts = [
        account.uid,
        "",
        account.ig_user or "",
        "",
        "",
        account.mail_login,
        account.mail_pass,
        "",
    ]
    return "\t".join(parts)
def append_log(filepath, content):
    """Ghi log và ép hệ điều hành lưu ngay lập tức xuống ổ cứng."""
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(content + "\n")
            f.flush()      # Đẩy từ bộ đệm Python xuống bộ đệm OS
            os.fsync(f.fileno()) # Đẩy từ bộ đệm OS xuống đĩa cứng vật lý (Quan trọng)
    except Exception as e:
        print(f"[LOG ERROR] Không thể ghi file: {e}")

def process_account(account, headless=False, status_cb=None, thread_id=0, max_threads=6):
    driver = get_driver(headless=headless, thread_id=thread_id, max_threads=max_threads)
    try:
        if status_cb:
            status_cb("Step1: open Instagram")
        ok, err = _retry_call(
            "Load cookies",
            lambda: load_instagram_cookies(driver, IG_COOKIE_PATH),
            retries=3,
            delay=2,
            fatal_exceptions=(FileNotFoundError,),
        )
        if not ok:
            raise RuntimeError(f"Cookie load failed: {err}")
        _clear_reset_cache(driver)

        if status_cb:
            status_cb("Step2: get reset link (IMAP)")
        getlink_result = mail_handler.verify_account_live(account.mail_login, account.mail_pass)
        if not (isinstance(getlink_result, str) and getlink_result.startswith("success")):
            raise RuntimeError(f"Get link fail: {getlink_result}")

        ig_user = account.ig_user
        link = ""
        for part in getlink_result.split("|"):
            if part.startswith("USER="):
                ig_user = part.split("=", 1)[1]
            if part.startswith("LINK="):
                link = part.split("=", 1)[1]
        if ig_user:
            account.ig_user = ig_user
            if status_cb:
                status_cb(f"USER={ig_user}")
        if not link:
            raise RuntimeError("No reset link found in mail")

        if status_cb:
            status_cb("Step3: reset password")
        driver.reset_url = link  # Cache the reset URL
        ok, _, err = _retry_step(
            "Step 3 Reset password",
            lambda: execute_step3(driver, link, account.mail_pass),
            retries=3,
            delay=3,
            success_check=lambda r: r is True,
        )
        if not ok:
            raise RuntimeError(f"Reset password submit failed: {err}")

        if status_cb:
            status_cb("Step4: verify mail (IMAP)")
        ok = mail_handler.verify_password_changed(account.mail_login, account.mail_pass, ig_user=ig_user)
        if ok:
            if status_cb:
                status_cb("Verify password changed: OK")
        if not ok:
            raise RuntimeError("Confirm mail not found")

        return "success"
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"? Error: Input file not found: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if lines and "UID" in lines[0]:
        lines = lines[1:]

    print(f"--- RUN BULK: {len(lines)} ACCOUNTS ---")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("UID\tEMAIL\tUSER\tSTATUS\tMESSAGE\n")

    driver = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            if driver is None:
                driver = get_driver(headless=False)
            else:
                driver.delete_all_cookies()
        except Exception:
            driver = get_driver(headless=False)

        try:
            success, msg, ig_user = process_line(driver, line)

            status = "SUCCESS" if success else "FAIL"
            print(f"?? Result: {status} - {msg}")

            parts = line.split("\t") if "\t" in line else line.split()
            uid = parts[0] if parts else "Unknown"
            email = parts[3] if len(parts) > 3 else "Unknown"
            
            # Ghi vào file tương ứng
            result_file = "success.txt" if success else "fail.txt"
            with open(result_file, "a", encoding="utf-8") as f:
                f.write(f"{uid}\t{email}\t{ig_user}\t{status}\t{msg}\n")
            
            append_log(OUTPUT_FILE, f"{uid}\t{email}\t{ig_user}\t{status}\t{msg}")
        except Exception as e:
            print(f"? Fatal error: {e}")
            append_log(OUTPUT_FILE, f"{line[:20]}...\tUnknown\t\tCRASH\t{str(e)}")
            try:
                driver.quit()
            except Exception:
                pass
            driver = None

        print("? Sleep 3s before next account...")
        time.sleep(3)

    if driver:
        driver.quit()
    print("\n--- DONE ---")


if __name__ == "__main__":
    main()
