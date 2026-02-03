# FILE: step1_login.py
import time
from selenium.webdriver.common.by import By
# Import các hàm từ gmx_core mới
from gmx_core import get_driver, find_element_safe, reload_if_ad_popup

# --- DATA TEST DEFAULT ---
DEF_USER = "saucycut1@gmx.de"
DEF_PASS = "muledok5P"

def login_process(driver, user, password):
    """
    Standard Login Function (Full Logic).
    Returns True if login success, False if failed.
    """
    try:
        print(f"--- START LOGIN PROCESS: {user} ---")
        
        # 1. Enter site
        driver.get("https://www.gmx.net/")
        time.sleep(2)
        
        # Reload nhẹ để đảm bảo tải hết resource (giữ logic cũ)
        if driver.current_url == "about:blank":
             driver.get("https://www.gmx.net/")

        # --- CÁC HÀM HỖ TRỢ NỘI BỘ (GIỮ NGUYÊN LOGIC GỐC) ---
        def abort_if_ad_popup():
            if reload_if_ad_popup(driver):
                print("?? Ad popup detected. Reloaded to GMX home.")
                return True
            return False

        def reload_if_no_password_prompt():
            """Xử lý trường hợp GMX hiện màn hình 'Không phải email của bạn?'"""
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            try:
                elems = driver.find_elements(
                    By.XPATH,
                    "//*[contains(normalize-space(.), 'Doch nicht Ihre E-Mail?')]",
                )
                if elems:
                    driver.get("https://www.gmx.net/")
                    time.sleep(2)
                    return True
            except Exception:
                pass
            return False

        def wait_page_ready(timeout=6):
            end_time = time.time() + timeout
            while time.time() < end_time:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
                try:
                    state = driver.execute_script("return document.readyState")
                except Exception:
                    state = ""
                if state == "complete":
                    return True
                time.sleep(0.2)
            return False

        # --- LOGIC QUÉT ELEMENT TRONG IFRAME (QUAN TRỌNG) ---
        user_selectors = [
            (By.CSS_SELECTOR, "input[data-testid='input-email']"),
            (By.NAME, "username"),
            (By.ID, "username"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.XPATH, "//input[@autocomplete='username']")
        ]

        button_selectors = [
            (By.CSS_SELECTOR, "button[data-testid='login-submit']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.ID, "login-submit")
        ]

        password_selectors = [
            (By.CSS_SELECTOR, "input[data-testid='input-password']"),
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.XPATH, "//input[@type='password']")
        ]

        fast_scan_interval = 0.2

        def fast_find_any(selectors):
            for by_f, val_f in selectors:
                try:
                    elements = driver.find_elements(by_f, val_f)
                    # Chỉ lấy element hiển thị được
                    visible_elems = [e for e in elements if e.is_displayed()]
                    if visible_elems:
                        return visible_elems[0], (by_f, val_f)
                    if elements: # Fallback nếu chưa kịp hiển thị
                        return elements[0], (by_f, val_f)
                except Exception:
                    continue
            return None, None

        def fast_locate_in_frames(selectors, timeout=6, prefer_iframe_index=None):
            """Hàm quét toàn bộ Iframes để tìm element - Logic cốt lõi của GMX Login"""
            end_time = time.time() + timeout
            while time.time() < end_time:
                if abort_if_ad_popup():
                    return None, None

                # 1. Check iframe ưu tiên trước (nếu đã tìm thấy ở bước trước)
                if prefer_iframe_index is not None:
                    try:
                        driver.switch_to.default_content()
                        iframes = driver.find_elements(By.TAG_NAME, "iframe")
                        if prefer_iframe_index < len(iframes):
                            driver.switch_to.frame(iframes[prefer_iframe_index])
                            element, _ = fast_find_any(selectors)
                            if element:
                                return prefer_iframe_index, element
                    except Exception:
                        pass

                # 2. Check Main Content
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
                element, _ = fast_find_any(selectors)
                if element:
                    return None, element

                # 3. Scan toàn bộ iframe
                try:
                    iframes = driver.find_elements(By.TAG_NAME, "iframe")
                except Exception:
                    iframes = []

                for idx, iframe in enumerate(iframes):
                    try:
                        driver.switch_to.default_content()
                        driver.switch_to.frame(iframe)
                        element, _ = fast_find_any(selectors)
                        if element:
                            return idx, element
                    except Exception:
                        continue

                time.sleep(fast_scan_interval)

            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            return None, None

        def click_element(element):
            try:
                element.click()
                return True
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    return False

        def type_into_element(element, text):
            try:
                element.clear()
            except Exception:
                pass
            try:
                element.send_keys(text)
                return True
            except Exception:
                try:
                    # Fallback JS nhập liệu nếu send_keys lỗi
                    driver.execute_script("arguments[0].value = arguments[1];", element, text)
                    driver.execute_script(
                        "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
                        element
                    )
                    return True
                except Exception:
                    return False

        # --- BẮT ĐẦU QUY TRÌNH LOGIN ---

        if abort_if_ad_popup():
            return False
        
        # 2. Handle Consent
        # print("-> Check Consent...")
        find_element_safe(driver, By.ID, "onetrust-accept-btn-handler", timeout=5, click=True)
        if abort_if_ad_popup():
            return False

        # 3. FIND USER INPUT
        # print("-> Scanning for Login Form (Main or Iframe)...")
        
        # Vòng lặp retry nhập password (Logic quan trọng giữ lại)
        max_password_retries = 3
        password_input = None
        
        for attempt in range(max_password_retries):
            if attempt > 0:
                print(f"-> Retry login process ({attempt + 1}/{max_password_retries})...")

            # Tìm ô nhập User
            current_iframe_index, user_input = fast_locate_in_frames(user_selectors, timeout=8)
            
            if abort_if_ad_popup(): return False
            
            if user_input:
                location = "Main Content" if current_iframe_index is None else f"Iframe #{current_iframe_index + 1}"
                # print(f"   Found Login Input in {location}")
            else:
                print("? Login input not found in main/iframes.")
                return False

            # 5. ENTER USERNAME
            # print("-> Entering Username...")
            if abort_if_ad_popup(): return False
            
            filled = type_into_element(user_input, user)
            if not filled:
                # Retry nhập bằng find_element_safe nếu hàm trên fail
                for by_u, val_u in user_selectors:
                    if find_element_safe(driver, by_u, val_u, send_keys=user):
                        filled = True
                        break

            if not filled:
                print("? Cannot enter Username.")
                return False

            # print(f"   Entered: {user}")

            # 6. CLICK NEXT/WEITER
            # print("-> Clicking Next/Weiter...")
            if abort_if_ad_popup(): return False
            
            # Tìm nút Next (ưu tiên tìm trong cùng iframe với user input)
            current_iframe_index, next_button = fast_locate_in_frames(
                button_selectors,
                timeout=4,
                prefer_iframe_index=current_iframe_index,
            )
            
            if not next_button or not click_element(next_button):
                # Fallback tìm nút bằng các selector cơ bản
                if not find_element_safe(driver, By.CSS_SELECTOR, "button[data-testid='login-submit']", click=True):
                    if not find_element_safe(driver, By.CSS_SELECTOR, "button[type='submit']", click=True):
                         print("? Next button not found.")

            wait_page_ready(timeout=6)

            # 7. WAIT FOR PASSWORD INPUT
            if abort_if_ad_popup(): return False
            
            # Tìm ô Password (ưu tiên iframe cũ)
            current_iframe_index, password_input = fast_locate_in_frames(
                password_selectors,
                timeout=8, # Tăng timeout chờ animation
                prefer_iframe_index=current_iframe_index,
            )
            
            if password_input:
                break # Đã tìm thấy password, thoát vòng lặp retry

            # Xử lý lỗi GMX đặc thù nếu không thấy ô pass
            if reload_if_no_password_prompt():
                print("?? Reloading due to 'Doch nicht Ihre E-Mail?'.")
            else:
                print("?? Missing password field; reloading GMX to retry.")
                driver.get("https://www.gmx.net/")
                time.sleep(2)
            
            # Chấp nhận lại cookie nếu reload
            find_element_safe(driver, By.ID, "onetrust-accept-btn-handler", timeout=3, click=True)
            if abort_if_ad_popup(): return False

        if not password_input:
            print("? Password input not found after retries.")
            return False

        # 7. ENTER PASSWORD
        # print("-> Entering Password...")
        if abort_if_ad_popup(): return False
        
        if not password_input or not type_into_element(password_input, password):
            # Fallback nhập pass
            if not find_element_safe(driver, By.CSS_SELECTOR, "input[data-testid='input-password']", timeout=5, send_keys=password):
                 print("? Password input error.")
                 return False
        # print("   Password entered.")

        # 8. CLICK LOGIN FINAL
        if abort_if_ad_popup(): return False
        
        current_iframe_index, login_button = fast_locate_in_frames(
            button_selectors,
            timeout=4,
            prefer_iframe_index=current_iframe_index
        )
        if not login_button or not click_element(login_button):
             find_element_safe(driver, By.CSS_SELECTOR, "button[type='submit']", click=True)
        # print("-> Clicked Login.")

        # 9. CHECK RESULT
        driver.switch_to.default_content()
        # print("-> Waiting for redirection...")
        
        # Logic check login thành công
        end_wait = time.time() + 20
        while time.time() < end_wait:
            curr = driver.current_url
            if "navigator" in curr or "mail.com/mail" in curr:
                print(f"✅ [PASS] Login Success: {user}")
                return True
            if "error" in curr or "login_failed" in driver.page_source:
                print("❌ [FAIL] Login Failed (Wrong Pass/Block)")
                return False
            time.sleep(0.5)
            
        print("❌ [FAIL] Timeout: Did not reach navigator page.")
        return False

    except Exception as e:
        print(f"❌ [FAIL] Login Error: {e}")
        return False

# Test run if file executed directly
if __name__ == "__main__":
    driver = get_driver(headless=False)
    try:
        login_process(driver, DEF_USER, DEF_PASS)
    finally:
        driver.quit()