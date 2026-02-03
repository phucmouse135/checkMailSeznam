import json
import os
import time
from dataclasses import dataclass

from gmx_core import get_driver
from step2_get_link import execute_step2
from step3_reset_password import execute_step3
from step4_verify import execute_step4

# --- CONFIG FILES ---
INPUT_FILE = "input.txt"
OUTPUT_FILE = "output.txt"
IG_COOKIE_PATH = r"new_Ig.json"


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
    Run steps for one account line.
    Input: raw line
    Output: (success, message, ig_user)
    """
    line = line.strip()
    if not line:
        return False, "Empty Line", ""

    parts = line.split("\t")
    if len(parts) < 2:
        parts = line.split()

    if len(parts) < 7:
        return False, "Data Error: missing columns", ""

    uid = parts[0]
    email = parts[5].strip()
    password = parts[6].strip()
    current_user = parts[2] if len(parts) > 2 else ""

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

    def _step2_call():
        _clear_reset_cache(driver)
        return execute_step2(driver, email=email, password=password)

    ok, step2_result, err = _retry_step(
        "Step 2 Read mail",
        _step2_call,
        retries=3,
        delay=4,
        success_check=lambda r: isinstance(r, tuple) and r[0],
    )
    if ok and step2_result:
        step2_ok, ig_user = step2_result
    else:
        step2_ok, ig_user = False, current_user
    if ig_user:
        parts[2] = ig_user
        line = "\t".join(parts)
    if not step2_ok:
        return False, f"Step 2 Fail: {err or 'Mail or link not found'}", ig_user

    ok, _, err = _retry_step(
        "Step 3 Reset password",
        lambda: execute_step3(driver, line),
        retries=3,
        delay=4,
        success_check=lambda r: r is True,
    )
    if not ok:
        return False, f"Step 3 Fail: {err or 'Reset submit failed'}", ig_user

    ok, _, err = _retry_step(
        "Step 4 Verify mail",
        lambda: execute_step4(driver, email=email, password=password, ig_user=ig_user),
        retries=3,
        delay=4,
        success_check=lambda r: r is True,
    )
    if not ok:
        return False, f"Step 4 Fail: {err or 'Confirm mail not found'}", ig_user

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

def process_account(account, headless=False, status_cb=None):
    driver = get_driver(headless=headless)
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
            status_cb("Step2: read mail (IMAP)")
        ok, step2_result, err = _retry_step(
            "Step 2 Read mail",
            lambda: (
                _clear_reset_cache(driver)
                or execute_step2(driver, email=account.mail_login, password=account.mail_pass)
            ),
            retries=3,
            delay=2,
            success_check=lambda r: isinstance(r, tuple) and r[0],
        )
        if ok and step2_result:
            step2_ok, ig_user = step2_result
        else:
            step2_ok, ig_user = False, account.ig_user
        if ig_user:
            account.ig_user = ig_user
            if status_cb:
                status_cb(f"USER={ig_user}")
        if not step2_ok:
            raise RuntimeError(f"Reset mail or link not found: {err}")

        if status_cb:
            status_cb("Step3: reset password")
        line = _build_line_from_account(account)
        ok, _, err = _retry_step(
            "Step 3 Reset password",
            lambda: execute_step3(driver, line),
            retries=3,
            delay=3,
            success_check=lambda r: r is True,
        )
        if not ok:
            raise RuntimeError(f"Reset password submit failed: {err}")

        if status_cb:
            status_cb("Step4: verify mail (IMAP)")
        ok, _, err = _retry_step(
            "Step 4 Verify mail",
            lambda: execute_step4(
                driver, email=account.mail_login, password=account.mail_pass
            ),
            retries=3,
            delay=4,
            success_check=lambda r: r is True,
        )
        if not ok:
            raise RuntimeError(f"Confirm mail not found: {err}")

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
            email = parts[5] if len(parts) > 5 else "Unknown"
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
