"""Builds the programs people download, with Nuitka.

    pip install -r requirements.txt nuitka
    python build.py

Windows: dist/CMS-Downloader/ holds "CMS Downloader.exe" (the app) and cms-dl.exe (the command
         line). With Inno Setup installed (https://jrsoftware.org/isdl.php) it also makes the
         installer dist/CMS-Downloader-Setup-<version>.exe.
Linux:   dist/CMS-Downloader-<version>-x86_64.AppImage, the app when started without arguments and
         the command line with them (see launcher.py). Needs patchelf.

Nuitka builds for the system it runs on; the GitHub release workflow builds both for every v* tag.
"""
import os
import re
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(ROOT, "build", "nuitka")
DIST_DIR = os.path.join(ROOT, "dist")
ASSETS_DIR = os.path.join(ROOT, "gui_modules", "assets")
APP_NAME = "GUC CMS Downloader"
PUBLISHER = "numberw8835"
APPIMAGETOOL_URL = "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"

GUI_OPTIONS = [
    "--enable-plugin=tk-inter",
    "--include-package-data=gui_modules",  # the app icon (Nuitka adds customtkinter's themes and fonts itself)
]

DESKTOP_ENTRY = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=Download course materials from the GUC CMS
Exec=cms-downloader
Icon=cms-downloader
Categories=Education;Network;
Terminal=false
"""

APP_RUN = """#!/bin/sh
# The app without arguments, the command line with them (see launcher.py)
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/cms-downloader/cms-downloader" "$@"
"""


def read_version():
    with open(os.path.join(ROOT, "cms_modules", "version.py"), encoding="utf-8") as f:
        return re.search(r'__version__ = "([^"]+)"', f.read()).group(1)


def nuitka(script, *options):
    """Compiles script into BUILD_DIR/<script>.dist and returns that folder."""
    subprocess.run(
        [
            sys.executable, "-m", "nuitka",
            "--standalone",
            "--assume-yes-for-downloads",
            "--lto=no",  # link-time optimization makes the build much slower for little gain here
            # yt-dlp's optional, generated extractor index: compiling it takes longer than everything else
            # together, and yt-dlp falls back to its regular extractor list without it
            "--nofollow-import-to=yt_dlp.extractor.lazy_extractors",
            f"--output-dir={BUILD_DIR}",
            *options,
            os.path.join(ROOT, script),
        ],
        check=True,
    )
    return os.path.join(BUILD_DIR, os.path.splitext(script)[0] + ".dist")


def build_windows(version):
    numeric_version = ".".join((version.split(".") + ["0"] * 4)[:4])
    details = [
        f"--windows-icon-from-ico={os.path.join(ASSETS_DIR, 'icon.ico')}",
        f"--product-name={APP_NAME}",
        f"--company-name={PUBLISHER}",
        f"--file-version={numeric_version}",
        f"--product-version={numeric_version}",
    ]
    gui_dist = nuitka(
        "gui.py", *GUI_OPTIONS, *details,
        "--windows-console-mode=disable",
        "--force-stderr-spec={TEMP}/CMS-Downloader-errors.txt",  # a window has nowhere else to show a crash
        f"--file-description={APP_NAME}",
        "--output-filename=CMS Downloader.exe",
    )
    cli_dist = nuitka(
        "main.py", *details,
        f"--file-description={APP_NAME} (command line)",
        "--output-filename=cms-dl.exe",
    )

    app_dir = os.path.join(DIST_DIR, "CMS-Downloader")
    shutil.rmtree(app_dir, ignore_errors=True)
    shutil.copytree(gui_dist, app_dir)
    shutil.copytree(cli_dist, app_dir, dirs_exist_ok=True)  # the two programs share their libraries
    print(f"\nPrograms: {app_dir}")

    iscc = find_inno_setup()
    if iscc is None:
        print("Inno Setup isn't installed (https://jrsoftware.org/isdl.php), so no installer was made")
        return
    subprocess.run(
        [iscc, f"/DAppVersion={version}", f"/DSourceDir={app_dir}", f"/O{DIST_DIR}", os.path.join(ROOT, "installer.iss")],
        check=True,
    )
    print(f"Installer: {os.path.join(DIST_DIR, f'CMS-Downloader-Setup-{version}.exe')}")


def find_inno_setup():
    found = shutil.which("ISCC")
    if found:
        return found
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        for folder in ("Inno Setup 6", os.path.join("Programs", "Inno Setup 6")):
            candidate = os.path.join(base or "", folder, "ISCC.exe")
            if base and os.path.exists(candidate):
                return candidate
    return None


def build_linux(version):
    dist = nuitka("launcher.py", *GUI_OPTIONS, "--output-filename=cms-downloader")

    app_dir = os.path.join(BUILD_DIR, "AppDir")
    shutil.rmtree(app_dir, ignore_errors=True)
    shutil.copytree(dist, os.path.join(app_dir, "usr", "lib", "cms-downloader"))
    with open(os.path.join(app_dir, "AppRun"), "w", encoding="utf-8") as f:
        f.write(APP_RUN)
    os.chmod(os.path.join(app_dir, "AppRun"), 0o755)
    with open(os.path.join(app_dir, "cms-downloader.desktop"), "w", encoding="utf-8") as f:
        f.write(DESKTOP_ENTRY)
    shutil.copy(os.path.join(ASSETS_DIR, "icon.png"), os.path.join(app_dir, "cms-downloader.png"))
    os.symlink("cms-downloader.png", os.path.join(app_dir, ".DirIcon"))

    os.makedirs(DIST_DIR, exist_ok=True)
    output = os.path.join(DIST_DIR, f"CMS-Downloader-{version}-x86_64.AppImage")
    # APPIMAGE_EXTRACT_AND_RUN lets appimagetool (an AppImage itself) run without FUSE, e.g. in CI
    env = {**os.environ, "ARCH": "x86_64", "APPIMAGE_EXTRACT_AND_RUN": "1"}
    subprocess.run([find_appimagetool(), app_dir, output], env=env, check=True)
    print(f"\nAppImage: {output}")


def find_appimagetool():
    found = shutil.which("appimagetool")
    if found:
        return found
    path = os.path.join(ROOT, "build", "appimagetool-x86_64.AppImage")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"Downloading {APPIMAGETOOL_URL}")
        urllib.request.urlretrieve(APPIMAGETOOL_URL, path)
        os.chmod(path, 0o755)
    return path


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        build_windows(read_version())
    elif sys.platform.startswith("linux"):
        build_linux(read_version())
    else:
        sys.exit("build.py makes the Windows and Linux builds; on macOS run gui.py with Python")
