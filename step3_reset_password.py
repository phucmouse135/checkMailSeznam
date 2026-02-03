import time
from urllib.parse import parse_qs, unquote, urlparse
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# --- CONFIG ---
PASSWORD_XPATH = (
    "/html/body/div[1]/div/div[1]/div[2]/div/div/div[1]/div[1]/div/div/div/"
    "div[1]/div[1]/div/div/div/div/div/div[1]/div[2]/form/div/div/div[4]/"
    "div/div/div[1]/input"
)
RESET_URL_HINTS = [
    "instagram.com/accounts/password/reset/confirm",
    "instagram.com/accounts/password/reset",
    "password/reset/confirm",
    "one_click_login_email",
    "deref-gmx.net/mail/client",
    "redirecturl=",
]
SUBMIT_KEYWORDS = [
    "reset", "continue", "submit", "save", "change password", "change", "next"
]
SUBMIT_NEGATIVE_KEYWORDS = ["cancel", "back"]
WAIT_AFTER_SUBMIT_SECONDS = 7

# Các dấu hiệu nhận biết link lỗi (Đã bỏ từ khóa 'error' chung chung để tránh nhận diện nhầm)
EXPIRED_LINK_MARKERS = [
    "page isn't available", "page isnt available", "this page isn't available",
    "sorry, this page isn't available", "the link may be broken",
    "link may be broken", "link has expired", "link is invalid", "invalid link",
    "something went wrong", "there's an issue and the page could not be loaded", 
    "sorry, something went wrong", "hãy thử lại", "đã xảy ra lỗi"
]

class ResetLinkExpiredError(RuntimeError):
    pass

# --- UTILS ---

def _find_element_in_frames(driver, by, value, depth=0, max_depth=3):
    try: return driver.find_element(by, value)
    except: pass
    if depth >= max_depth: return None
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            found = _find_element_in_frames(driver, by, value, depth + 1, max_depth)
            if found: return found
            driver.switch_to.parent_frame()
        except:
            try: driver.switch_to.parent_frame()
            except: pass
    return None

def _find_elements_in_frames(driver, by, value, depth=0, max_depth=3):
    try:
        elements = driver.find_elements(by, value)
        if elements: return elements
    except: pass
    if depth >= max_depth: return []
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            elements = _find_elements_in_frames(driver, by, value, depth + 1, max_depth)
            if elements: return elements
            driver.switch_to.parent_frame()
        except:
            try: driver.switch_to.parent_frame()
            except: pass
    return []

