# 📚 GUC CMS Downloader

🚀 **Easily download course materials** from the German University in Cairo's CMS, on Windows, Linux or macOS, with a simple app or from the command line.

## ⬇️ Download

Get the latest version from the [Releases page](https://github.com/numberw8835/CMS-dl/releases/latest), no Python needed.

### 🪟 Windows

1. Download `CMS-Downloader-Setup-<version>.exe` and run it. It installs just for you, no admin rights needed.
2. Start **GUC CMS Downloader** from the Start menu.

Windows doesn't know unsigned programs like this one, so it may say "Windows protected your PC": click **More info → Run anyway**.

Want the command line too? Tick **Add the cms-dl command to PATH** during setup, then `cms-dl --sync` works in any terminal.

### 🐧 Linux

Download `CMS-Downloader-<version>-x86_64.AppImage` and make it executable:

```bash
chmod +x CMS-Downloader-*-x86_64.AppImage
```

Started without arguments (or double-clicked) it opens the app; with arguments it's the command line:

```bash
./CMS-Downloader-2.0.0-x86_64.AppImage --sync
```

### ⌨️ Linux command line only

`cms-dl-linux-x86_64` is just the command line, in a single file. Put it in `~/.local/bin`:

```bash
curl -L -o ~/.local/bin/cms-dl https://github.com/numberw8835/CMS-dl/releases/latest/download/cms-dl-linux-x86_64
chmod +x ~/.local/bin/cms-dl
cms-dl --sync
```

Run the same two lines again to update.

## ⚙️ Running from source

You can also run it with Python, on any system.

### Prerequisites

- Python 3.10 or newer ([python.org](https://www.python.org/downloads/)). On Linux you may also need Tk for the app, e.g. `sudo apt install python3-tk`
- The required packages:

  ```bash
  pip install -r requirements.txt
  ```

  On Windows use `py -m pip install -r requirements.txt`.
- A GUC account with access to the courses you want to download
- Optional: [ffmpeg](https://ffmpeg.org/download.html) for lecture videos. Without it videos are saved as `.ts` files, which VLC and the Windows media player open fine.

### 🖥️ The app

```bash
python gui.py
```

(On Windows: `py gui.py`.)

1. The first time, sign in with your GUC account and pick where to save your courses.
2. **Download Courses** lists every course you've taken. A course you took more than once shows up once. Filter by semester or search, tick what you want and press **Download**. You can follow along in the log and press **Stop** at any time.
3. **Save as Sync List** remembers your ticked courses, so **Sync All Courses** on the home page updates all of them in one click.
4. **Settings** has your account, download folder, the delay between requests, semester folders and the theme.

## ⌨️ Command line

### 🔑 First-time setup

Run any command with `-u your_username -p your_password` once; your credentials are then saved in `.guc_account.json` in your home folder (`C:\Users\<you>\.guc_account.json` on Windows). You can also create that file yourself:

```json
{
  "username": "your_username",
  "password": "your_password"
}
```

### 🔍 Getting available courses

```bash
python main.py --get-courses
```

This creates/updates `courses.json` with every course you've taken. Edit it down to the courses you want to keep in sync. Repeated courses show up once per time you took them; they are merged when downloading.

> Note: This doesn't download anything yet, it only saves an **Index** of the courses.

### 📥 Syncing your courses

```bash
python main.py --sync
```

Downloads every course in `courses.json`, each in its own folder. Only new files are downloaded, so run it as often as you like.

### 🚀 Downloading a course directly

By course ID 🌟 (every time you took the course is merged into one folder):

```bash
python main.py -C CSEN901
```

Or by the URL of the course page:

```bash
python main.py -c "course_url" --course-name "Some Course"
```

### Other options

- `-o FOLDER` saves the courses in FOLDER instead of the current folder
- `-d SECONDS` sets the delay between requests (default 1)
- `--by-semester` puts the courses in semester folders (see below)

## 📂 How your downloads are organized

Each course gets a folder named after it, right in your download folder:

```
CMS_Courses/
├── Microprocessors/              taken twice (Winter 2024 and Summer 2026): one folder
│   ├── 1 - Lecture 1.pdf
│   ├── 4 - Lecture 3.pdf
│   └── 1 - Final Revision.pdf    only in the retake, so it was just added
├── Advanced Computer lab 1/      CSEN704  ┐ different courses with the same name,
├── Advanced Computer lab 2/      CSEN903  │ numbered from first taken to last
├── Advanced Computer Lab 3/      CSEN1002 ┘
├── Basic German 4/               taken three times: one folder
└── ...
```

- **Repeated and summer courses** (the same course code again) go into the folder of the first time you took it. Files that are already there aren't downloaded again; only new ones are added. If a retake renumbers an item (`1 - Lecture 3` becomes `4 - Lecture 3`), the file sizes are compared so it isn't downloaded twice.
- **Different courses with the same name** are numbered from first taken to last.
- **Semester folders** are optional: `--by-semester` (or the switch in the app's settings) gives you `Semester 1/`, `Semester 2/`, `Semester 2 - Summer/`, ... A retaken course stays in the semester you first took it. Switching moves your existing folders instead of downloading them again.
- A download that gets interrupted never leaves a half file behind.

## 🩹 When names don't match (manual fix)

Teachers sometimes write material titles in unusual ways, so a course page can show a different number of links and names. When that happens:

- **In the app**, a window opens with the links and names side by side. Line them up (line N on the left belongs to line N on the right) and press **Save & Continue**.
- **On the command line**, a `MANUAL_FIX_<course>.txt` file is created in the course folder. Edit the `[LINKS]` and `[NAMES]` lists so they have the same length, save, and press Enter.

Your fix is remembered: later, only new uploads that don't line up need fixing. Links you delete are skipped from then on; they are listed under `[IGNORED]` in that file, and deleting them there brings them back.

## 📦 Building the downloads

```bash
pip install -r requirements.txt nuitka
python build.py
```

[Nuitka](https://nuitka.net) compiles the program, so it runs without Python installed. It builds for the system it runs on:

- **Windows**: `dist/CMS-Downloader/` with `CMS Downloader.exe` (the app) and `cms-dl.exe` (the command line). Nuitka uses Visual Studio's C compiler or, without it, `pip install ziglang`. With [Inno Setup](https://jrsoftware.org/isdl.php) installed you also get the installer `dist/CMS-Downloader-Setup-<version>.exe` (from `installer.iss`).
- **Linux**: `dist/CMS-Downloader-<version>-x86_64.AppImage` and the single-file command line `dist/cms-dl-linux-x86_64`. Needs gcc and patchelf (`pip install zstandard` to compress the single file); appimagetool is downloaded automatically.

The first build takes a while (yt-dlp alone is over a thousand modules); later ones reuse Nuitka's cache.

**Releasing**: bump the version in `cms_modules/version.py`, then push a tag like `v2.0.1`. GitHub builds the Windows installer and the AppImage (`.github/workflows/release.yml`) and creates a draft release with both, ready to publish. Pull requests get the same builds as downloadable artifacts.

## 🗂️ Where things are stored

- `~/.guc_account.json`: your username and password, in plain text, so keep it private
- `~/.guc_cms_settings.json`: the app's settings
- `courses.json`: your sync list, in the current folder or next to the app/`.exe`

## ⏳ Specifying delay between downloads

To specify the delay (in seconds) between downloading each file, use the `-d` flag:

```bash
python main.py --sync -d 5
```

> Note: Please have mercy on the poor servers of the CMS; they can't handle all the traffic. Make sure to use this with caution (i.e., make the delay longer than 1 or 3, do at least 5).
