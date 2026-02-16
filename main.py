import json
import os
import time
from dataclasses import dataclass

from gmx_core import get_driver, is_driver_alive
from step3_reset_password import execute_step3, DriverConnectionError
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


def _safe_driver_operation(driver, operation_func, operation_name="operation"):
    """Execute driver operation with automatic recovery on connection errors"""
    try:
        return operation_func()
    except Exception as exc:
        error_str = str(exc).lower()
        is_connection_error = (
            "connection" in error_str or 
            "newconnectionerror" in error_str or 
            "max retries exceeded" in error_str or
            "target machine actively refused" in error_str
        )
        
        if is_connection_error:
            print(f"? Connection error in {operation_name}, attempting recovery...")
            # This will be caught by the caller and driver will be recreated
            raise exc
        else:
            raise exc


def _recreate_driver_if_needed(driver_ref, headless=False):
    """Recreate driver if connection is lost. driver_ref is a list containing [driver]"""
    try:
        if not driver_ref[0] or not is_driver_alive(driver_ref[0]):
            print("? Driver connection lost, recreating...")
            if driver_ref[0]:
                try:
                    driver_ref[0].quit()
                except Exception:
                    pass
            driver_ref[0] = get_driver(headless=headless)
            return True
    except Exception as e:
        print(f"? Error checking driver health: {e}")
        try:
            driver_ref[0] = get_driver(headless=headless)
            return True
        except Exception:
            pass
    return False


def load_instagram_cookies(driver, cookie_path):
    # Check driver connection first
    if not is_driver_alive(driver):
        raise RuntimeError("Driver connection lost before loading cookies")
        
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