def wait_element_any_frame(driver, by, value, timeout=10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try: driver.switch_to.default_content()
        except: pass
        el = _find_element_in_frames(driver, by, value)
        if el:
            try:
                if el.is_displayed(): return el
            except: return el
        time.sleep(0.5)
    return None

def _wait_for_url(driver, timeout=10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            url = driver.current_url or ""
            if url and url != "about:blank": return url
        except: pass
        time.sleep(0.3)
    return ""

def _check_if_page_broken(driver):
    """Kiểm tra xem trang có bị lỗi 'Something went wrong' hay không"""
    try:
        # Check title và body text hiển thị (innerText) thay vì page_source để tránh code ẩn
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        except:
            body_text = (driver.page_source or "").lower()
            
        title = (driver.title or "").lower()
        text = f"{title} {body_text}"
        
        for marker in EXPIRED_LINK_MARKERS:
            if marker in text:
                return True
    except: pass
    return False

def _wait_for_new_window(driver, previous_handles, timeout=10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            handles = driver.window_handles
            for handle in handles:
                if handle not in previous_handles: return handle
        except: pass
        time.sleep(0.3)
    return ""

def _is_reset_url(url):
    if not url: return False
    url_low = url.lower()
    return any(hint in url_low for hint in RESET_URL_HINTS)

def _open_url_in_new_tab(driver, url, timeout=10):
    if not url: return ""
    previous_handles = set(driver.window_handles)
    try: driver.execute_script("window.open(arguments[0], '_blank');", url)
    except: 
        try: driver.execute_script("window.open('about:blank', '_blank');")
        except: return ""
    new_handle = _wait_for_new_window(driver, previous_handles, timeout=timeout)
    if not new_handle: return ""
    try:
        driver.switch_to.window(new_handle)
        driver.get(url)
    except: pass
    return new_handle

def _pick_reset_handle(driver, reset_url=""):
    handles = []
    try: handles = driver.window_handles
    except: pass

    # 1. Ưu tiên handle đã cache ở step 2
    reset_handle = getattr(driver, "reset_handle", "")
    if reset_handle and reset_handle in handles:
        return reset_handle

    # 2. Quét các tab hiện tại xem có tab nào chứa url reset không
    for handle in handles:
        try:
            driver.switch_to.window(handle)
            url = _wait_for_url(driver, timeout=2)
            if _is_reset_url(url): return handle
        except: pass

    # 3. Nếu không thấy tab nào nhưng có URL cache, mở tab mới
    if reset_url:
        print(f"   -> Opening cached reset URL in new tab: {reset_url[:60]}...")
        new_handle = _open_url_in_new_tab(driver, reset_url, timeout=12)
        if new_handle: return new_handle
    return ""

def _navigate_if_deref(driver, timeout=10):
    """Xử lý link redirect của GMX (deref)"""
    url = _wait_for_url(driver, timeout=timeout)
    if not url: return ""
    if "deref" not in url.lower(): return url
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        redirect_vals = qs.get("redirectUrl") or qs.get("redirecturl") or []
        if redirect_vals:
            target = unquote(redirect_vals[0])
            if target:
                driver.get(target)
                return target
    except: pass
    return url

# --- PASSWORD FORM UTILS ---

def find_elements_any_frame(driver, by, value):
    try: driver.switch_to.default_content()
    except: pass
    return _find_elements_in_frames(driver, by, value)

def _fill_password(driver, element, password):
    try:
        element.click()
        element.clear()
        element.send_keys(password)
        driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            element, password
        )
        return True
    except: return False

def _find_best_submit_button(driver, pass_input):
    form = None
    try: form = pass_input.find_element(By.XPATH, "./ancestor::form[1]")
    except: pass
    
    candidates = []
    if form:
        try: candidates = form.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
        except: pass
    if not candidates:
        try: candidates = driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
        except: pass
        
    best = None
    best_score = -1
    for el in candidates:
        txt = (el.text or el.get_attribute("value") or "").lower()
        if any(bad in txt for bad in SUBMIT_NEGATIVE_KEYWORDS): continue
        score = 0
        if el.get_attribute("type") == "submit": score += 3
        if any(k in txt for k in SUBMIT_KEYWORDS): score += 5
        if score > best_score:
            best = el
            best_score = score
    return best, form

def _submit_password_form(driver, pass_input):
    submit_btn, form = _find_best_submit_button(driver, pass_input)
    # 1. Click button
    if submit_btn:
        try:
            submit_btn.click()
            return True
        except:
            try:
                driver.execute_script("arguments[0].click();", submit_btn)
                return True
            except: pass
    # 2. Enter key
    try:
        pass_input.send_keys(Keys.ENTER)
        return True
    except: pass
    # 3. Form submit
    if form:
        try:
            driver.execute_script("arguments[0].submit();", form)
            return True
        except: pass
    return False

def _fill_confirm_password(driver, pass_input, new_password):
    """Điền ô confirm password nếu có"""
    try:
        form = pass_input.find_element(By.XPATH, "./ancestor::form[1]")
        inputs = form.find_elements(By.CSS_SELECTOR, "input[type='password']")
        for el in inputs:
            if el != pass_input:
                _fill_password(driver, el, new_password)
    except: pass

# --- MAIN STEP 3 FUNCTION ---

def execute_step3(driver, row_data_line):
    print("--- [STEP 3] ENTER NEW PASSWORD ---")

    # 1. Parse Data
    try:
        parts = row_data_line.split("\t")
        if len(parts) < 2: parts = row_data_line.split()
        new_password = parts[6].strip()
        print(f"   -> New password: {new_password}")
    except:
        print("? Input error: missing password column.")
        return False

    if not new_password:
        print("? Error: password is empty.")
        return False

    # 2. Switch to Reset Tab
    handles = driver.window_handles
    original_window = handles[0]
    
    # Lấy URL đã cache từ Step 2
    cached_reset_url = getattr(driver, "reset_url", "")
    
    reset_handle = _pick_reset_handle(driver, cached_reset_url)
    
    if not reset_handle:
        if cached_reset_url:
            print(f"   -> Tab not found, opening cached URL: {cached_reset_url[:50]}...")
            reset_handle = _open_url_in_new_tab(driver, cached_reset_url)
            
    if not reset_handle:
        print("? No reset tab found and no cached URL.")
        return False

    driver.switch_to.window(reset_handle)
    
    # 3. Handle GMX Redirect & Check Input First
    final_url = _navigate_if_deref(driver, timeout=10)
    
    pass_input = None
    
    # === LOGIC MỚI: ƯU TIÊN TÌM INPUT - NẾU CÓ THÌ BỎ QUA CHECK LỖI ===
    max_retries = 3
    for attempt in range(max_retries):
        
        # [QUAN TRỌNG] Kiểm tra Input Password TRƯỚC
        # Nếu tìm thấy input -> Page OK -> Thoát vòng lặp ngay
        pass_input = wait_element_any_frame(driver, By.XPATH, PASSWORD_XPATH, timeout=5)
        if not pass_input:
             # Fallback tìm input generic
             inputs = find_elements_any_frame(driver, By.CSS_SELECTOR, "input[type='password']")
             if inputs: pass_input = inputs[0]
        
        if pass_input:
            # print("   -> Password input found. Page is OK.")
            break 

        # Nếu KHÔNG thấy input, mới đi check xem page có bị lỗi không
        if _check_if_page_broken(driver):
            print(f"   ?? Page broken detection ('Something went wrong'). Reload attempt {attempt+1}/{max_retries}...")
            
            if attempt < max_retries - 1:
                driver.refresh()
                time.sleep(3)
                # Check lại lần nữa xem refresh có tác dụng không, nếu không thì get lại URL
                if _check_if_page_broken(driver) and cached_reset_url:
                     driver.get(cached_reset_url)
            else:
                print("   ?? Page still broken after all retries.")
        else:
            # Không thấy input, cũng không thấy lỗi -> Có thể đang load hoặc layout lạ
            time.sleep(2) # Chờ thêm chút rồi thử lại
            
    # ===================================

    if not pass_input:
        print("? Password input not found (Link might be expired/invalid).")
        driver.close()
        try: driver.switch_to.window(original_window)
        except: pass
        return False

    # 5. Fill & Submit
    try:
        print("   -> Filling password...")
        _fill_password(driver, pass_input, new_password)
        _fill_confirm_password(driver, pass_input, new_password)
        
        time.sleep(1)
        print("   -> Submitting form...")
        if not _submit_password_form(driver, pass_input):
            print("? Warning: submit action failed.")
    except Exception as e:
        print(f"? Error interacting with form: {e}")
        return False

    # 6. Wait & Cleanup
    print(f"? Waiting {WAIT_AFTER_SUBMIT_SECONDS}s after submit...")
    time.sleep(WAIT_AFTER_SUBMIT_SECONDS)

    print("   -> Back to Main Tab.")
    try: driver.switch_to.window(original_window)
    except: pass
    return True