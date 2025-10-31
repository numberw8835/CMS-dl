import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import json
import os
import threading
from pathlib import Path
from cms_auth import authenticate
from cms_config import load_credentials, save_credentials, load_course_definitions
from cms_modules import download_course, get_course_list

# Set appearance and theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class CMSDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("GUC CMS Downloader 📚")
        self.geometry("900x650")
        self.minsize(800, 600)  # Set minimum window size
        self.resizable(True, True)
        
        # App state
        self.session = None
        self.username = None
        self.password = None
        self.courses = []
        self.selected_courses = []
        self.download_path = str(Path.home() / "Downloads" / "CMS_Courses")
        
        # Check if credentials exist
        self.credentials_exist = self.check_credentials()
        
        # Container for all frames
        self.container = ctk.CTkFrame(self)
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
        
        # Show appropriate starting frame
        if self.credentials_exist:
            self.show_frame("HomeFrame")
        else:
            self.show_frame("OnboardingFrame")
    
    def check_credentials(self):
        """Check if credentials are saved"""
        try:
            username, password = load_credentials()
            if username and password:
                self.username = username
                self.password = password
                return True
        except:
            pass
        return False
    
    def show_frame(self, frame_name):
        """Show the requested frame"""
        frame = self.frames[frame_name]
        frame.tkraise()
        # Call on_show if the frame has this method
        if hasattr(frame, 'on_show'):
            frame.on_show()
    
    def authenticate_user(self):
        """Authenticate with CMS"""
        try:
            self.session = authenticate(self.username, self.password)
            return True
        except Exception as e:
            messagebox.showerror("Authentication Error", str(e))
            return False


class OnboardingFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        # Configure grid for responsiveness
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Scrollable container for content
        scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
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
            font=ctk.CTkFont(size=32, weight="bold")
        )
        title.pack(pady=(0, 10))
        
        subtitle = ctk.CTkLabel(
            main_frame,
            text="Let's get you set up in just a few steps",
            font=ctk.CTkFont(size=16),
            text_color="gray"
        )
        subtitle.pack(pady=(0, 40))
        
        # Credentials frame
        cred_frame = ctk.CTkFrame(main_frame)
        cred_frame.pack(pady=20, padx=40, fill="both")
        
        # Username
        username_label = ctk.CTkLabel(
            cred_frame,
            text="GUC Username 👤",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        username_label.pack(pady=(20, 5), anchor="w", padx=20)
        
        self.username_entry = ctk.CTkEntry(
            cred_frame,
            placeholder_text="Enter your GUC username",
            width=350,
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
            width=350,
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
            width=250,
            height=40
        )
        self.path_entry.insert(0, self.controller.download_path)
        self.path_entry.pack(side="left", padx=(0, 10))
        
        browse_btn = ctk.CTkButton(
            path_frame,
            text="Browse",
            width=90,
            height=40,
            command=self.browse_folder
        )
        browse_btn.pack(side="left")
        
        # Get Started button
        start_btn = ctk.CTkButton(
            main_frame,
            text="Get Started! 🚀",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=350,
            height=50,
            command=self.complete_onboarding
        )
        start_btn.pack(pady=(30, 20))
    
    def browse_folder(self):
        """Open folder browser"""
        folder = filedialog.askdirectory(initialdir=self.controller.download_path)
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
    
    def complete_onboarding(self):
        """Complete onboarding and save credentials"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        download_path = self.path_entry.get().strip()
        
        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password!")
            return
        
        if not download_path:
            messagebox.showerror("Error", "Please select a download location!")
            return
        
        # Create download directory if it doesn't exist
        try:
            os.makedirs(download_path, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create download directory: {e}")
            return
        
        # Update controller state
        self.controller.username = username
        self.controller.password = password
        self.controller.download_path = download_path
        
        # Save credentials
        save_credentials(username, password)
        
        # Try to authenticate
        if self.controller.authenticate_user():
            messagebox.showinfo("Success", "Setup complete! Welcome aboard! 🎉")
            self.controller.show_frame("HomeFrame")
        else:
            messagebox.showerror("Error", "Authentication failed. Please check your credentials.")


class HomeFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        # Configure grid for responsiveness
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(self, height=80, fg_color=("#3b8ed0", "#1f6aa5"))
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
        content.grid(row=1, column=0, sticky="nsew", padx=40, pady=40)
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)
        
        # Welcome message
        welcome_frame = ctk.CTkFrame(content)
        welcome_frame.grid(row=0, column=0, sticky="ew", pady=(0, 30))
        
        welcome_text = ctk.CTkLabel(
            welcome_frame,
            text=f"Welcome back! 👋",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        welcome_text.pack(pady=15, anchor="w", padx=20)
        
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
            "Update all courses from courses.json",
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
            fg_color=("#3b8ed0", "#1f6aa5"),
            hover_color=("#2e7ab8", "#164f7a"),
            command=command,
            height=150,
            corner_radius=10,
            anchor="center"
        )
        
        return card
    
    def sync_all_courses(self):
        """Sync all courses from courses.json"""
        try:
            courses = load_course_definitions()
            if not courses:
                messagebox.showinfo("Info", "No courses found in courses.json")
                return
            
            # Authenticate if needed
            if not self.controller.session:
                if not self.controller.authenticate_user():
                    return
            
            response = messagebox.askyesno(
                "Confirm Sync",
                f"This will sync {len(courses)} course(s). Continue?"
            )
            
            if response:
                self.controller.show_frame("DownloadFrame")
                download_frame = self.controller.frames["DownloadFrame"]
                download_frame.sync_courses(courses)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to sync courses: {e}")
    
    def show_about(self):
        """Show about dialog"""
        about_text = """
GUC CMS Downloader v2.0
📚 Easily download course materials from GUC CMS

Created for students at the German University in Cairo
        
Features:
• Automatic course material downloads
• Batch course syncing
• Progress tracking
• Credential management

© 2025 - Open Source Project
        """
        messagebox.showinfo("About CMS Downloader", about_text)
    
    def on_show(self):
        """Called when frame is shown"""
        # Authenticate if session doesn't exist
        if not self.controller.session and self.controller.username:
            self.controller.authenticate_user()


class DownloadFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.course_checkboxes = {}
        self.is_downloading = False
        self.all_courses = []  # Store all fetched courses
        self.available_semesters = []  # Store available semester IDs

        # Configure grid for responsiveness
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Header with back button
        header = ctk.CTkFrame(self, height=70, fg_color=("#3b8ed0", "#1f6aa5"))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        
        header_content = ctk.CTkFrame(header, fg_color="transparent")
        header_content.pack(fill="both", expand=True, padx=20, pady=10)
        
        back_btn = ctk.CTkButton(
            header_content,
            text="← Back",
            width=80,
            height=35,
            command=lambda: controller.show_frame("HomeFrame")
        )
        back_btn.pack(side="left", pady=10)
        
        title = ctk.CTkLabel(
            header_content,
            text="📥 Download Course Materials",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="white"
        )
        title.pack(side="left", padx=20, pady=10)
        
        # Main content
        content = ctk.CTkFrame(self)
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        content.grid_rowconfigure(2, weight=1)
        content.grid_columnconfigure(0, weight=1)
        
        # Top controls
        controls = ctk.CTkFrame(content, fg_color="transparent")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        fetch_btn = ctk.CTkButton(
            controls,
            text="🔄 Fetch Available Courses",
            height=40,
            command=self.fetch_courses
        )
        fetch_btn.pack(side="left", padx=(0, 10))
        
        select_all_btn = ctk.CTkButton(
            controls,
            text="✓ Select All",
            height=40,
            fg_color="gray",
            command=self.select_all
        )
        select_all_btn.pack(side="left", padx=(0, 10))
        
        deselect_all_btn = ctk.CTkButton(
            controls,
            text="✗ Deselect All",
            height=40,
            fg_color="gray",
            command=self.deselect_all
        )
        deselect_all_btn.pack(side="left")
        
        # Semester filter
        filter_frame = ctk.CTkFrame(content, fg_color="transparent")
        filter_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))

        filter_label = ctk.CTkLabel(
            filter_frame,
            text="Filter by Semester:",
            font=ctk.CTkFont(size=13)
        )
        filter_label.pack(side="left", padx=(0, 10))

        self.semester_var = ctk.StringVar(value="All Semesters")
        self.semester_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["All Semesters"],
            variable=self.semester_var,
            width=200,
            height=35,
            command=self.filter_by_semester
        )
        self.semester_menu.pack(side="left")

        # Course list frame with scrollbar
        list_frame = ctk.CTkFrame(content)
        list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 15))

        # Scrollable frame for courses
        self.courses_scroll = ctk.CTkScrollableFrame(
            list_frame,
            label_text="Available Courses",
            label_font=ctk.CTkFont(size=16, weight="bold")
        )
        self.courses_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Progress and status
        self.status_label = ctk.CTkLabel(
            content,
            text="Ready to download",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        
        self.progress_bar = ctk.CTkProgressBar(content)
        self.progress_bar.grid(row=3, column=0, sticky="ew", pady=(0, 15))
        self.progress_bar.set(0)
        
        # Download button
        self.download_btn = ctk.CTkButton(
            content,
            text="⬇️ Download Selected Courses",
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.download_selected
        )
        self.download_btn.grid(row=4, column=0, sticky="ew")
    
    def on_show(self):
        """Called when frame is shown"""
        # Auto-fetch courses if list is empty
        if not self.course_checkboxes:
            self.after(100, self.fetch_courses)
    
    def fetch_courses(self):
        """Fetch available courses from CMS"""
        if not self.controller.session:
            if not self.controller.authenticate_user():
                return
        
        self.status_label.configure(text="Fetching courses from CMS...")
        self.progress_bar.set(0.5)
        
        def fetch():
            try:
                courses = get_course_list(self.controller.session)
                self.after(0, lambda: self.display_courses(courses))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch courses: {e}"))
                self.after(0, lambda: self.status_label.configure(text="Failed to fetch courses"))
                self.after(0, lambda: self.progress_bar.set(0))
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def display_courses(self, courses):
        """Display courses in the scrollable frame"""
        # Store all courses
        self.all_courses = courses

        # Extract unique semester IDs
        semester_ids = set()
        for course in courses:
            sid = course.get('semester_id', '')
            if sid:
                semester_ids.add(sid)

        self.available_semesters = sorted(list(semester_ids))

        # Update semester dropdown
        semester_options = ["All Semesters"] + self.available_semesters
        self.semester_menu.configure(values=semester_options)
        self.semester_var.set("All Semesters")

        # Store courses
        self.controller.courses = courses

        # Display courses (initially all)
        self._display_filtered_courses(courses)

        self.status_label.configure(text=f"Found {len(courses)} courses across {len(self.available_semesters)} semesters")
        self.progress_bar.set(1.0)
        self.after(1000, lambda: self.progress_bar.set(0))

    def _display_filtered_courses(self, courses):
        """Helper method to display a filtered list of courses"""
        # Clear existing checkboxes
        for widget in self.courses_scroll.winfo_children():
            widget.destroy()
        self.course_checkboxes.clear()
        
        # Create checkboxes for each course
        for course in courses:
            var = ctk.BooleanVar(value=False)
            
            course_frame = ctk.CTkFrame(self.courses_scroll)
            course_frame.pack(fill="x", pady=5, padx=5)
            
            semester_info = f" [SID: {course.get('semester_id', 'N/A')}]"
            checkbox = ctk.CTkCheckBox(
                course_frame,
                text=f"{course['name']} (ID: {course['id']}){semester_info}",
                variable=var,
                font=ctk.CTkFont(size=13)
            )
            checkbox.pack(anchor="w", padx=10, pady=10)
            
            self.course_checkboxes[course['id']] = {
                'var': var,
                'course': course
            }

    def filter_by_semester(self, selected_semester):
        """Filter courses by selected semester ID"""
        if selected_semester == "All Semesters":
            filtered_courses = self.all_courses
        else:
            filtered_courses = [
                course for course in self.all_courses
                if course.get('semester_id') == selected_semester
            ]

        self._display_filtered_courses(filtered_courses)
        self.status_label.configure(
            text=f"Showing {len(filtered_courses)} courses for {selected_semester}"
        )

    def select_all(self):
        """Select all courses"""
        for item in self.course_checkboxes.values():
            item['var'].set(True)
    
    def deselect_all(self):
        """Deselect all courses"""
        for item in self.course_checkboxes.values():
            item['var'].set(False)
    
    def download_selected(self):
        """Download selected courses"""
        if self.is_downloading:
            messagebox.showwarning("Warning", "Download already in progress!")
            return
        
        selected = [
            item['course'] for item in self.course_checkboxes.values()
            if item['var'].get()
        ]
        
        if not selected:
            messagebox.showwarning("Warning", "Please select at least one course!")
            return
        
        self.start_download(selected)
    
    def sync_courses(self, courses):
        """Sync courses from courses.json"""
        self.start_download(courses, is_sync=True)
    
    def start_download(self, courses, is_sync=False):
        """Start downloading courses in background thread"""
        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="⏳ Downloading...")
        
        def download_task():
            total = len(courses)
            for i, course in enumerate(courses, 1):
                try:
                    course_url = course.get('url', '')
                    course_name = course.get('name', f"Course_{course.get('id', 'unknown')}")
                    
                    self.after(0, lambda c=course_name, i=i, t=total: 
                              self.status_label.configure(text=f"Downloading {i}/{t}: {c}"))
                    self.after(0, lambda i=i, t=total: self.progress_bar.set(i/t))
                    
                    download_course(
                        self.controller.session,
                        course_url,
                        course_name,
                        delay=1,
                        output=self.controller.download_path
                    )
                except Exception as e:
                    self.after(0, lambda c=course_name, e=e: 
                              messagebox.showerror("Download Error", f"Failed to download {c}: {e}"))
            
            # Download complete
            self.after(0, self.download_complete)
        
        threading.Thread(target=download_task, daemon=True).start()
    
    def download_complete(self):
        """Called when download is complete"""
        self.is_downloading = False
        self.download_btn.configure(state="normal", text="⬇️ Download Selected Courses")
        self.status_label.configure(text="✅ Download complete!")
        self.progress_bar.set(1.0)
        messagebox.showinfo("Success", "All courses downloaded successfully! 🎉")
        self.after(2000, lambda: self.progress_bar.set(0))


class SettingsFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        # Configure grid for responsiveness
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(self, height=70, fg_color=("#3b8ed0", "#1f6aa5"))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        
        header_content = ctk.CTkFrame(header, fg_color="transparent")
        header_content.pack(fill="both", expand=True, padx=20, pady=10)
        
        back_btn = ctk.CTkButton(
            header_content,
            text="← Back",
            width=80,
            height=35,
            command=lambda: controller.show_frame("HomeFrame")
        )
        back_btn.pack(side="left", pady=10)
        
        title = ctk.CTkLabel(
            header_content,
            text="⚙️ Settings",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="white"
        )
        title.pack(side="left", padx=20, pady=10)
        
        # Content - Scrollable
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=40, pady=40)
        content.grid_columnconfigure(0, weight=1)
        
        # Settings sections
        settings_container = ctk.CTkFrame(content)
        settings_container.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        settings_container.grid_columnconfigure(0, weight=1)
        
        # Credentials section
        cred_section = ctk.CTkFrame(settings_container)
        cred_section.grid(row=0, column=0, sticky="ew", pady=(0, 20), ipady=15)
        cred_section.grid_columnconfigure(0, weight=1)
        
        cred_title = ctk.CTkLabel(
            cred_section,
            text="Account Credentials",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        cred_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        # Username
        username_label = ctk.CTkLabel(cred_section, text="Username:", font=ctk.CTkFont(size=13))
        username_label.pack(anchor="w", padx=20, pady=(10, 5))
        
        self.username_entry = ctk.CTkEntry(cred_section, width=400, height=35)
        self.username_entry.pack(anchor="w", padx=20, pady=(0, 10))
        
        # Password
        password_label = ctk.CTkLabel(cred_section, text="Password:", font=ctk.CTkFont(size=13))
        password_label.pack(anchor="w", padx=20, pady=(10, 5))
        
        self.password_entry = ctk.CTkEntry(cred_section, width=400, height=35, show="*")
        self.password_entry.pack(anchor="w", padx=20, pady=(0, 15))
        
        # Download path section
        path_section = ctk.CTkFrame(settings_container)
        path_section.grid(row=1, column=0, sticky="ew", pady=(0, 20), ipady=15)
        path_section.grid_columnconfigure(0, weight=1)
        
        path_title = ctk.CTkLabel(
            path_section,
            text="Download Settings",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        path_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        path_label = ctk.CTkLabel(path_section, text="Download Location:", font=ctk.CTkFont(size=13))
        path_label.pack(anchor="w", padx=20, pady=(10, 5))
        
        path_frame = ctk.CTkFrame(path_section, fg_color="transparent")
        path_frame.pack(anchor="w", padx=20, pady=(0, 15))
        
        self.path_entry = ctk.CTkEntry(path_frame, width=350, height=35)
        self.path_entry.pack(side="left", padx=(0, 10))
        
        browse_btn = ctk.CTkButton(
            path_frame,
            text="Browse",
            width=80,
            height=35,
            command=self.browse_folder
        )
        browse_btn.pack(side="left")
        
        # Appearance section
        appearance_section = ctk.CTkFrame(settings_container)
        appearance_section.grid(row=2, column=0, sticky="ew", ipady=15)
        appearance_section.grid_columnconfigure(0, weight=1)
        
        appearance_title = ctk.CTkLabel(
            appearance_section,
            text="Appearance",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        appearance_title.pack(anchor="w", padx=20, pady=(15, 10))
        
        theme_label = ctk.CTkLabel(appearance_section, text="Theme:", font=ctk.CTkFont(size=13))
        theme_label.pack(anchor="w", padx=20, pady=(10, 5))
        
        self.theme_var = ctk.StringVar(value="dark")
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
        save_btn = ctk.CTkButton(
            content,
            text="💾 Save Settings",
            height=45,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.save_settings
        )
        save_btn.grid(row=1, column=0, sticky="ew", pady=(20, 0))
    
    def on_show(self):
        """Load current settings when shown"""
        if self.controller.username:
            self.username_entry.delete(0, "end")
            self.username_entry.insert(0, self.controller.username)
        
        if self.controller.password:
            self.password_entry.delete(0, "end")
            self.password_entry.insert(0, self.controller.password)
        
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, self.controller.download_path)
    
    def browse_folder(self):
        """Browse for download folder"""
        folder = filedialog.askdirectory(initialdir=self.controller.download_path)
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
    
    def change_theme(self, theme):
        """Change application theme"""
        ctk.set_appearance_mode(theme)
    
    def save_settings(self):
        """Save settings"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        download_path = self.path_entry.get().strip()
        
        if not username or not password:
            messagebox.showerror("Error", "Username and password cannot be empty!")
            return
        
        if not download_path:
            messagebox.showerror("Error", "Download path cannot be empty!")
            return
        
        # Create directory if it doesn't exist
        try:
            os.makedirs(download_path, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Invalid download path: {e}")
            return
        
        # Update controller
        self.controller.username = username
        self.controller.password = password
        self.controller.download_path = download_path
        
        # Save credentials
        save_credentials(username, password)
        
        # Re-authenticate if credentials changed
        self.controller.session = None
        if self.controller.authenticate_user():
            messagebox.showinfo("Success", "Settings saved successfully! ✅")
        else:
            messagebox.showerror("Error", "Settings saved but authentication failed. Please check credentials.")


def main():
    app = CMSDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