def _retry_call(label, func, retries=3, delay=2, fatal_exceptions=(), driver_ref=None, headless=False):
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            func()
            return True, ""
        except Exception as exc:
            error_str = str(exc).lower()
            # Check for connection errors
            is_connection_error = (
                "connection" in error_str or 
                "newconnectionerror" in error_str or 
                "max retries exceeded" in error_str or
                "target machine actively refused" in error_str
            )
            
            if fatal_exceptions and isinstance(exc, fatal_exceptions):
                return False, str(exc)
            
            last_err = str(exc)
            
            if is_connection_error:
                print(f"? Connection error detected in {label} ({attempt}/{retries})")
                if driver_ref and attempt < retries:
                    # Try to recreate driver
                    print(f"? Attempting to recreate driver for {label}...")
                    try:
                        _recreate_driver_if_needed(driver_ref, headless=headless)
                        time.sleep(delay)
                        continue
                    except Exception as recreate_err:
                        print(f"? Failed to recreate driver: {recreate_err}")
                        return False, f"Connection lost and recovery failed: {last_err}"
                else:
                    # No driver_ref or last attempt, raise connection error
                    raise DriverConnectionError(f"Driver connection lost: {last_err}")
            
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
        except DriverConnectionError:
            # Re-raise connection errors immediately so the caller can recreate the driver
            raise
        except Exception as exc:
            # Convert critical connection errors to DriverConnectionError
            error_str = str(exc).lower()
            if "connection" in error_str or "reset" in error_str or "aborted" in error_str:
                raise DriverConnectionError(f"Driver connection lost: {exc}")
            last_err = str(exc)
        print(f"? {label} failed ({attempt}/{retries}): {last_err}")
        if attempt < retries:
            time.sleep(delay)
    return False, result, last_err


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
    max_retries = 3
    last_exception = None
    
    for attempt in range(max_retries):
        driver = None
        # Exponential backoff for retries
        if attempt > 0:
            retry_wait = 3 * attempt
            if status_cb:
                status_cb(f"Waiting {retry_wait}s before retry {attempt+1}...")
            time.sleep(retry_wait)
            
        try:
            driver = get_driver(headless=headless, thread_id=thread_id, max_threads=max_threads)
            
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
                # If caused by connection error that bubbled up as string (legacy), check err string?
                # But we modified _retry_step to raise DriverConnectionError. 
                # So if we are here, it's a regular failure (ok=False) or RuntimeError.
                # If step3 returned False (logic error), err is set.
                raise RuntimeError(f"Reset password submit failed: {err}")

            if status_cb:
                status_cb("Step4: verify mail (IMAP)")
            ok = mail_handler.verify_password_changed(account.mail_login, account.mail_pass, ig_user=ig_user)
            if ok:
                if status_cb:
                    status_cb("Verify password changed: OK")
            if not ok:
                raise RuntimeError("Confirm mail not found")

            # Success!
            return "success"

        except DriverConnectionError as e:
            print(f"? Driver connection lost during account processing (attempt {attempt+1}): {e}")
            if status_cb:
                status_cb(f"Connection lost, retrying... ({attempt+1})")
            last_exception = e
            # Loop will continue and create new driver
            
        except Exception as e:
            # Check if execution failed due to connection error masquerading as other error?
            msg = str(e).lower()
            if "connection" in msg or "driver" in msg and "lost" in msg:
                 print(f"? Connection error detected as Exception: {e}")
                 if status_cb:
                    status_cb(f"Connection error, retrying... ({attempt+1})")
                 last_exception = e
                 continue
            raise  # Re-raise other errors
            
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # If we exhausted retries
    if last_exception:
        raise last_exception
    raise RuntimeError("Process failed after retries")


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
    success_count = 0
    fail_count = 0
    processed_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check driver health before processing
        if driver and not is_driver_alive(driver):
            print("? Driver connection lost, recreating...")
            try:
                driver.quit()
            except Exception:
                pass
            driver = None

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
            
            # Cập nhật counter
            processed_count += 1
            if success:
                success_count += 1
            else:
                fail_count += 1
            
            # Hiển thị progress
            print(f"?? Progress: {processed_count}/{len(lines)} - Success: {success_count}, Fail: {fail_count}")
            
            # Ghi vào file tương ứng
            result_file = "success.txt" if success else "fail.txt"
            
            # Ghi toàn bộ dòng gốc + status + msg
            clean_line = line.strip()
            with open(result_file, "a", encoding="utf-8") as f:
                f.write(f"{clean_line}\t{status}\t{msg}\n")
            
            append_log(OUTPUT_FILE, f"{clean_line}\t{status}\t{msg}")
        except DriverConnectionError as e:
            print(f"? Driver connection lost during processing: {e}")
            processed_count += 1
            fail_count += 1
            print(f"?? Progress: {processed_count}/{len(lines)} - Success: {success_count}, Fail: {fail_count}")
            append_log(OUTPUT_FILE, f"{line[:20]}...\tUnknown\t\tCONNECTION_LOST\t{str(e)}")
            # Don't quit driver here, it might be already dead
            driver = None
        except Exception as e:
            error_str = str(e).lower()
            # Check if this is a connection error that should trigger driver recreation
            is_connection_error = (
                "connection" in error_str or 
                "newconnectionerror" in error_str or 
                "max retries exceeded" in error_str or
                "target machine actively refused" in error_str or
                "driver connection lost" in error_str
            )
            
            if is_connection_error:
                print(f"? Connection error detected, recreating driver: {e}")
                processed_count += 1
                fail_count += 1
                print(f"?? Progress: {processed_count}/{len(lines)} - Success: {success_count}, Fail: {fail_count}")
                append_log(OUTPUT_FILE, f"{line[:20]}...\tUnknown\t\tCONNECTION_LOST\t{str(e)}")
                driver = None  # Force recreation
            else:
                print(f"? Fatal error: {e}")
                processed_count += 1
                fail_count += 1
                print(f"?? Progress: {processed_count}/{len(lines)} - Success: {success_count}, Fail: {fail_count}")
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
    print(f"\n--- DONE --- Total: {processed_count}, Success: {success_count}, Fail: {fail_count} ---")


if __name__ == "__main__":
    main()
