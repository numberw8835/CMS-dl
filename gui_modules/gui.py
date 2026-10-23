import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import os
import queue
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from cms_auth import authenticate
from cms_config import (
    courses_file_path,
    load_course_definitions,
    load_credentials,
    load_settings,
    save_course_definitions,
    save_credentials,
    save_settings,
)
from cms_modules import (
    __version__,
    DownloadCancelled,
    DownloadHooks,
    course_key,
    describe_stats,
    download_course_group,
    get_course_list,
    group_courses,
    read_manual_fix_file,
    refresh_course_definitions,
    season_id_of,
    semester_labels,
    write_manual_fix_file,
)

DEFAULT_SETTINGS = {
    "download_path": str(Path.home() / "Downloads" / "CMS_Courses"),
    "theme": "dark",
    "delay": 1,
    "by_semester": False,
}
ACCENT = ("#3b8ed0", "#1f6aa5")
ACCENT_HOVER = ("#2e7ab8", "#164f7a")
MUTED_TEXT = ("gray40", "gray65")
ALL_SEMESTERS = "All semesters"
CTK_MAJOR_VERSION = int(ctk.__version__.split(".")[0])
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def open_in_file_manager(path):
    """Opens a folder (or file) with the system's default application."""
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        # A PyInstaller build points LD_LIBRARY_PATH at its bundled libraries; don't hand that to the file manager
        env = os.environ.copy()
        if getattr(sys, "frozen", False):
            if "LD_LIBRARY_PATH_ORIG" in env:
                env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
            else:
                env.pop("LD_LIBRARY_PATH", None)
        subprocess.Popen(["xdg-open", path], env=env)


def format_size(num_bytes):
    if num_bytes < 1_048_576:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes / 1_048_576:.1f} MB"


def set_window_icon(window):
    """Uses the app icon instead of customtkinter's; on Windows that has to happen after customtkinter sets its own."""
    try:
        if sys.platform.startswith("win"):
            window.iconbitmap(os.path.join(ASSETS_DIR, "icon.ico"))
        else:
            window._icon_image = tk.PhotoImage(file=os.path.join(ASSETS_DIR, "icon.png"))
            window.iconphoto(True, window._icon_image)
    except (tk.TclError, OSError):
        pass  # keep the default icon


def monospace_font(size=12):
    family = {"win32": "Consolas", "darwin": "Menlo"}.get(sys.platform, "DejaVu Sans Mono")
    return ctk.CTkFont(family=family, size=size)


class LogStream:
    """Stands in for stdout/stderr so everything the downloader prints shows up in the log panel."""

    encoding = "utf-8"

    def __init__(self, app, original):
        self._app = app
        self._original = original  # None when there is no console (pythonw or a windowed .exe)

    def write(self, text):
        if self._original is not None:
            try:
                self._original.write(text)
            except Exception:
                pass
        if text:
            self._app.post_log(text)
        return len(text)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def writable(self):
        return True


class ScrollableFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame that also scrolls with the mouse wheel on Linux (customtkinter 6 does this itself)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sys.platform.startswith("linux") and CTK_MAJOR_VERSION < 6:
            self.bind_all("<Button-4>", self._linux_mouse_wheel, add="+")
            self.bind_all("<Button-5>", self._linux_mouse_wheel, add="+")

    def _linux_mouse_wheel(self, event):
        if self.check_if_master_is_canvas(event.widget) and self._parent_canvas.yview() != (0.0, 1.0):
            self._parent_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")


def create_header(parent, controller, title):
    """The blue bar with a back button used by the inner pages."""
    header = ctk.CTkFrame(parent, height=64, corner_radius=0, fg_color=ACCENT)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    header.grid_columnconfigure(1, weight=1)
    header.grid_rowconfigure(0, weight=1)

    back_btn = ctk.CTkButton(
        header,
        text="← Back",
        width=80,
        height=34,
        fg_color=("#2e7ab8", "#164f7a"),
        hover_color=("#25689e", "#123f63"),
        command=lambda: controller.show_frame("HomeFrame"),
    )
    back_btn.grid(row=0, column=0, padx=(16, 12))

    title_label = ctk.CTkLabel(
        header,
        text=title,
        font=ctk.CTkFont(size=22, weight="bold"),
        text_color="white",
        anchor="w",
    )
    title_label.grid(row=0, column=1, sticky="w")
    return header


