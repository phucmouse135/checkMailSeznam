import time
import os
import tempfile
import threading
import subprocess  
import shutil
from selenium import webdriver 
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
# from webdriver_manager.chrome import ChromeDriverManager 


# --- CẤU HÌNH ---
TIMEOUT_MAX = 15 
SLEEP_INTERVAL = 1 
PROXY_HOST = "127.0.0.1"

# Folder chung chứa tất cả các profile tmp của Chrome
TMP_PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_profiles")

# --- WINDOW MANAGER CONFIG ---
# Cấu hình lưới hiển thị (Cho màn hình 1920x1080)
GRID_COLS = 6        # 6 cột cho horizontal split
GRID_ROWS = 1        # 1 hàng
WIN_WIDTH = 320      # Chiều rộng cửa sổ (1920/6)
WIN_HEIGHT = 1080    # Chiều cao cửa sổ
X_OFFSET = 0         # Lùi vào từ mép trái
Y_OFFSET = 0         # Lùi vào từ mép trên

# Lock & Cache
_DRIVER_LOCK = threading.Lock()
_INSTALLER_LOCK = threading.Lock()
_CACHED_DRIVER_PATH = None

# Quản lý Slot vị trí (Thread-safe)
class WindowPositionManager:
    def __init__(self, max_slots=10):
        self.slots = [False] * max_slots # False = Trống, True = Đang dùng
        self.lock = threading.Lock()

    def acquire(self):
        """Lấy một vị trí trống (index)"""
        with self.lock:
            for i, occupied in enumerate(self.slots):
                if not occupied:
                    self.slots[i] = True
                    return i
            return 0 # Nếu full thì xếp chồng lên slot 0

    def release(self, index):
        """Trả lại vị trí khi driver tắt"""
        with self.lock:
            if 0 <= index < len(self.slots):
                self.slots[index] = False

# Khởi tạo Global Manager
_WIN_MANAGER = WindowPositionManager(max_slots=GRID_COLS * GRID_ROWS)

# --- CÁC HÀM HỖ TRỢ DỌN DẸP ---
def ensure_tmp_dir():
    """Tạo folder tmp_profiles nếu chưa có."""
    try:
        if not os.path.exists(TMP_PROFILES_DIR):
            os.makedirs(TMP_PROFILES_DIR)
    except Exception as e:
        print(f"[CLEANUP] Lỗi tạo tmp folder: {e}")

