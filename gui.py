import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os

import mail_handler


COLUMNS = [
    "PHOI GOC",
    "PASS MAIL",
    "FOUND_DATA",
    "LINK",
    "NOTE",
]
_FILE_LOCK = threading.Lock()

class AutomationGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GMX Automation Tool")
        self.geometry("1200x700")

        self.file_path_var = tk.StringVar()
        self.threads_var = tk.IntVar(value=2)
        self.headless_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.StringVar(value="0/0")
        self.success_var = tk.StringVar(value="0")

        self.task_queue = queue.Queue()
        self.update_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.workers = []
        self.running = False
        self.total_count = 0
        self.done_count = 0
        self.success_count = 0

        self._build_ui()
        self.after(200, self._process_updates)
        
    def _save_live_result(self, values, status, message):
        """Ghi kết quả ngay lập tức vào file success.txt hoặc fail.txt"""
        try:
            # Tạo nội dung dòng log: Ghi toàn bộ các cột + status + message
            # Chuyển đổi values sang string (nếu chưa phải string) và join lại bằng tab
            row_content = "\t".join(str(v) for v in values)
            
            line_content = f"{row_content}\t{status}\t{message}"
            
            # Xác định file để ghi dựa trên status
            is_success = status == "success"
            filename = "success.txt" if is_success else "fail.txt"
            
            with _FILE_LOCK: # Khóa file để các luồng không ghi đè nhau
                with open(filename, "a", encoding="utf-8") as f:
                    f.write(line_content + "\n")
                    f.flush()
                    os.fsync(f.fileno()) # Ép ghi xuống ổ cứng ngay
                    
                # Vẫn ghi vào output.txt như cũ để tương thích
                with open("output.txt", "a", encoding="utf-8") as f:
                    f.write(line_content + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        except Exception as e:
            print(f"Lỗi ghi live output: {e}")

    def _save_result(self, ok, values, status, message):
        """Ghi kết quả vào success.txt hoặc fail.txt"""
        try:
            # Tạo nội dung dòng log: MAIL | PASS | STATUS | MSG
            mail = values[0]
            password = values[1]
            line_content = f"{mail}\t{password}\t{status}\t{message}"
            
            file_name = "success.txt" if ok else "fail.txt"
            
            with _FILE_LOCK:
                with open(file_name, "a", encoding="utf-8") as f:
                    f.write(line_content + "\n")
                    f.flush()
                    os.fsync(f.fileno())
        except Exception as e:
            print(f"Lỗi ghi result: {e}")

    def _shutdown_workers(self):
        if not self.workers:
            return
        self.stop_event.set()
        for _ in self.workers:
            try:
                self.task_queue.put(None)
            except Exception:
                pass
        for thread in self.workers:
            try:
                thread.join(timeout=0.2)
            except Exception:
                pass
        self.workers = []

    def _build_ui(self):
        self._build_file_frame()
        self._build_config_frame()
        self._build_table()
        self._build_control_frame()

    def _build_file_frame(self):
        frame = ttk.LabelFrame(self, text="Input")
        frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame, text="Input file").grid(row=0, column=0, padx=5, pady=5)
        entry = ttk.Entry(frame, textvariable=self.file_path_var, width=70)
        entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(frame, text="Browse", command=self.browse_file).grid(
            row=0, column=2, padx=5, pady=5
        )
        ttk.Button(frame, text="Load Data", command=self.load_file).grid(
            row=0, column=3, padx=5, pady=5
        )
        ttk.Button(frame, text="Paste Data", command=self.open_paste_dialog).grid(
            row=0, column=4, padx=5, pady=5
        )

        frame.columnconfigure(1, weight=1)

    def _build_config_frame(self):
        frame = ttk.LabelFrame(self, text="Config")
        frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame, text="Threads").grid(row=0, column=0, padx=5, pady=5)
        spin = ttk.Spinbox(
            frame, from_=1, to=20, textvariable=self.threads_var, width=5
        )
        spin.grid(row=0, column=1, padx=5, pady=5)

        ttk.Checkbutton(frame, text="Headless", variable=self.headless_var).grid(
            row=0, column=2, padx=10, pady=5
        )

        ttk.Button(frame, text="Delete Selected", command=self.delete_selected).grid(
            row=0, column=3, padx=10, pady=5
        )
        ttk.Button(frame, text="Delete All", command=self.delete_all).grid(
            row=0, column=4, padx=5, pady=5
        )

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings")
        for col in COLUMNS:
            self.tree.heading(col, text=col)
            if col in ["FOUND_DATA", "LINK"]:
                width = 200
            elif col == "NOTE":
                width = 180
            else:
                width = 120
            self.tree.column(col, width=width, minwidth=80, anchor=tk.W)
        self.tree.tag_configure(
            "success", foreground="#1b7f1b", background="#e6f4ea"
        )
        self.tree.tag_configure("error", foreground="#c62828", background="#fdecea")
        self.tree.tag_configure("running", background="#fff3cd")  # vàng nhạt

        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._build_context_menu()
        self.tree.bind("<Button-3>", self._show_context_menu)

    def _build_context_menu(self):
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Delete selected", command=self.delete_selected)

    def _build_control_frame(self):
        frame = ttk.LabelFrame(self, text="Control")
        frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(frame, text="START", command=self.start).grid(
            row=0, column=0, padx=5, pady=5
        )
        ttk.Button(frame, text="STOP", command=self.stop).grid(
            row=0, column=1, padx=5, pady=5
        )

        ttk.Label(frame, text="Progress").grid(row=0, column=2, padx=10, pady=5)
        ttk.Label(frame, textvariable=self.progress_var).grid(
            row=0, column=3, padx=5, pady=5
        )

        ttk.Label(frame, text="Success").grid(row=0, column=4, padx=10, pady=5)
        ttk.Label(frame, textvariable=self.success_var).grid(
            row=0, column=5, padx=5, pady=5
        )

        ttk.Label(frame, text="Status").grid(row=0, column=6, padx=10, pady=5)
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=0, column=7, padx=5, pady=5
        )

        ttk.Button(frame, text="Export Success", command=self.export_success).grid(
            row=0, column=8, padx=10, pady=5
        )
        ttk.Button(frame, text="Export Fail", command=self.export_fail).grid(
            row=0, column=9, padx=5, pady=5
        )
        ttk.Button(frame, text="Export No Success", command=self.export_no_success).grid(
            row=0, column=10, padx=5, pady=5
        )
        ttk.Button(frame, text="Export All", command=self.export_all).grid(
            row=0, column=11, padx=5, pady=5
        )

    def browse_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if path:
            self.file_path_var.set(path)
            self.load_file()

    def load_file(self):
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Input", "Please select a file.")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            rows = self._parse_lines(content)
            self._load_rows(rows)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def open_paste_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Paste Data")
        dialog.geometry("820x460")
        dialog.minsize(700, 360)

        try:
            ttk.Style(dialog).theme_use("clam")
        except Exception:
            pass

        container = ttk.Frame(dialog, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text="Paste tab-separated data",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            container,
            text="Press Enter to submit. Shift+Enter for new line.",
            foreground="#555555",
        ).pack(anchor=tk.W, pady=(2, 8))

        sample_frame = ttk.LabelFrame(container, text="Sample data")
        sample_frame.pack(fill=tk.X, pady=(0, 10))
        sample_text = tk.Text(sample_frame, height=3, wrap=tk.NONE, relief="flat")
        sample_text.pack(fill=tk.X, padx=6, pady=6)
        sample_value = (
            "PHOI GOC\tPASS MAIL\tFOUND_DATA\tLINK\tNOTE\n"
            "example@gmx.de\tpassword\t\t\tPending"
        )
        sample_text.insert("1.0", sample_value)
        sample_text.configure(state="disabled")

        text = tk.Text(dialog, wrap=tk.NONE)
        text_frame = ttk.Frame(container, borderwidth=1, relief="solid")
        text_frame.pack(fill=tk.BOTH, expand=True)
        text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        text.focus_set()

        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=y_scroll.set)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def on_submit(event=None):
            content = text.get("1.0", tk.END)
            rows = self._parse_lines(content)
            self._append_rows(rows)
            dialog.destroy()
            return "break"

        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Submit", command=on_submit).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        text.bind("<Return>", on_submit)
        text.bind("<Shift-Return>", lambda event: None)
        dialog.bind("<Escape>", lambda event: dialog.destroy())

    def _parse_lines(self, content):
        lines = [line for line in content.splitlines() if line.strip()]
        if not lines:
            return []

        expected_cols = len(COLUMNS)
        start_idx = 0
        header_probe = lines[0].lower()
        if "phoi" in header_probe and "pass" in header_probe:
            start_idx = 1

        rows = []
        for line in lines[start_idx:]:
            parts = line.split("\t")
            if len(parts) == 1:
                parts = line.split()
            parts = [p.strip() for p in parts]
            if len(parts) < expected_cols:
                parts.extend([""] * (expected_cols - len(parts)))
            if len(parts) > expected_cols:
                parts = parts[:expected_cols]
            rows.append(parts)
        return rows

    def _load_rows(self, rows):
        self.delete_all()
        expected_cols = len(COLUMNS)
        for row in rows:
            values = list(row)
            if len(values) < expected_cols:
                values.extend([""] * (expected_cols - len(values)))
            if len(values) > expected_cols:
                values = values[:expected_cols]
            note = (values[-1] or "").strip()
            if not note:
                values[-1] = "Pending"
                note = values[-1]
            tag = self._get_note_tag(note)
            tags = (tag,) if tag else ()
            self.tree.insert("", tk.END, values=values, tags=tags)
        self._reset_stats()

    def _append_rows(self, rows):
        expected_cols = len(COLUMNS)
        for row in rows:
            values = list(row)
            if len(values) < expected_cols:
                values.extend([""] * (expected_cols - len(values)))
            if len(values) > expected_cols:
                values = values[:expected_cols]
            note = (values[-1] or "").strip()
            if not note:
                values[-1] = "Pending"
                note = values[-1]
            tag = self._get_note_tag(note)
            tags = (tag,) if tag else ()
            self.tree.insert("", tk.END, values=values, tags=tags)
        if not self.running:
            self._reset_stats()

    def delete_selected(self):
        for item in self.tree.selection():
            self.tree.delete(item)
        self._reset_stats()

    def delete_all(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._reset_stats()

    def _reset_stats(self):
        self.total_count = 0
        self.done_count = 0
        self.success_count = 0
        self.progress_var.set("0/0")
        self.success_var.set("0")

    def _is_success_note(self, note):
        if not isinstance(note, str):
            return False
        return note.strip().lower().startswith("success")

    def _get_note_tag(self, note):
        if not isinstance(note, str):
            return ""
        clean = note.strip().lower()
        if clean.startswith("success"):
            return "success"
        if clean.startswith("error") or clean == "fail":
            return "error"
        return ""

    def _apply_note_tag(self, item_id, note):
        tag = self._get_note_tag(note)
        if tag:
            self.tree.item(item_id, tags=(tag,))
        else:
            self.tree.item(item_id, tags=())

    def _show_context_menu(self, event):
        if self.tree.identify_row(event.y):
            self.menu.tk_popup(event.x_root, event.y_root)

    def start(self):
        if self.running:
            return

        self._shutdown_workers()
        items = self.tree.get_children()
        tasks = []
        for item in items:
            values = list(self.tree.item(item, "values"))
            note = values[-1]
            if self._is_success_note(note):
                continue
            has_login = len(values) >= 1 and values[0]
            has_pass = len(values) >= 2 and values[1]
            if not has_login or not has_pass:
                values[-1] = "Error: missing phoi goc/pass mail"
                self.tree.item(item, values=values)
                self._apply_note_tag(item, values[-1])
                continue
            values[-1] = "Pending"
            self.tree.item(item, values=values)
            self._apply_note_tag(item, values[-1])
            tasks.append((item, values))

        if not tasks:
            messagebox.showinfo("Run", "No valid rows to process.")
            return

        self.total_count = len(tasks)
        self.done_count = 0
        self.success_count = 0
        self.progress_var.set(f"{self.done_count}/{self.total_count}")
        self.success_var.set(str(self.success_count))

        self.stop_event.clear()
        self.task_queue = queue.Queue()
        for task in tasks:
            self.task_queue.put(task)

        worker_count = max(1, int(self.threads_var.get()))
        self.workers = []
        for _ in range(worker_count):
            thread = threading.Thread(target=self._worker, daemon=True)
            thread.start()
            self.workers.append(thread)

        self.running = True
        self.status_var.set("Running")

    def stop(self):
        if not self.running:
            return
        self.stop_event.set()

        drained = 0
        while True:
            try:
                item = self.task_queue.get_nowait()
                if item is not None:
                    drained += 1
                self.task_queue.task_done()
            except queue.Empty:
                break

        self.total_count = max(0, self.total_count - drained)
        for _ in self.workers:
            self.task_queue.put(None)

        self.progress_var.set(f"{self.done_count}/{self.total_count}")
        self.status_var.set("Stopping")

    def _worker(self):
        while True:
            try:
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                if self.stop_event.is_set():
                    break
                continue

            if task is None:
                self.task_queue.task_done()
                break

            item_id, values = task
            if self.stop_event.is_set():
                self.task_queue.task_done()
                continue

            print(f"{values[0]} : Starting verification")

            self.update_queue.put(("status", item_id, "Running"))

            ok = False
            result = None
            err = ""
            for attempt in range(1):  # Thử tối đa 2 lần
                print(f"{values[0]} : Attempt {attempt+1} starting")
                try:
                    result = mail_handler.verify_account_live(values[0], values[1])
                    if result.startswith("success"):
                        ok = True
                        print(f"{values[0]} : Success - {result}")
                        break
                    else:
                        print(f"{values[0]} : Attempt {attempt+1} failed: {result}")
                except Exception as exc:
                    err = str(exc)
                    print(f"{values[0]} : Attempt {attempt+1} error: {err}")
                    break
            else:
                result = "fail"
                err = "Fail after 2 retries"
                print(f"{values[0]} : Failed after 2 attempts")

            if ok:
                values[2] = result  # ghi found_data vào FOUND_DATA
                # Parse LINK from result
                link = ""
                if "|" in result:
                    parts = result.split("|")
                    for part in parts:
                        if part.startswith("LINK="):
                            link = part.split("=", 1)[1]
                            break
                values[3] = link  # ghi link vào LINK
                values[4] = "success"  # ghi success vào NOTE
            else:
                values[4] = "fail"
            
            print(f"{values[0]} : Updated FOUND_DATA: {values[2]}, NOTE: {values[3]}")
            
            self.update_queue.put(("update", item_id, values))

            msg_log = err if err else result
            status = "success" if ok else "fail"
            self._save_live_result(values, status, msg_log)
            self._save_result(ok, values, status, msg_log)

            self.update_queue.put(("done", item_id, ok, err))
            self.task_queue.task_done()

        self.update_queue.put(("worker_done",))

    def _process_updates(self):
        try:
            while True:
                msg = self.update_queue.get_nowait()
                if msg[0] == "status":
                    _, item_id, status = msg
                    if status == "Running":
                        self.tree.item(item_id, tags=("running",))
                    elif isinstance(status, str) and status.startswith("USER="):
                        user_value = status.split("=", 1)[1].strip()
                        values = list(self.tree.item(item_id, "values"))
                        if user_value:
                            values[2] = user_value
                        self.tree.item(item_id, values=values)
                    else:
                        values = list(self.tree.item(item_id, "values"))
                        values[-1] = status
                        self.tree.item(item_id, values=values)
                        self._apply_note_tag(item_id, status)
                elif msg[0] == "update":
                    _, item_id, values = msg
                    self.tree.item(item_id, values=values)
                    self._apply_note_tag(item_id, values[-1])
                elif msg[0] == "done":
                    _, item_id, ok, err = msg
                    values = list(self.tree.item(item_id, "values"))
                    if ok:
                        self.success_count += 1
                    self.tree.item(item_id, values=values)
                    self._apply_note_tag(item_id, values[-1])
                    self.done_count += 1
                    self.progress_var.set(f"{self.done_count}/{self.total_count}")
                    self.success_var.set(str(self.success_count))
                elif msg[0] == "worker_done":
                    pass
        except queue.Empty:
            pass

        if self.running and self.done_count >= self.total_count:
            self.running = False
            self._shutdown_workers()
            self.status_var.set("Ready")
            self.stop_event.clear()

        self.after(200, self._process_updates)

    def export_success(self):
        rows = []
        for item in self.tree.get_children():
            values = list(self.tree.item(item, "values"))
            if values and self._is_success_note(values[-1]):
                rows.append(values)
        if not rows:
            messagebox.showinfo("Export", "No success rows.")
            return
        self._export_rows(rows, "success.txt")


    def export_fail(self):
        # Chỉ xuất các dòng có trạng thái Fail (Error)
        rows = []
        for item in self.tree.get_children():
            values = list(self.tree.item(item, "values"))
            if values and self._get_note_tag(values[-1]) == "error":
                rows.append(values)
        if not rows:
            messagebox.showinfo("Export", "No failed rows.")
            return
        self._export_rows(rows, "fail.txt")

    def export_no_success(self):
        # Xuất các dòng không phải Success (bao gồm cả Fail và Pending)
        rows = []
        for item in self.tree.get_children():
            values = list(self.tree.item(item, "values"))
            if values and not self._is_success_note(values[-1]):
                rows.append(values)
        if not rows:
            messagebox.showinfo("Export", "No 'No Success' rows.")
            return
        self._export_rows(rows, "no_success.txt")

    def export_all(self):
        rows = [list(self.tree.item(item, "values")) for item in self.tree.get_children()]
        if not rows:
            messagebox.showinfo("Export", "No data to export.")
            return
        self._export_rows(rows, "all.txt")

    def _export_rows(self, rows, default_filename="export.txt"):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_filename,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\t".join(COLUMNS) + "\n")
                for row in rows:
                    f.write("\t".join(row) + "\n")
            messagebox.showinfo("Export", f"Saved: {path}")
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))


if __name__ == "__main__":
    app = AutomationGUI()
    app.mainloop()