class CMSDownloaderApp(ctk.CTk):
    def __init__(self, settings=None):
        super().__init__()

        self.title("GUC CMS Downloader 📚")
        self.geometry("900x650")
        self.minsize(800, 560)
        self.resizable(True, True)
        set_window_icon(self)

        # App state
        self.settings = {**DEFAULT_SETTINGS, **(settings or {})}
        self.session = None
        self.username, self.password = load_credentials()
        self.courses = []  # latest course list from the CMS, one entry per time a course was taken
        self.busy = False
        self.cancel_event = threading.Event()
        self.open_dialog = None
        self.current_frame = None
        self._ui_queue = queue.Queue()

        # Show everything the downloader prints in the log panel
        self._original_streams = (sys.stdout, sys.stderr)
        sys.stdout = LogStream(self, sys.stdout)
        sys.stderr = LogStream(self, sys.stderr)

        # Container for all frames
        self.container = ctk.CTkFrame(self, corner_radius=0)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Dictionary to hold frames
        self.frames = {}

        # Initialize frames
        for F in (OnboardingFrame, HomeFrame, DownloadFrame, SettingsFrame):
            frame = F(self.container, self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, self._process_queue)

        # Show appropriate starting frame
        if self.username and self.password:
            self.show_frame("HomeFrame")
        else:
            self.show_frame("OnboardingFrame")

    def show_frame(self, frame_name):
        """Show the requested frame"""
        self.current_frame = frame_name
        frame = self.frames[frame_name]
        frame.tkraise()
        # Call on_show if the frame has this method
        if hasattr(frame, 'on_show'):
            frame.on_show()

    # --- Talking to the background thread -------------------------------------------------

    def post(self, callback, *args):
        """Runs callback(*args) on the UI thread; safe to call from the background thread."""
        self._ui_queue.put((callback, args))

    def post_log(self, text):
        self._ui_queue.put((None, (text,)))

    def _process_queue(self):
        pending_log = []
        try:
            for _ in range(500):
                callback, args = self._ui_queue.get_nowait()
                if callback is None:
                    pending_log.append(args[0])
                    continue
                if pending_log:
                    self.frames["DownloadFrame"].append_log("".join(pending_log))
                    pending_log = []
                try:
                    callback(*args)
                except Exception as e:
                    self._original_print(f"UI callback failed: {e!r}")
        except queue.Empty:
            pass
        if pending_log:
            self.frames["DownloadFrame"].append_log("".join(pending_log))
        self.after(50, self._process_queue)

    def _original_print(self, text):
        stream = self._original_streams[1]
        if stream is not None:
            print(text, file=stream)

    def run_task(self, work, on_done=None, on_error=None):
        """Runs work() on a background thread, one task at a time, so the window never freezes.

        on_done(result) or on_error(exception) is then called on the UI thread.
        """
        if self.busy:
            messagebox.showinfo("Please wait", "Something is still running. Wait for it or press Stop.")
            return False
        self.cancel_event.clear()
        self._set_busy(True)

        def runner():
            try:
                result = work()
            except BaseException as e:
                self.post(self._task_finished, on_error, e)
            else:
                self.post(self._task_finished, on_done, result)

        threading.Thread(target=runner, daemon=True).start()
        return True

    def _task_finished(self, callback, value):
        self._set_busy(False)
        if callback is not None:
            callback(value)
        elif isinstance(value, BaseException) and not isinstance(value, DownloadCancelled):
            messagebox.showerror("Error", str(value))

    def _set_busy(self, busy):
        self.busy = busy
        for frame in self.frames.values():
            if hasattr(frame, "on_busy_changed"):
                frame.on_busy_changed(busy)

    def make_hooks(self, on_progress):
        """Download hooks that report progress to the UI, ask for manual fixes in a dialog and obey Stop."""
        last_update = [0.0]

        def progress(name, done, total):
            now = time.monotonic()
            if done == 0 or (total and done >= total) or now - last_update[0] > 0.1:
                last_update[0] = now
                self.post(on_progress, name, done, total)

        return DownloadHooks(resolve_mismatch=self.ask_manual_fix, progress=progress, cancel=self.cancel_event)

    def ask_manual_fix(self, manual_file_path):
        """Called on the download thread: shows the manual-fix dialog and waits for the answer."""
        answer = {"saved": False}
        closed = threading.Event()

        def on_close(saved):
            answer["saved"] = saved
            closed.set()

        print(f"Names didn't match; waiting for you to fix them in the dialog ({os.path.basename(manual_file_path)})")
        self.post(lambda: ManualFixDialog(self, manual_file_path, on_close))
        while not closed.wait(0.2):
            if self.cancel_event.is_set():
                return False
        return answer["saved"]

    def stop(self):
        self.cancel_event.set()
        if self.open_dialog is not None:
            self.open_dialog.close(False)

    # --- Account --------------------------------------------------------------------------

    def sign_in(self, on_success=None, on_failure=None):
        """Signs in on a background thread and reports the result on the home page."""
        username, password = self.username, self.password
        home = self.frames["HomeFrame"]
        home.set_account_status(f"Signing in as {username}…")

        def done(session):
            self.session = session
            home.set_account_status(f"✅ Signed in as {username}", ok=True)
            if on_success is not None:
                on_success()

        def failed(error):
            self.session = None
            home.set_account_status(f"⚠️ Couldn't sign in: {error}", ok=False)
            if on_failure is not None:
                on_failure(error)

        return self.run_task(lambda: authenticate(username, password), done, failed)

    def ensure_session(self, then):
        """Calls then() once signed in, signing in first if needed."""
        if self.session is not None:
            then()
            return
        self.sign_in(on_success=then, on_failure=lambda e: messagebox.showerror("Sign-in failed", str(e)))

    def save_app_settings(self):
        save_settings(self.settings)

    def on_close(self):
        if self.busy and not messagebox.askyesno("Quit", "A download is still running. Stop it and quit?"):
            return
        self.stop()
        sys.stdout, sys.stderr = self._original_streams
        if self.session is not None:
            self.session.close()
        self.destroy()


class OnboardingFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Configure grid for responsiveness
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Scrollable container for content
        scroll_frame = ScrollableFrame(self, fg_color="transparent")
        scroll_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        scroll_frame.grid_columnconfigure(0, weight=1)

        # Main container
        main_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        main_frame.grid(row=0, column=0, pady=20)
        main_frame.grid_columnconfigure(0, weight=1)

        # Welcome header
        title = ctk.CTkLabel(
            main_frame,
            text="Welcome to CMS Downloader! 🎓",
            font=ctk.CTkFont(size=30, weight="bold")
        )
        title.pack(pady=(0, 10))

        subtitle = ctk.CTkLabel(
            main_frame,
            text="Sign in with your GUC account and choose where to save your courses",
            font=ctk.CTkFont(size=15),
            text_color=MUTED_TEXT
        )
        subtitle.pack(pady=(0, 30))

        # Credentials frame
        cred_frame = ctk.CTkFrame(main_frame)
        cred_frame.pack(pady=10, padx=40, fill="both")

        # Username
        username_label = ctk.CTkLabel(
            cred_frame,
            text="GUC Username 👤",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        username_label.pack(pady=(20, 5), anchor="w", padx=20)

        self.username_entry = ctk.CTkEntry(
            cred_frame,
            placeholder_text="e.g. firstname.lastname",
            width=360,
            height=40
        )
        self.username_entry.pack(pady=(0, 15), padx=20)

        # Password
        password_label = ctk.CTkLabel(
            cred_frame,
            text="GUC Password 🔒",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        password_label.pack(pady=(10, 5), anchor="w", padx=20)

        self.password_entry = ctk.CTkEntry(
            cred_frame,
            placeholder_text="Enter your GUC password",
            show="*",
            width=360,
            height=40
        )
        self.password_entry.pack(pady=(0, 20), padx=20)

        # Download path
        path_label = ctk.CTkLabel(
            cred_frame,
            text="Download Location 📁",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        path_label.pack(pady=(10, 5), anchor="w", padx=20)

        path_frame = ctk.CTkFrame(cred_frame, fg_color="transparent")
        path_frame.pack(pady=(0, 20), padx=20, fill="x")

        self.path_entry = ctk.CTkEntry(
            path_frame,
            placeholder_text="Download folder",
            width=260,
            height=40
        )
        self.path_entry.insert(0, self.controller.settings["download_path"])
        self.path_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)

        browse_btn = ctk.CTkButton(
            path_frame,
            text="Browse",
            width=90,
            height=40,
            command=self.browse_folder
        )
        browse_btn.pack(side="left")

        # Get Started button
        self.start_btn = ctk.CTkButton(
            main_frame,
            text="Get Started! 🚀",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=360,
            height=50,
            command=self.complete_onboarding
        )
        self.start_btn.pack(pady=(25, 8))

        self.message_label = ctk.CTkLabel(main_frame, text="", text_color=MUTED_TEXT, wraplength=420)
        self.message_label.pack(pady=(0, 10))

        for entry in (self.username_entry, self.password_entry, self.path_entry):
            entry.bind("<Return>", lambda event: self.complete_onboarding())

    def browse_folder(self):
        """Open folder browser"""
        folder = filedialog.askdirectory(initialdir=self.path_entry.get() or str(Path.home()))
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, os.path.normpath(folder))

    def complete_onboarding(self):
        """Sign in, then save the credentials and download folder"""
        if self.controller.busy:
            return
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        download_path = self.path_entry.get().strip()

        if not username or not password:
            self.message_label.configure(text="Please enter both username and password.", text_color="#e5534b")
            return

        if not download_path:
            self.message_label.configure(text="Please choose a download location.", text_color="#e5534b")
            return

        # Create download directory if it doesn't exist
        try:
            os.makedirs(download_path, exist_ok=True)
        except OSError as e:
            self.message_label.configure(text=f"Could not create the download folder: {e}", text_color="#e5534b")
            return

        self.controller.username = username
        self.controller.password = password
        self.message_label.configure(text="Signing in…", text_color=MUTED_TEXT)

        def signed_in():
            save_credentials(username, password)
            self.controller.settings["download_path"] = download_path
            self.controller.save_app_settings()
            self.message_label.configure(text="")
            self.controller.show_frame("HomeFrame")

        def failed(error):
            self.message_label.configure(text=f"Sign-in failed: {error}", text_color="#e5534b")

        self.controller.sign_in(on_success=signed_in, on_failure=failed)

    def on_busy_changed(self, busy):
        self.start_btn.configure(state="disabled" if busy else "normal")


class HomeFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self._sign_in_attempted = False

        # Configure grid for responsiveness
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(self, height=80, corner_radius=0, fg_color=ACCENT)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="📚 CMS Downloader Dashboard",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="white"
        )
        title.grid(row=0, column=0, pady=20)

        # Main content area
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=40, pady=30)
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)

        # Welcome message
        welcome_frame = ctk.CTkFrame(content)
        welcome_frame.grid(row=0, column=0, sticky="ew", pady=(0, 24))
        welcome_frame.grid_columnconfigure(0, weight=1)

        self.welcome_text = ctk.CTkLabel(
            welcome_frame,
            text="Welcome back! 👋",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.welcome_text.grid(row=0, column=0, pady=(14, 2), sticky="w", padx=20)

        self.account_label = ctk.CTkLabel(welcome_frame, text="", text_color=MUTED_TEXT, anchor="w", justify="left")
        self.account_label.grid(row=1, column=0, pady=(0, 14), sticky="w", padx=20)

        self.retry_btn = ctk.CTkButton(welcome_frame, text="Retry", width=80, command=self.retry_sign_in)

        # Action cards
        cards_frame = ctk.CTkFrame(content, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="nsew")

        # Configure grid
        cards_frame.grid_columnconfigure(0, weight=1)
        cards_frame.grid_columnconfigure(1, weight=1)
        cards_frame.grid_rowconfigure(0, weight=1)
        cards_frame.grid_rowconfigure(1, weight=1)

        # Card 1: Download Courses
        download_card = self.create_action_card(
            cards_frame,
            "📥 Download Courses",
            "Browse and download course materials",
            lambda: controller.show_frame("DownloadFrame")
        )
        download_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Card 2: Sync All
        sync_card = self.create_action_card(
            cards_frame,
            "🔄 Sync All Courses",
            "Update every course in your sync list",
            self.sync_all_courses
        )
        sync_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        # Card 3: Settings
        settings_card = self.create_action_card(
            cards_frame,
            "⚙️ Settings",
            "Manage credentials and preferences",
            lambda: controller.show_frame("SettingsFrame")
        )
        settings_card.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # Card 4: About
        about_card = self.create_action_card(
            cards_frame,
            "ℹ️ About",
            "Learn more about this application",
            self.show_about
        )
        about_card.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")

    def create_action_card(self, parent, title, description, command):
        """Create a clickable action card"""
        card = ctk.CTkButton(
            parent,
            text=f"{title}\n\n{description}",
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=command,
            height=120,
            corner_radius=10,
            anchor="center"
        )

        return card

    def set_account_status(self, text, ok=None):
        self.account_label.configure(text=text)
        if ok is False:
            self.retry_btn.grid(row=0, column=1, rowspan=2, padx=20)
        else:
            self.retry_btn.grid_forget()

    def retry_sign_in(self):
        if not self.controller.busy:
            self.controller.sign_in()

    def sync_all_courses(self):
        """Sync all courses from courses.json"""
        courses = load_course_definitions()
        if not courses:
            messagebox.showinfo(
                "Nothing to sync",
                "Your sync list is empty.\n\nOpen 'Download Courses', tick the courses you want to keep "
                f"up to date and press 'Save as sync list'.\n\n(It's stored in {courses_file_path()})"
            )
            return

        count = len(group_courses(courses))
        if not messagebox.askyesno("Confirm Sync", f"This will sync {count} course(s). Continue?"):
            return

        download_frame = self.controller.frames["DownloadFrame"]

        def start():
            if download_frame.start_sync(courses):
                self.controller.show_frame("DownloadFrame")

        self.controller.ensure_session(start)

    def show_about(self):
        """Show about dialog"""
        about_text = f"""
GUC CMS Downloader v{__version__}
📚 Easily download course materials from GUC CMS

Created for students at the German University in Cairo

Features:
• Automatic course material downloads
• Courses you took more than once are merged into one folder
• Batch course syncing
• Progress tracking
• Credential management

© 2025 - Open Source Project
        """
        messagebox.showinfo("About CMS Downloader", about_text)

    def on_show(self):
        """Called when frame is shown"""
        if self.controller.username:
            self.welcome_text.configure(text=f"Welcome back, {self.controller.username}! 👋")
        # Sign in once in the background; failures show a Retry button
        if (
            not self._sign_in_attempted
            and self.controller.session is None
            and self.controller.username
            and not self.controller.busy
        ):
            self._sign_in_attempted = True
            self.controller.sign_in()


class DownloadFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.rows = {}  # course key -> widgets and data for one course in the list
        self.selection = {}  # course key -> BooleanVar; survives refreshes and filtering
        self.labels = {}  # season id -> "Semester N" label
        self._preselected = False

        # Configure grid for responsiveness
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        create_header(self, controller, "📥 Download Course Materials")

        # Main content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(14, 16))
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)

        # Top controls
        controls = ctk.CTkFrame(content, fg_color="transparent")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        controls.grid_columnconfigure(3, weight=1)

        self.fetch_btn = ctk.CTkButton(controls, text="🔄 Refresh", width=110, height=34, command=self.fetch_courses)
        self.fetch_btn.grid(row=0, column=0, padx=(0, 8))

        select_all_btn = ctk.CTkButton(
            controls, text="✓ Select All", width=100, height=34, fg_color="gray", command=self.select_all
        )
        select_all_btn.grid(row=0, column=1, padx=(0, 8))

        deselect_all_btn = ctk.CTkButton(
            controls, text="✗ Clear", width=80, height=34, fg_color="gray", command=self.deselect_all
        )
        deselect_all_btn.grid(row=0, column=2, padx=(0, 8))

        self.search_entry = ctk.CTkEntry(controls, placeholder_text="Search name or code…", height=34)
        self.search_entry.grid(row=0, column=3, sticky="ew", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda event: self.apply_filter())

        self.semester_var = ctk.StringVar(value=ALL_SEMESTERS)
        self.semester_menu = ctk.CTkOptionMenu(
            controls,
            values=[ALL_SEMESTERS],
            variable=self.semester_var,
            width=190,
            height=34,
            dynamic_resizing=False,
            command=lambda value: self.apply_filter(),
        )
        self.semester_menu.grid(row=0, column=4)

        # Scrollable frame for courses
        self.courses_scroll = ScrollableFrame(
            content,
            label_text="Available Courses",
            label_font=ctk.CTkFont(size=15, weight="bold")
        )
        self.courses_scroll.grid(row=1, column=0, sticky="nsew")

        self.empty_label = ctk.CTkLabel(self.courses_scroll, text="", text_color=MUTED_TEXT)
        self.empty_label.pack(pady=30)

        # Progress and status
        self.status_label = ctk.CTkLabel(content, text="Ready to download", anchor="w", font=ctk.CTkFont(size=13))
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(10, 2))

        self.progress_bar = ctk.CTkProgressBar(content, height=10)
        self.progress_bar.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        self.progress_bar.set(0)

        self.file_label = ctk.CTkLabel(content, text="", anchor="w", text_color=MUTED_TEXT, font=ctk.CTkFont(size=12))
        self.file_label.grid(row=4, column=0, sticky="ew")
        self.file_label.grid_remove()  # only shown while downloading

        # Log of what the downloader is doing
        log_header = ctk.CTkFrame(content, fg_color="transparent")
        log_header.grid(row=5, column=0, sticky="ew", pady=(4, 2))
        log_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_header, text="Log", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.log_toggle = ctk.CTkButton(
            log_header, text="Show", width=60, height=22, fg_color="gray", command=self.toggle_log
        )
        self.log_toggle.grid(row=0, column=1)

        self.log_box = ctk.CTkTextbox(content, height=110, wrap="word", font=monospace_font(11), state="disabled")
        self.log_box.grid(row=6, column=0, sticky="ew", pady=(0, 10))
        self.log_box.grid_remove()  # opens by itself when a download starts

        # Buttons
        buttons = ctk.CTkFrame(content, fg_color="transparent")
        buttons.grid(row=7, column=0, sticky="ew")
        buttons.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(
            buttons,
            text="⬇️ Download Selected Courses",
            height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.download_selected
        )
        self.download_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            buttons, text="⏹ Stop", width=90, height=44, fg_color="#c0392b", hover_color="#962d22",
            state="disabled", command=self.stop
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, 8))

        open_btn = ctk.CTkButton(buttons, text="📂 Open Folder", width=120, height=44, fg_color="gray",
                                 command=self.open_download_folder)
        open_btn.grid(row=0, column=2, padx=(0, 8))

        self.save_list_btn = ctk.CTkButton(buttons, text="💾 Save as Sync List", width=150, height=44, fg_color="gray",
                                           command=self.save_sync_list)
        self.save_list_btn.grid(row=0, column=3)

    # --- Showing the course list ----------------------------------------------------------

    def on_show(self):
        """Called when frame is shown"""
        # Auto-fetch courses if list is empty, once whatever is running (like signing in) is done
        if not self.rows:
            self.after(100, self._fetch_when_idle)

    def _fetch_when_idle(self):
        if self.rows or self.controller.current_frame != "DownloadFrame":
            return
        if self.controller.busy:
            self.after(300, self._fetch_when_idle)
        else:
            self.fetch_courses()

    def fetch_courses(self):
        """Fetch available courses from CMS"""
        if self.controller.busy:
            return

        def fetch():
            session = self.controller.session
            self.status_label.configure(text="Fetching courses from CMS…")
            self._indeterminate(True)
            self.controller.run_task(
                lambda: get_course_list(session, verbose=False),
                self.display_courses,
                self._fetch_failed,
            )

        self.controller.ensure_session(fetch)

    def _fetch_failed(self, error):
        self._indeterminate(False)
        self.status_label.configure(text="Failed to fetch courses")
        messagebox.showerror("Error", f"Failed to fetch courses: {error}")

    def display_courses(self, courses):
        """Display courses in the scrollable frame, one row per course (repeated takes merged)"""
        self._indeterminate(False)
        self.controller.courses = courses
        self.labels = semester_labels(courses)
        groups = group_courses(courses)

        for row in self.rows.values():
            row["frame"].destroy()
        self.rows = {}

        # Tick the courses from the sync list the first time
        if not self._preselected:
            self._preselected = True
            saved = {course_key(course) for course in load_course_definitions()}
            for group in groups:
                if group["key"] in saved:
                    self._selection_var(group["key"]).set(True)

        for group in groups:
            self.rows[group["key"]] = self._create_row(group)

        # Newest semester first in the filter
        semester_options = [ALL_SEMESTERS] + list(reversed(list(self.labels.values())))
        self.semester_menu.configure(values=semester_options)
        if self.semester_var.get() not in semester_options:
            self.semester_var.set(ALL_SEMESTERS)

        self.apply_filter()
        merged = len(courses) - len(groups)
        note = f" ({merged} repeated takes merged)" if merged else ""
        self.status_label.configure(text=f"Found {len(groups)} courses across {len(self.labels)} semesters{note}")
        self._update_download_button()

    def _selection_var(self, key):
        if key not in self.selection:
            var = ctk.BooleanVar(value=False)
            var.trace_add("write", lambda *args: self._update_download_button())
            self.selection[key] = var
        return self.selection[key]

    def _create_row(self, group):
        takes = group["takes"]
        take_labels = [self.labels.get(season_id_of(take), "") for take in takes]
        home = group.get("semester") or (take_labels[-1] if take_labels else "")
        details = [group["id"]] if group["id"] else []
        if home:
            details.append(home)
        others = [label for label in dict.fromkeys(take_labels) if label and label != home]
        if others:
            details.append("also taken in " + ", ".join(others))
        if all(take.get("canceled") for take in takes):
            details.append("canceled")

        row_frame = ctk.CTkFrame(self.courses_scroll)
        var = self._selection_var(group["key"])
        checkbox = ctk.CTkCheckBox(row_frame, text=group["name"], variable=var, font=ctk.CTkFont(size=13))
        checkbox.pack(side="left", padx=10, pady=8)
        detail_label = ctk.CTkLabel(row_frame, text="  ·  ".join(details), text_color=MUTED_TEXT,
                                    font=ctk.CTkFont(size=12))
        detail_label.pack(side="right", padx=12)
        # Clicking anywhere on the row toggles it
        for widget in (row_frame, detail_label):
            widget.bind("<Button-1>", lambda event, v=var: v.set(not v.get()))

        search_text = " ".join([group["name"], group["id"], *take_labels, *(t.get("title", "") for t in takes)])
        return {
            "frame": row_frame,
            "group": group,
            "search": search_text.casefold(),
            "semesters": set(take_labels),
        }

    def apply_filter(self):
        """Show only the courses matching the search text and semester filter"""
        query = self.search_entry.get().strip().casefold()
        semester = self.semester_var.get()
        visible = 0
        for row in self.rows.values():
            row["frame"].pack_forget()
        for row in self.rows.values():
            if (not query or query in row["search"]) and (semester == ALL_SEMESTERS or semester in row["semesters"]):
                row["frame"].pack(fill="x", pady=3, padx=4)
                visible += 1
        if self.rows and not visible:
            self.empty_label.configure(text="No courses match your search")
            self.empty_label.pack(pady=30)
        elif not self.rows:
            self.empty_label.configure(text="Press Refresh to load your courses")
            self.empty_label.pack(pady=30)
        else:
            self.empty_label.pack_forget()

    def _visible_rows(self):
        return [row for row in self.rows.values() if row["frame"].winfo_manager()]

    def select_all(self):
        """Select all courses currently shown"""
        for row in self._visible_rows():
            self.selection[row["group"]["key"]].set(True)

    def deselect_all(self):
        """Deselect all courses currently shown"""
        for row in self._visible_rows():
            self.selection[row["group"]["key"]].set(False)

    def _selected_groups(self):
        return [row["group"] for key, row in self.rows.items() if self.selection[key].get()]

    def _update_download_button(self):
        if self.controller.busy:
            return
        count = len(self._selected_groups())
        text = f"⬇️ Download {count} Selected Course{'s' if count != 1 else ''}" if count else "⬇️ Download Selected Courses"
        self.download_btn.configure(text=text)

    # --- Downloading ----------------------------------------------------------------------

    def download_selected(self):
        """Download selected courses"""
        selected = self._selected_groups()
        if not selected:
            messagebox.showwarning("Warning", "Please select at least one course!")
            return
        self.controller.ensure_session(lambda: self.start_download(lambda: selected))

    def start_sync(self, saved_courses):
        """Sync the courses from courses.json, refreshed with the current list from the CMS"""
        session = self.controller.session

        def prepare():
            try:
                current = get_course_list(session, verbose=False)
            except Exception as e:
                print(f"⚠️ Could not refresh the course list ({e}), using courses.json as it is")
                current = []
            if current and not self.rows:
                self.controller.post(self.display_courses, current)
            return group_courses(refresh_course_definitions(saved_courses, current))

        return self.start_download(prepare)

    def start_download(self, prepare):
        """Start downloading in the background; prepare() returns the courses (merged groups) to download"""
        settings = self.controller.settings
        download_path = settings["download_path"]
        try:
            os.makedirs(download_path, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Error", f"Could not create the download folder {download_path}: {e}")
            return False

        session = self.controller.session
        hooks = self.controller.make_hooks(self._on_file_progress)
        delay = int(settings.get("delay", 1))
        by_semester = bool(settings.get("by_semester", False))

        def download_task():
            groups = prepare()
            totals, failed = Counter(), []
            for i, group in enumerate(groups, 1):
                hooks.check_cancel()
                self.controller.post(self._on_course_started, i, len(groups), group["name"])
                takes = len(group["takes"])
                print(f"\n⚙️ {group['name']}" + (f" (taken {takes} times, merged)" if takes > 1 else ""))
                try:
                    stats = download_course_group(
                        session, group, delay=delay, output=download_path, by_semester=by_semester, hooks=hooks
                    )
                except DownloadCancelled:
                    raise
                except Exception as e:
                    print(f"❌ Failed to download {group['name']}: {e}")
                    failed.append(group["name"])
                    continue
                print(f"   {describe_stats(stats)}")
                totals.update(stats)
            return totals, failed

        self.status_label.configure(text="Starting…")
        self.progress_bar.set(0)
        self.file_label.grid()
        self.set_log_visible(True)
        return self.controller.run_task(download_task, self.download_complete, self._download_failed)

    def _on_course_started(self, index, total, name):
        self.status_label.configure(text=f"Course {index} of {total}: {name}")
        self.progress_bar.set((index - 1) / total)
        self._course_progress = (index - 1, total)
        self.file_label.configure(text="")

    def _on_file_progress(self, name, done, total):
        if total:
            percent = min(done / total, 1.0)
            self.file_label.configure(text=f"{name} — {percent:.0%} of {format_size(total)}")
            finished, courses = getattr(self, "_course_progress", (0, 1))
            self.progress_bar.set((finished + percent) / courses)
        else:
            self.file_label.configure(text=f"{name} — {format_size(done)}")

    def download_complete(self, result):
        """Called when download is complete"""
        totals, failed = result
        summary = describe_stats(totals)
        self.progress_bar.set(1.0)
        self.file_label.grid_remove()
        if failed:
            self.status_label.configure(text=f"⚠️ Finished with problems: {summary}")
            messagebox.showwarning(
                "Finished with problems",
                f"{summary}\n\nCould not download: {', '.join(failed)}\n\nThe log shows the details."
            )
        else:
            self.status_label.configure(text=f"✅ Done: {summary}")
            if totals["failed"] or totals["unmatched"]:
                messagebox.showwarning("Finished", f"{summary}\n\nThe log shows the details.")
            else:
                messagebox.showinfo("Success", f"All courses are up to date! 🎉\n\n{summary}")
        self.after(2000, lambda: self.progress_bar.set(0))

    def _download_failed(self, error):
        self.file_label.grid_remove()
        self.progress_bar.set(0)
        if isinstance(error, DownloadCancelled):
            self.status_label.configure(text="⏹ Stopped")
            print("\n⏹ Stopped")
        else:
            self.status_label.configure(text="Download failed")
            messagebox.showerror("Download Error", str(error))

    def stop(self):
        self.status_label.configure(text="Stopping…")
        self.controller.stop()

    def on_busy_changed(self, busy):
        state = "disabled" if busy else "normal"
        self.download_btn.configure(state=state)
        self.fetch_btn.configure(state=state)
        self.save_list_btn.configure(state=state)
        self.stop_btn.configure(state="normal" if busy else "disabled")
        if busy:
            self.download_btn.configure(text="⏳ Working…")
        else:
            self._indeterminate(False)
            self._update_download_button()

    def _indeterminate(self, on):
        if on:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)

    # --- Other actions --------------------------------------------------------------------

    def open_download_folder(self):
        path = self.controller.settings["download_path"]
        try:
            os.makedirs(path, exist_ok=True)
            open_in_file_manager(path)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open {path}: {e}")

    def save_sync_list(self):
        """Save the selected courses to courses.json, used by 'Sync All Courses' and main.py --sync"""
        selected = self._selected_groups()
        if not selected:
            messagebox.showwarning("Warning", "Tick the courses you want in your sync list first.")
            return
        path = courses_file_path()
        if os.path.exists(path) and not messagebox.askyesno(
            "Save Sync List", f"Replace your sync list with the {len(selected)} selected course(s)?\n\n{path}"
        ):
            return
        entries = [take for group in selected for take in group["takes"]]
        try:
            save_course_definitions(entries, path)
        except OSError as e:
            messagebox.showerror("Error", f"Could not save {path}: {e}")
            return
        messagebox.showinfo("Saved", f"Saved {len(selected)} course(s) to your sync list.\n\n{path}")

    def toggle_log(self):
        self.set_log_visible(not self.log_box.winfo_manager())

    def set_log_visible(self, visible):
        if visible:
            self.log_box.grid()
            self.log_toggle.configure(text="Hide")
        else:
            self.log_box.grid_remove()
            self.log_toggle.configure(text="Show")

    def append_log(self, text):
        text = text.replace("\r", "")
        if not text:
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 3000:
            self.log_box.delete("1.0", f"{lines - 3000}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


class ManualFixDialog(ctk.CTkToplevel):
    """Lets you line up material links with their names when the CMS page can't be read automatically.

    Works on the course's MANUAL_FIX file, so the result is the same as editing that file by hand.
    """

    def __init__(self, master, manual_file_path, on_close):
        super().__init__(master)
        self.title("Fix material names")
        # Centered over the main window; customtkinter scales the size but not the position
        width, height, scaling = 860, 540, self._get_window_scaling()
        x = master.winfo_rootx() + (master.winfo_width() - width * scaling) / 2
        y = master.winfo_rooty() + (master.winfo_height() - height * scaling) / 2
        self.geometry(f"{width}x{height}+{max(int(x), 0)}+{max(int(y), 0)}")
        self.minsize(680, 420)
        self._path = manual_file_path
        self._on_close = on_close
        self._closed = False
        master.open_dialog = self

        links, names, self._ignored = read_manual_fix_file(manual_file_path)
        self._link_for_label = {}
        link_labels = []
        for link in links:
            label = link.replace("\\", "/").rsplit("/", 1)[-1] or link
            if label in self._link_for_label:  # keep what's shown unique
                label = link
            self._link_for_label[label] = link
            link_labels.append(label)

        self.grid_columnconfigure((0, 1), weight=1, uniform="columns")
        self.grid_rowconfigure(3, weight=1)

        course = os.path.basename(os.path.dirname(manual_file_path))
        ctk.CTkLabel(self, text=f"Fix material names — {course}", font=ctk.CTkFont(size=18, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            self,
            text=("The links and names on this course's page don't line up (a title was probably written "
                  "in an unusual way). Edit the lists so that line N on the left belongs to line N on the "
                  "right. Delete a link you don't want: it will be skipped from now on."),
            anchor="w", justify="left", wraplength=800, text_color=MUTED_TEXT,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 10))

        self.links_title = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.links_title.grid(row=2, column=0, sticky="ew", padx=(20, 6))
        self.names_title = ctk.CTkLabel(self, text="", anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.names_title.grid(row=2, column=1, sticky="ew", padx=(6, 20))

        self.links_box = ctk.CTkTextbox(self, wrap="none", font=monospace_font(12))
        self.links_box.grid(row=3, column=0, sticky="nsew", padx=(20, 6), pady=(4, 10))
        self.names_box = ctk.CTkTextbox(self, wrap="none", font=monospace_font(12))
        self.names_box.grid(row=3, column=1, sticky="nsew", padx=(6, 20), pady=(4, 10))
        self.links_box.insert("1.0", "\n".join(link_labels))
        self.names_box.insert("1.0", "\n".join(names))

        for box in (self.links_box, self.names_box):
            box.bind("<KeyRelease>", lambda event: self._update_counts())
            # Scroll both lists together so the lines stay side by side
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                box.bind(sequence, self._scroll_both)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 16))
        buttons.grid_columnconfigure(0, weight=1)
        self.hint_label = ctk.CTkLabel(buttons, text="", anchor="w")
        self.hint_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(buttons, text="Skip These", width=110, fg_color="gray", command=lambda: self.close(False)).grid(
            row=0, column=1, padx=(8, 8)
        )
        self.save_btn = ctk.CTkButton(buttons, text="Save & Continue", width=150, command=self.save)
        self.save_btn.grid(row=0, column=2)

        self._update_counts()
        self.protocol("WM_DELETE_WINDOW", lambda: self.close(False))
        self.transient(master)
        self.after(150, self._bring_to_front)
        self.after(300, lambda: set_window_icon(self))  # after customtkinter has set its own icon

    def _bring_to_front(self):
        if self._closed:
            return
        self.deiconify()
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:  # not viewable yet
            self.after(150, self._bring_to_front)

    def _lines(self, box):
        return [line.strip() for line in box.get("1.0", "end").splitlines() if line.strip()]

    def _update_counts(self):
        links, names = len(self._lines(self.links_box)), len(self._lines(self.names_box))
        self.links_title.configure(text=f"Links ({links})")
        self.names_title.configure(text=f"Names ({names})")
        if links == names:
            self.hint_label.configure(text="✓ The lists match", text_color=("#2d7d46", "#57ab5a"))
            self.save_btn.configure(state="normal")
        else:
            self.hint_label.configure(text=f"{abs(links - names)} line(s) off — make both lists the same length",
                                      text_color=("#c0392b", "#e5534b"))
            self.save_btn.configure(state="disabled")

    def _scroll_both(self, event):
        step = -1 if (getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0) else 1
        for box in (self.links_box, self.names_box):
            box.yview("scroll", step * 3, "units")
        return "break"

    def save(self):
        links = [self._link_for_label.get(line, line) for line in self._lines(self.links_box)]
        names = self._lines(self.names_box)
        if len(links) != len(names):
            return
        unknown = [line for line in links if line not in self._link_for_label.values() and "/" not in line]
        if unknown:
            messagebox.showerror("Unknown link", f"This line isn't one of the course's links:\n\n{unknown[0]}", parent=self)
            return
        try:
            write_manual_fix_file(self._path, links, names, self._ignored)
        except OSError as e:
            messagebox.showerror("Error", f"Could not save {self._path}: {e}", parent=self)
            return
        self.close(True)

    def close(self, saved):
        if self._closed:
            return
        self._closed = True
        if self.master.open_dialog is self:
            self.master.open_dialog = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self._on_close(saved)


class SettingsFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Configure grid for responsiveness
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        create_header(self, controller, "⚙️ Settings")

        # Content - Scrollable
        content = ScrollableFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=30, pady=20)
        content.grid_columnconfigure(0, weight=1)

        # Credentials section
        cred_section = ctk.CTkFrame(content)
        cred_section.grid(row=0, column=0, sticky="ew", pady=(0, 16), ipady=8)

        cred_title = ctk.CTkLabel(
            cred_section,
            text="Account Credentials",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        cred_title.pack(anchor="w", padx=20, pady=(15, 10))

        # Username
        username_label = ctk.CTkLabel(cred_section, text="Username:", font=ctk.CTkFont(size=13))
        username_label.pack(anchor="w", padx=20, pady=(4, 5))

        self.username_entry = ctk.CTkEntry(cred_section, width=400, height=35)
        self.username_entry.pack(anchor="w", padx=20, pady=(0, 10))

        # Password
        password_label = ctk.CTkLabel(cred_section, text="Password:", font=ctk.CTkFont(size=13))
        password_label.pack(anchor="w", padx=20, pady=(4, 5))

        self.password_entry = ctk.CTkEntry(cred_section, width=400, height=35, show="*")
        self.password_entry.pack(anchor="w", padx=20, pady=(0, 15))

        # Download settings section
        path_section = ctk.CTkFrame(content)
        path_section.grid(row=1, column=0, sticky="ew", pady=(0, 16), ipady=8)

        path_title = ctk.CTkLabel(
            path_section,
            text="Download Settings",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        path_title.pack(anchor="w", padx=20, pady=(15, 10))

        path_label = ctk.CTkLabel(path_section, text="Download Location:", font=ctk.CTkFont(size=13))
        path_label.pack(anchor="w", padx=20, pady=(4, 5))

        path_frame = ctk.CTkFrame(path_section, fg_color="transparent")
        path_frame.pack(anchor="w", padx=20, pady=(0, 12), fill="x")

        self.path_entry = ctk.CTkEntry(path_frame, width=420, height=35)
        self.path_entry.pack(side="left", padx=(0, 10))

        browse_btn = ctk.CTkButton(
            path_frame,
            text="Browse",
            width=80,
            height=35,
            command=self.browse_folder
        )
        browse_btn.pack(side="left")

        delay_label = ctk.CTkLabel(
            path_section, text="Delay between requests (seconds, be kind to the CMS):", font=ctk.CTkFont(size=13)
        )
        delay_label.pack(anchor="w", padx=20, pady=(4, 5))
        self.delay_entry = ctk.CTkEntry(path_section, width=80, height=35)
        self.delay_entry.pack(anchor="w", padx=20, pady=(0, 12))

        self.by_semester_var = ctk.BooleanVar(value=False)
        by_semester_switch = ctk.CTkSwitch(
            path_section,
            text="Put courses in semester folders (Semester 1, Semester 2 - Summer, …)",
            variable=self.by_semester_var,
        )
        by_semester_switch.pack(anchor="w", padx=20, pady=(4, 4))
        ctk.CTkLabel(
            path_section,
            text="Existing course folders are moved when you switch, not downloaded again.",
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # Appearance section
        appearance_section = ctk.CTkFrame(content)
        appearance_section.grid(row=2, column=0, sticky="ew", ipady=8)

        appearance_title = ctk.CTkLabel(
            appearance_section,
            text="Appearance",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        appearance_title.pack(anchor="w", padx=20, pady=(15, 10))

        theme_label = ctk.CTkLabel(appearance_section, text="Theme:", font=ctk.CTkFont(size=13))
        theme_label.pack(anchor="w", padx=20, pady=(4, 5))

        self.theme_var = ctk.StringVar(value=self.controller.settings["theme"])
        theme_menu = ctk.CTkOptionMenu(
            appearance_section,
            values=["dark", "light", "system"],
            variable=self.theme_var,
            width=200,
            height=35,
            command=self.change_theme
        )
        theme_menu.pack(anchor="w", padx=20, pady=(0, 15))

        # Save button
        self.save_btn = ctk.CTkButton(
            content,
            text="💾 Save Settings",
            height=45,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.save_settings
        )
        self.save_btn.grid(row=3, column=0, sticky="ew", pady=(20, 10))

    def on_show(self):
        """Load current settings when shown"""
        settings = self.controller.settings
        self.username_entry.delete(0, "end")
        self.username_entry.insert(0, self.controller.username or "")
        self.password_entry.delete(0, "end")
        self.password_entry.insert(0, self.controller.password or "")

        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, settings["download_path"])
        self.delay_entry.delete(0, "end")
        self.delay_entry.insert(0, str(settings.get("delay", 1)))
        self.by_semester_var.set(bool(settings.get("by_semester", False)))
        self.theme_var.set(settings["theme"])

    def browse_folder(self):
        """Browse for download folder"""
        folder = filedialog.askdirectory(initialdir=self.path_entry.get() or str(Path.home()))
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, os.path.normpath(folder))

    def change_theme(self, theme):
        """Change application theme"""
        ctk.set_appearance_mode(theme)

    def save_settings(self):
        """Save settings"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        download_path = self.path_entry.get().strip()

        if not username or not password:
            messagebox.showerror("Error", "Username and password cannot be empty!")
            return

        if not download_path:
            messagebox.showerror("Error", "Download path cannot be empty!")
            return

        try:
            delay = int(self.delay_entry.get().strip())
            if delay < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "The delay must be a whole number of seconds (0 or more).")
            return

        # Create directory if it doesn't exist
        try:
            os.makedirs(download_path, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Invalid download path: {e}")
            return

        settings = self.controller.settings
        settings.update(download_path=download_path, delay=delay, by_semester=self.by_semester_var.get(),
                        theme=self.theme_var.get())
        self.controller.save_app_settings()

        credentials_changed = (username, password) != (self.controller.username, self.controller.password)
        if not credentials_changed:
            messagebox.showinfo("Success", "Settings saved successfully! ✅")
            return

        self.controller.username = username
        self.controller.password = password
        save_credentials(username, password)

        # Re-authenticate with the new credentials
        self.controller.session = None
        if self.controller.busy:
            messagebox.showinfo("Success", "Settings saved. The new credentials are used once the current task is done.")
        else:
            self.controller.sign_in(
                on_success=lambda: messagebox.showinfo("Success", "Settings saved successfully! ✅"),
                on_failure=lambda e: messagebox.showerror(
                    "Error", f"Settings saved but authentication failed. Please check credentials.\n\n{e}"
                ),
            )


def main():
    settings = {**DEFAULT_SETTINGS, **load_settings()}
    ctk.set_appearance_mode(settings["theme"])
    ctk.set_default_color_theme("blue")
    app = CMSDownloaderApp(settings)
    app.mainloop()