def kill_orphaned_chrome():
    """Dọn dẹp các process chromedriver bị treo (và chrome con của nó)."""
    try:
        if os.name == 'nt': # Windows
            # /T terminates child processes (the automated chrome instances)
            subprocess.run("taskkill /f /im chromedriver.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else: # Linux/Mac
            os.system("pkill -f chromedriver")
    except Exception:
        pass

def is_driver_alive(driver):
    """Check if WebDriver connection is still alive."""
    if not driver:
        return False
    try:
        # Try to get current URL - this is a lightweight operation
        driver.current_url
        return True
    except Exception:
        return False

def _install_driver_once():
    """Use existing chromedriver.exe exclusively."""
    global _CACHED_DRIVER_PATH
    if _CACHED_DRIVER_PATH:
        return _CACHED_DRIVER_PATH
    
    with _INSTALLER_LOCK:
        if not _CACHED_DRIVER_PATH:
            try:
                # Try to find chromedriver.exe in current directory
                driver_path = os.path.join(os.getcwd(), "chromedriver.exe")
                if os.path.exists(driver_path):
                    _CACHED_DRIVER_PATH = driver_path
                    print(f"[CORE] Using local driver at: {_CACHED_DRIVER_PATH}")
                else:
                    raise FileNotFoundError("chromedriver.exe not found in current directory. Please download it and place it next to the script.")
            except Exception as e:
                print(f"[CORE] Driver initialization failed: {e}")
                raise e
    return _CACHED_DRIVER_PATH

# --- HÀM KHỞI TẠO DRIVER (TỐI ƯU HIỆU SUẤT + GRID LAYOUT) ---
def get_driver(headless=False, proxy_port=None, thread_id=0, max_threads=6):
    """
    Initialize browser with Standard Selenium + Grid Layout Positioning.
    """
    options = Options()
    
    # --- Proxy ---
    if proxy_port:
        proxy_server = f"http://{PROXY_HOST}:{proxy_port}"
        options.add_argument(f'--proxy-server={proxy_server}')
    
    # --- User Agent ---
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options.add_argument(f'--user-agent={user_agent}')

    # --- WINDOW POSITIONING LOGIC ---
    if headless:
        options.add_argument('--headless=new')
        options.add_argument("--window-size=1280,720")
    else:
        # Horizontal split based on thread_id, max 6
        effective_cols = min(6, max_threads)
        effective_width = 1920 // effective_cols  # Total screen width / number of columns
        col_idx = thread_id % effective_cols
        row_idx = 0
        slot_idx = col_idx  # Slot index for window manager
        
        pos_x = X_OFFSET + (col_idx * effective_width)
        pos_y = Y_OFFSET + (row_idx * WIN_HEIGHT)
        
        # Set tham số chrome
        options.add_argument(f"--window-size={effective_width},{WIN_HEIGHT}")
        options.add_argument(f"--window-position={pos_x},{pos_y}")
        
        # print(f"[CORE] Thread {thread_id}: Position ({pos_x}, {pos_y})")

    # --- Config Khác ---
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    
    # Tắt load ảnh để chạy nhanh
    options.add_argument("--blink-settings=imagesEnabled=false") 
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    
    options.page_load_strategy = 'eager'

    # Anti-detect cơ bản
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # Tạo profile trong folder tmp_profiles của dự án (không phải system temp)
    ensure_tmp_dir()
    profile_dir = tempfile.mkdtemp(dir=TMP_PROFILES_DIR)
    options.add_argument(f"--user-data-dir={profile_dir}")
    
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    }
    options.add_experimental_option("prefs", prefs)
    
    try:
        # Kill any orphaned Chrome processes before starting? NO! This kills other threads' drivers!
        # kill_orphaned_chrome() 
        
        driver_path = _install_driver_once()
        # Add verbose logging to help debug if needed, but suppressed for normal use
        service = Service(driver_path, log_output=subprocess.DEVNULL) 
        driver = webdriver.Chrome(service=service, options=options)
        
        # Store profile_dir for cleanup
        setattr(driver, '_profile_dir', profile_dir)
        
        # Increase timeouts for stability
        driver.set_page_load_timeout(120)  # Increased from 60
        driver.set_script_timeout(120)     # Increased from 60

        # Bypass navigator.webdriver
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        })
        
        # --- MONKEY PATCH DRIVER.QUIT ---
        # Để tự động trả lại slot vị trí và dọn dẹp profile khi driver tắt
        original_quit = driver.quit
        def quit_wrapper():
            result = None
            try:
                # BƯỚC 1: Quit driver trước để đóng Chrome process
                result = original_quit()
            except Exception:
                pass
            
            try:
                # BƯỚC 2: Trả lại window slot
                if not headless:
                    _WIN_MANAGER.release(slot_idx)
            except Exception:
                pass
            
            # BƯỚC 3: Xóa folder tmp NGAY sau khi Chrome đã tắt
            try:
                profile_dir = getattr(driver, '_profile_dir', None)
                if profile_dir:
                    # Thử xóa nhiều lần (tối đa 5 giây) để chờ OS nhả lock
                    end_time = time.time() + 5
                    while time.time() < end_time:
                        try:
                            if os.path.exists(profile_dir):
                                shutil.rmtree(profile_dir)
                                print(f"[CLEANUP] Đã xóa profile: {os.path.basename(profile_dir)}")
                            break
                        except Exception:
                            time.sleep(0.2)
                    # Lần cuối cùng với ignore_errors nếu vẫn chưa xóa được
                    try:
                        if os.path.exists(profile_dir):
                            shutil.rmtree(profile_dir, ignore_errors=True)
                    except Exception:
                        pass
            except Exception:
                pass
            
            return result
        driver.quit = quit_wrapper
        
        return driver
    except Exception as e:
        # Nếu lỗi khởi tạo, nhớ trả lại slot
        if not headless:
            try:
                _WIN_MANAGER.release(slot_idx)
            except Exception:
                pass
        print(f"[CORE] Lỗi khởi tạo Driver: {e}")
        raise e

# --- CÁC HÀM LOGIC NGHIỆP VỤ (GIỮ NGUYÊN) ---
def find_element_safe(driver, by, value, timeout=TIMEOUT_MAX, click=False, send_keys=None):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if reload_if_ad_popup(driver):
             pass
        try:
            element = driver.find_element(by, value)
            if click:
                try:
                    element.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", element)
                return True
            if send_keys:
                element.clear()
                element.send_keys(send_keys)
                return True
            return element 
        except Exception:
            time.sleep(SLEEP_INTERVAL)
            continue
    return None

def reload_if_ad_popup(driver, url="https://www.gmx.net/"):
    try:
        try:
            current_url = driver.current_url
        except Exception:
            current_url = ""

        if current_url.startswith("https://suche.gmx.net/web"):
            driver.get(url)
            time.sleep(2)
            return True

        page_source = ""
        try:
            page_source = driver.page_source.lower()
        except Exception:
            pass

        if "wir finanzieren uns" in page_source:
            popup_hints = [
                "werbung", "akzeptieren und weiter", "zum abo ohne fremdwerbung", "postfach ohne fremdwerbebanner",
            ]
            if any(hint in page_source for hint in popup_hints):
                # print(">> [CORE] Phát hiện Popup Quảng cáo -> Reload GMX.")
                driver.get(url)
                time.sleep(2)
                return True

    except Exception:
        pass
    return False

def wait_element(driver, by, value, timeout=10, visible=True):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            elements = driver.find_elements(by, value)
            if elements:
                el = elements[0]
                if not visible or el.is_displayed():
                    return el
        except Exception:
            pass
        time.sleep(0.2)
    return None

def wait_and_click(driver, by, value, timeout=10):
    el = wait_element(driver, by, value, timeout=timeout, visible=True)
    if not el:
        return False
    try:
        el.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False