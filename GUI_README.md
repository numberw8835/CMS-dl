# 🎨 CMS Downloader GUI

A modern, user-friendly graphical interface for the GUC CMS Downloader.

## ✨ Features

### 🎯 Onboarding Phase
- **Easy Setup**: First-time users are greeted with a clean onboarding screen
- **Credential Management**: Securely save your GUC credentials
- **Custom Download Path**: Choose where to save your course materials

### 🏠 Homepage
- **Dashboard View**: Clean and intuitive main navigation
- **Quick Actions**:
  - 📥 Download Courses - Browse and download individual courses
  - 🔄 Sync All Courses - Update all courses from `courses.json`
  - ⚙️ Settings - Manage your preferences
  - ℹ️ About - Learn more about the app

### 📥 Download Phase
- **Course Browser**: Fetch and view all available courses from CMS
- **Bulk Selection**: Select/deselect all courses with one click
- **Progress Tracking**: Real-time download progress with status updates
- **Background Downloads**: Download multiple courses without freezing the UI
- **Smart Sync**: Automatically sync courses defined in `courses.json`

### ⚙️ Settings
- **Account Management**: Update credentials anytime
- **Path Configuration**: Change download location
- **Theme Switcher**: Choose between dark, light, or system theme

## 🚀 Getting Started

### Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Run the GUI application:
```bash
python gui.py
```

### First Launch

On first launch, you'll be guided through the onboarding process:

1. **Enter Credentials**: Provide your GUC username and password
2. **Choose Download Location**: Select where course materials will be saved
3. **Get Started**: Click the button to complete setup and authenticate

Your credentials are saved securely in `~/.guc_account.json` for future use.

## 📖 Usage Guide

### Downloading Individual Courses

1. From the homepage, click **"📥 Download Courses"**
2. Click **"🔄 Fetch Available Courses"** to load your courses from CMS
3. Select the courses you want to download using checkboxes
4. Click **"⬇️ Download Selected Courses"**
5. Monitor progress in the progress bar

### Syncing All Courses

1. Create or update `courses.json` with your course definitions:
```json
[
  {
    "name": "Data Structures",
    "url": "https://cms.guc.edu.eg/courses/12345",
    "id": "12345"
  }
]
```

2. From the homepage, click **"🔄 Sync All Courses"**
3. Confirm the sync operation
4. All courses will be downloaded automatically

### Changing Settings

1. From the homepage, click **"⚙️ Settings"**
2. Update your credentials, download path, or theme
3. Click **"💾 Save Settings"**

## 🎨 Themes

The app supports three appearance modes:
- **Dark Mode** (default): Easy on the eyes for late-night studying
- **Light Mode**: Clean and bright interface
- **System**: Automatically matches your system theme

Change themes in the Settings page.

## 🔒 Security

- Credentials are stored in `~/.guc_account.json` in your home directory
- The file is only accessible to your user account
- Passwords are sent securely over HTTPS to the GUC CMS

## 🐛 Troubleshooting

### Authentication Failed
- Double-check your username and password
- Ensure you have internet connectivity
- Verify you can log in to CMS through the web browser

### Courses Not Fetching
- Make sure you're authenticated (credentials are correct)
- Check your internet connection
- Try logging out and back in through Settings

### Download Errors
- Ensure the download path exists and is writable
- Check available disk space
- Verify the course URLs are correct

## 💡 Tips

- Use **Select All** to quickly download all your courses at once
- The progress bar shows which course is currently downloading
- Downloads continue in the background - you can minimize the window
- Existing files are skipped automatically to avoid re-downloading

## 🆚 CLI vs GUI

Both interfaces are available:

- **CLI** (`main.py`): For automation, scripts, and advanced users
- **GUI** (`gui.py`): For easy, visual interaction

Choose whichever fits your workflow!

## 📝 Notes

- First-time setup is required before downloading
- Downloaded courses are organized in folders by course name
- The app remembers your settings between sessions
- You can switch between accounts anytime in Settings

## 🎓 Perfect for

- Students who want a simple way to download course materials
- Users who prefer visual interfaces over command-line tools
- Batch downloading multiple courses at once
- Keeping course materials up-to-date with sync feature

---

Enjoy your enhanced CMS downloading experience! 🚀
