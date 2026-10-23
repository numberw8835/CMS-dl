# 📚 GUC CMS Downloader

🚀 **Easily download course materials** from the German University in Cairo's CMS, on Windows and Linux, with a simple app or from the command line.

## ⬇️ Download

Get the latest version from the [Releases page](https://github.com/numberw8835/CMS-dl/releases/latest). You don't need Python for these.

### 🪟 Windows

1. Download `CMS-Downloader-Setup-<version>.exe` and run it. It installs just for you, no admin rights needed.
2. Start **GUC CMS Downloader** from the Start menu.

Windows doesn't know unsigned programs like this one, so it may say "Windows protected your PC": click **More info → Run anyway**.

The installer also includes the command line, `cms-dl.exe`. Tick **Add the cms-dl command to PATH** during setup, open a new terminal, and `cms-dl --sync` works from anywhere.

### 🐧 Linux

There are two downloads:

- **`cms-dl-linux-x86_64`**: just the command line, in a single file. Put it in `~/.local/bin`:

  ```bash
  curl -L -o ~/.local/bin/cms-dl https://github.com/numberw8835/CMS-dl/releases/latest/download/cms-dl-linux-x86_64
  chmod +x ~/.local/bin/cms-dl
  cms-dl --version
  ```

  Run the same lines again to update. The first start unpacks it into `~/.cache/cms-dl/<version>`, so later starts are quick.

- **`CMS-Downloader-<version>-x86_64.AppImage`**: the app and the command line. Make it executable with `chmod +x`, then double-click it (or start it without arguments) for the app; with arguments it's the command line, e.g. `./CMS-Downloader-2.0.0-x86_64.AppImage --sync`. AppImages need FUSE; without it, add `--appimage-extract-and-run`.

## ⌨️ Command line

The examples use `cms-dl`. Running from source it's `python main.py` instead (`py main.py` on Windows), and with the AppImage `./CMS-Downloader-<version>-x86_64.AppImage`. `cms-dl --help` lists every option.

### 🔑 First-time setup

Run any command with `-u your_username -p your_password` once. After signing in, your credentials are saved in `.guc_account.json` in your home folder (`C:\Users\<you>\.guc_account.json` on Windows), so you can leave them out from then on. The app uses the same file. You can also create it yourself:

```json
{
  "username": "your_username",
  "password": "your_password"
}
```

### 🔍 Getting available courses

```bash
cms-dl --get-courses
```

This saves `courses.json` in the current folder, listing every course you've taken (it replaces an existing `courses.json` there). Edit it down to the courses you want to keep in sync. A course you took more than once appears once per time you took it; those are merged when downloading.

> Note: This doesn't download anything yet, it only saves an **Index** of the courses.

### 📥 Syncing your courses

```bash
cms-dl --sync
```

Downloads every course in the `courses.json` of the current folder, each in its own folder. Only new files are downloaded, so run it as often as you like. It also checks the course list on the CMS so the folder names stay the same as the app's; a name you changed in `courses.json` is kept.

### 🚀 Downloading a course directly

By course ID 🌟 (every time you took the course is merged into one folder):

```bash
cms-dl -C CSEN901
```

Or by the URL of the course page (saved in a folder called `Untitled` unless you give a name):

```bash
cms-dl -c "course_url" --course-name "Some Course"
```

### Other options

- `-o FOLDER` saves the courses in FOLDER instead of the current folder
- `-d SECONDS` sets the delay between downloads (default 1, see below)
- `--by-semester` puts the courses in semester folders (see below)
- `--version` shows the version

## 🖥️ The app

1. The first time, sign in with your GUC account and choose where to save your courses.
2. **Download Courses** lists every course you've taken; a course you took more than once shows up once. Filter by semester or search, tick what you want and press **Download**. You can follow along in the log and press **Stop** at any time.
3. **Save as Sync List** remembers your ticked courses in `courses.json`, so **Sync All Courses** on the home page updates all of them in one click.
4. **Settings** has your account, download folder, the delay between downloads, semester folders and the theme.

## 📂 How your downloads are organized

Each course gets a folder named after it, inside your download folder: the one you chose in the app, or for the command line the current folder (or `-o`).

```
<download folder>/
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
- **On the command line**, an editor opens in the terminal: links on the left, names on the right, every row numbered and both counts at the top. `>` marks the first item of each week on both sides, and rows where only one side starts a week are red, which is usually where a name is missing or extra. Keys:

  | Key | Does |
  |---|---|
  | Up/Down, PgUp/PgDn | move |
  | Tab | switch between the links and the names |
  | `d` | delete the line (a deleted link is skipped from now on) |
  | `a` / `A` | add a name below / above |
  | Enter | edit the name |
  | `K` / `J` | move the line up / down |
  | `u` | undo |
  | `s` | save, once both lists are the same length |
  | `q` | skip these materials for now |

  Without an interactive terminal (e.g. in a script), edit the `MANUAL_FIX_<course>.txt` file it creates in the course folder instead, so the `[LINKS]` and `[NAMES]` lists have the same length, then press Enter.

Your fix is remembered: later, only new uploads that don't line up need fixing. Links you delete are skipped from then on; they are listed under `[IGNORED]` in that file, and deleting them there brings them back.

## 🎬 Lecture videos

Videos are downloaded with yt-dlp, which is built in. With [ffmpeg](https://ffmpeg.org/download.html) installed they're saved as `.mp4`; without it as `.ts`, which VLC and the Windows media player play fine.

## ⚙️ Running from source

1. Install Python 3.10 or newer ([python.org](https://www.python.org/downloads/)). On Linux the app also needs Tk, e.g. `sudo apt install python3-tk`.
2. Install the required packages: `pip install -r requirements.txt` (on Windows `py -m pip install -r requirements.txt`).
3. Start the app with `python gui.py`, or use the command line with `python main.py` (see Command line above).

## 📦 Building the downloads

```bash
pip install -r requirements.txt nuitka
python build.py
```

[Nuitka](https://nuitka.net) compiles the program so it runs without Python. It builds for the system it runs on:

- **Windows**: `dist/CMS-Downloader/` with `CMS Downloader.exe` (the app) and `cms-dl.exe` (the command line). Nuitka needs a C compiler: Visual Studio's (Build Tools) or `pip install ziglang`. With [Inno Setup](https://jrsoftware.org/isdl.php) installed you also get the installer `dist/CMS-Downloader-Setup-<version>.exe` (made from `installer.iss`).
- **Linux**: `dist/cms-dl-linux-x86_64` (single-file command line) and `dist/CMS-Downloader-<version>-x86_64.AppImage`. Needs gcc and patchelf; appimagetool is downloaded automatically. Packing the single file needs zstd compression with threads: on Python 3.13 or older run `pip install zstandard`; some Python 3.14 builds lack threaded zstd, which is why the release builds use 3.13 on Linux.

The first build takes a while (yt-dlp alone is over a thousand modules).

**Releasing**: bump the version in `cms_modules/version.py`, commit, then push a tag like `v2.0.1`. GitHub builds the Windows installer, the AppImage and the Linux `cms-dl` on its own machines (`.github/workflows/release.yml`; free for public repositories) and creates a draft release with all three. Check it, then publish it on GitHub.

## 🗂️ Where things are stored

- `~/.guc_account.json`: your username and password, in plain text, so keep it private
- `~/.guc_cms_settings.json`: the app's settings
- `courses.json`: your sync list. The command line uses the one in the current folder; the app looks in the folder it was started from, then its program folder (on Windows, where it's installed). The Linux AppImage can't write inside itself, so it keeps the list in `~/.guc_cms_courses.json`
- `~/.cache/cms-dl/<version>`: where the Linux `cms-dl` unpacks itself; old versions can be deleted
- `%TEMP%\CMS-Downloader-errors.txt` (Windows app): error details if the app ever fails to start

## ⏳ Specifying delay between downloads

To specify the delay (in seconds) between downloads, use the `-d` flag:

```bash
cms-dl --sync -d 5
```

> Note: Please have mercy on the poor servers of the CMS; they can't handle all the traffic. Make sure to use this with caution (i.e., make the delay longer than 1 or 3, do at least 5).
