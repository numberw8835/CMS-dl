import os
import re
import shutil
import sys
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from time import sleep
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://cms.guc.edu.eg"
COURSES_URL = BASE_URL + "/apps/student/ViewAllCourseStn"

MEDIA_EXTENSIONS = {".mp4", ".mp3", ".wav", ".m4a", ".aac", ".ts", ".mkv", ".avi", ".mov"}
SEASON_HEADER_RE = re.compile(r"Season\s*:\s*(-?\d+)\s*,?\s*Title\s*:\s*(.*)", re.S)
COURSE_TITLE_RE = re.compile(r"^\(\|\s*(?P<code>[^|]*?)\s*\|\)\s*(?P<name>.*?)\s*(?:\(\d+\))?$", re.S)
NUMBER_PREFIX_RE = re.compile(r"^\s*\d+\s*-\s*")  # the "3 - " in "3 - Lecture 3"
MANUAL_FIX_HELP = (
    "# Every link under [LINKS] gets the name on the same line under [NAMES].\n"
    "# Make both lists the same length, then save. Remove a link to skip it from now on\n"
    "# (it moves to [IGNORED]; delete it there to get it back).\n\n"
)


class DownloadCancelled(Exception):
    """Raised when the user stops a download."""


def ask_in_terminal(manual_file_path: str) -> bool:
    """Default manual-fix prompt: waits until the user has edited the file and pressed Enter."""
    print("\n[ACTION REQUIRED]")
    print(f"A file has been created: {manual_file_path}")
    print("Please open this file, edit the lists so they match (same number of items), and SAVE IT.")
    try:
        # --- SCRIPT STOPS HERE AND WAITS FOR YOU ---
        input(">>> Press Enter after you have SAVED the file to continue...")
    except (EOFError, RuntimeError):  # no terminal to type in, e.g. started without a console
        print("No terminal input available, skipping the materials that need fixing.")
        return False
    return True


@dataclass
class DownloadHooks:
    """Lets a front end (the GUI) take over the manual-fix prompt, progress display and stopping."""

    resolve_mismatch: Callable[[str], bool] = ask_in_terminal
    # Called with (file name, bytes done, total bytes or 0); tqdm progress bars are used when unset
    progress: Callable[[str, int, int], None] | None = None
    cancel: threading.Event | None = None

    def check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            raise DownloadCancelled()


def get_extension(file_url: str) -> str:
    """Extracts the file extension from a URL's path."""
    path = urlparse(file_url).path.replace("\\", "/")
    extension = os.path.splitext(path.rsplit("/", 1)[-1])[1]
    return extension if extension else ".error"


# Clean up filenames
def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:\*\?"<>\|]+', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return re.sub(r"[\x00-\x1f\x7f]", "", cleaned).strip()


def sanitize_folder_name(name: str) -> str:
    """Like sanitize_filename, but also drops the trailing dots and spaces Windows strips from folder names."""
    return sanitize_filename(name).rstrip(". ")


def _link_key(link: str) -> str:
    """Normalizes a material link so relative and full links to the same file compare equal."""
    return urljoin(BASE_URL + "/", link.strip()).replace("\\", "/")


def download_via_ytdlp(
    session: requests.Session, dacast_id: str, mp4_filename: str, delay: int = 1, hooks: DownloadHooks | None = None
) -> bool:
    """Gets HLS stream for dacast_id and downloads it using yt-dlp."""
    hooks = hooks or DownloadHooks()

    # 1. Fetch iframe page
    iframe_url = f"https://iframe.dacast.com/b/{dacast_id.replace('_', '/')}"
    try:
        iframe_response = session.get(iframe_url)
        sleep(delay)
        iframe_response.raise_for_status()
        iframe_html = iframe_response.text
    except Exception as e:
        print(f"Failed to fetch Dacast iframe {iframe_url}: {e}")
        return False

    # 2. Extract contentId
    content_id_match = re.search(r'contentId=([a-f0-9]+-(?:vod|live)-[a-f0-9]+)', iframe_html)
    if not content_id_match:
        content_id_match = re.search(r'id=["\']([a-f0-9]+-(?:vod|live)-[a-f0-9]+)["\']', iframe_html)

    if not content_id_match:
        print("Could not extract contentId from Dacast iframe HTML")
        return False

    content_id = content_id_match.group(1)

    # 3. Fetch playback access JSON
    access_url = f"https://playback.dacast.com/content/access?contentId={content_id}&provider=default"
    try:
        access_response = session.get(access_url)
        sleep(delay)
        access_response.raise_for_status()
        access_data = access_response.json()
    except Exception as e:
        print(f"Failed to fetch playback access metadata for {content_id}: {e}")
        return False

    hls_url = access_data.get("hls")
    if not hls_url:
        print("HLS URL not found in playback access response")
        return False

    # 4. Download the HLS stream with yt-dlp, used as a library so it also works inside a packaged .exe
    print("Switching to yt-dlp...")
    import yt_dlp  # heavy import, only needed for videos

    video_name = os.path.basename(mp4_filename)

    def on_progress(status):
        hooks.check_cancel()
        if hooks.progress is not None and status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            hooks.progress(video_name, int(status.get("downloaded_bytes") or 0), int(total))

    options = {
        "outtmpl": mp4_filename.replace("%", "%%"),  # yt-dlp treats % as a template field
        "no_warnings": True,
        "quiet": hooks.progress is not None,
        "noprogress": hooks.progress is not None,
        "progress_hooks": [on_progress],
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            if ydl.download([hls_url]) or not os.path.exists(mp4_filename):
                raise RuntimeError("yt-dlp could not save the video")
    except Exception as e:
        if hooks.cancel is not None and hooks.cancel.is_set():
            raise DownloadCancelled() from e
        print(f"yt-dlp download failed: {e}")
        if os.path.exists(mp4_filename):
            try:
                os.remove(mp4_filename)
            except OSError:
                pass
        return False

    if shutil.which("ffmpeg") is None:
        mp4_filename = _rename_if_mpegts(mp4_filename)
    print(f"Successfully downloaded video via yt-dlp to: {os.path.basename(mp4_filename)}")
    return True


def _rename_if_mpegts(path: str) -> str:
    """Without ffmpeg, yt-dlp can't repackage an MPEG-TS stream, so the '.mp4' is really a '.ts' file.

    Renaming it lets players such as the one built into Windows open it.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(189)
    except OSError:
        return path
    if len(head) == 189 and head[0] == 0x47 and head[188] == 0x47:  # MPEG-TS sync bytes, every 188 bytes
        ts_path = os.path.splitext(path)[0] + ".ts"
        try:
            os.replace(path, ts_path)
            return ts_path
        except OSError:
            pass
    return path


def _same_file_already_downloaded(
    session: requests.Session, file_url: str, folder: str, stem: str, extension: str, delay: int
) -> bool:
    """True when the folder already has a file with this title (ignoring the 'N - ' number) and size.

    Retakes often renumber items ('1 - Lecture 3' becomes '4 - Lecture 3'), so the size from a
    HEAD request decides whether it's the same file without downloading it again.
    """
    title = NUMBER_PREFIX_RE.sub("", stem).casefold()
    if not title:
        return False
    candidates = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                base, ext = os.path.splitext(entry.name)
                if ext.lower() == extension.lower() and NUMBER_PREFIX_RE.sub("", base).casefold() == title and entry.is_file():
                    candidates.append(entry)
    except OSError:
        return False
    if not candidates:
        return False

    try:
        response = session.head(file_url, allow_redirects=True)
        sleep(delay)
        size = int(response.headers.get("content-length", 0)) if response.ok else 0
    except (requests.RequestException, ValueError):
        return False
    for entry in candidates:
        if size and entry.stat().st_size == size:
            print(f"{stem}{extension} is the same file as {entry.name}, skipping download.")
            return True
    return False


def download_file(
    session: requests.Session,
    file_url: str,
    save_filename: str,
    delay: int = 1,
    vod_mapping: dict = None,
    *,
    folder: str = "",
    hooks: DownloadHooks | None = None,
) -> str:
    """Downloads a file into folder unless it's already there.

    Returns "downloaded", "skipped" or "failed".
    """
    hooks = hooks or DownloadHooks()
    hooks.check_cancel()

    # Generate full file name with extension
    file_extension = get_extension(file_url)

    # Sanitize the filename to remove invalid characters
    sanitized_filename = sanitize_filename(save_filename)
    full_filename = os.path.join(folder, sanitized_filename + file_extension)

    # Determine the video/audio fallback file extension dynamically
    fallback_extension = file_extension if file_extension.lower() in MEDIA_EXTENSIONS else ".mp4"
    video_filename = os.path.join(folder, sanitized_filename + fallback_extension)

    # Check if file already exists
    if os.path.exists(full_filename):
        print(f"File {os.path.basename(full_filename)} already exists, skipping download.")
        return "skipped"

    # Videos saved without ffmpeg end in .ts (see _rename_if_mpegts)
    for existing_video in (video_filename, os.path.join(folder, sanitized_filename + ".ts")):
        if os.path.exists(existing_video):
            print(f"Video/Audio {os.path.basename(existing_video)} already exists, skipping download.")
            return "skipped"

    if _same_file_already_downloaded(session, file_url, folder, sanitized_filename, file_extension, delay):
        return "skipped"

    # Check if this is a video stream that we should download using yt-dlp fallback
    parsed = urlparse(file_url)
    cleaned_path = parsed.path.replace('\\', '/').strip()

    dacast_id = None
    if vod_mapping:
        if cleaned_path in vod_mapping:
            dacast_id = vod_mapping[cleaned_path]

    # Try standard download
    try:
        response = session.get(file_url, stream=True)
        sleep(delay)  # Add delay to prevent server stress
        response.raise_for_status()

        # Check if the content is HTML (meaning it's probably the player page)
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            if not dacast_id:
                html_content = response.content.decode('utf-8', errors='ignore')
                id_match = re.search(r'id=["\'](\d+_f_\d+)["\']', html_content)
                if id_match:
                    dacast_id = id_match.group(1)

            if dacast_id:
                success = download_via_ytdlp(session, dacast_id, video_filename, delay, hooks)
                if success:
                    return "downloaded"

            print(f"Could not download {file_url} as video stream.")
            return "failed"

    except DownloadCancelled:
        raise
    except Exception as e:
        print(f"Standard download failed for {file_url}: {str(e)}")
        if not dacast_id:
            try:
                html_response = session.get(file_url)
                sleep(delay)
                html_response.raise_for_status()
                html_content = html_response.text
                id_match = re.search(r'id=["\'](\d+_f_\d+)["\']', html_content)
                if id_match:
                    dacast_id = id_match.group(1)
            except Exception:
                pass

        if dacast_id:
            success = download_via_ytdlp(session, dacast_id, video_filename, delay, hooks)
            if success:
                return "downloaded"
        return "failed"

    return _save_response(response, full_filename, sanitized_filename, hooks)


def _save_response(response: requests.Response, full_filename: str, label: str, hooks: DownloadHooks) -> str:
    """Streams a response into full_filename via a .part file, so a cut-off download never looks finished."""
    # Get the total file size
    total_size = int(response.headers.get("content-length", 0) or 0)
    part_filename = full_filename + ".part"
    file_name = os.path.basename(full_filename)

    try:
        with open(part_filename, "wb") as f:
            if hooks.progress is not None:
                done = 0
                hooks.progress(file_name, 0, total_size)
                for chunk in response.iter_content(chunk_size=65536):
                    hooks.check_cancel()
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        hooks.progress(file_name, done, total_size)
            else:
                # Use tqdm for progress bar
                with tqdm(
                    total=total_size or None,
                    unit="B",
                    unit_scale=True,
                    desc=f"Downloading {label}",
                    disable=sys.stderr is None,
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=65536):
                        hooks.check_cancel()
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
        os.replace(part_filename, full_filename)
    except BaseException as e:  # also on Ctrl+C and Stop: never leave a half file behind
        response.close()
        try:
            os.remove(part_filename)
        except OSError:
            pass
        if isinstance(e, DownloadCancelled) or not isinstance(e, Exception):
            raise
        print(f"Failed to download {file_name}: {e}")
        return "failed"

    print(f"Successfully downloaded: {file_name}")
    return "downloaded"


def get_material_links(page_content: str) -> list[str]:
    """Parses HTML to find links to course materials."""
    links = []
    for line in page_content.splitlines():
        if "href='/Uploads" in line:
            link = line.split("href='")[1].split("'")[0]
            links.append(link)
    return links


def get_material_names(page_content: str) -> list[str]:
    """Parses HTML to find names of course materials using a regex pattern."""
    soup = BeautifulSoup(page_content, "html.parser")
    names = []

    # Flexible pattern: any number of spaces, number, any number of spaces, dash, any number of spaces, then the
    # title, which can start with anything (e.g. "1 - [Dr. Someone] Thesis Topics")
    pattern = r"^\s*\d+\s*-\s*\S"


    for line in soup.get_text(separator="\n").splitlines():
        cleaned_line = line.strip()

        # Check if the start of the line matches the pattern
        if re.match(pattern, cleaned_line):
            names.append(cleaned_line)

    return names


def get_vod_mapping(page_content: str) -> dict[str, str]:
    """Maps video material paths to their Dacast ids, for the HLS stream fallback."""
    vod_mapping = {}
    try:
        soup = BeautifulSoup(page_content, "html.parser")
        for btn in soup.find_all(class_=lambda x: x and 'vodbutton' in x):
            url = btn.get('data-url')
            btn_id = btn.get('id')
            if url and btn_id:
                cleaned_url = url.replace('\\', '/').strip()
                vod_mapping[cleaned_url] = btn_id.strip()
    except Exception as e:
        print(f"Warning: Could not parse vodbutton mappings: {e}")
    return vod_mapping


def fetch_course_page(session: requests.Session, course_url: str) -> dict:
    """Downloads a course page and pulls out its material links, names and video ids."""
    response = session.get(course_url)
    response.raise_for_status()
    page_html = response.text
    return {
        "url": course_url,
        "links": get_material_links(page_html),
        "names": get_material_names(page_html),
        "vod_mapping": get_vod_mapping(page_html),
    }


def read_manual_fix_file(manual_file_path: str) -> tuple[list[str], list[str], list[str]]:
    """Reads the [LINKS], [NAMES] and [IGNORED] lists of a manual-fix file."""
    sections = {"[LINKS]": [], "[NAMES]": [], "[IGNORED]": []}
    try:
        with open(manual_file_path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except UnicodeDecodeError:  # an editor saved it in another encoding
        with open(manual_file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

    current = None
    for line in lines:
        line = line.strip()
        if line.startswith("["):  # a section starts; unknown sections are skipped
            current = sections.get(line.upper())
        elif line and not line.startswith("#") and current is not None:
            current.append(line)
    return sections["[LINKS]"], sections["[NAMES]"], sections["[IGNORED]"]


def write_manual_fix_file(manual_file_path: str, links: list[str], names: list[str], ignored: list[str] = ()):
    with open(manual_file_path, "w", encoding="utf-8") as f:
        f.write(MANUAL_FIX_HELP)
        f.write("[LINKS]\n")
        for link in links:
            f.write(f"{link}\n")
        f.write("\n[NAMES]\n")
        for name in names:
            f.write(f"{name}\n")
        if ignored:
            f.write("\n[IGNORED]\n")
            for link in ignored:
                f.write(f"{link}\n")


def manual_fix_path(folder: str, course_name: str) -> str:
    """The course's manual-fix file: the MANUAL_FIX_*.txt already in its folder, or a new one."""
    safe_course_name = sanitize_filename(course_name) if course_name else "UNKNOWN_COURSE"
    manual_file_path = os.path.join(folder, f"MANUAL_FIX_{safe_course_name}.txt")
    if not os.path.exists(manual_file_path):
        try:
            existing = sorted(n for n in os.listdir(folder) if n.startswith("MANUAL_FIX_") and n.endswith(".txt"))
        except OSError:
            existing = []
        if existing:
            manual_file_path = os.path.join(folder, existing[0])
    return manual_file_path


def _load_manual_fixes(manual_file_path: str) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """The link -> (link, name) pairs and the ignored links remembered in a manual-fix file."""
    if not os.path.exists(manual_file_path):
        return {}, {}
    try:
        links, names, ignored = read_manual_fix_file(manual_file_path)
    except OSError as e:
        print(f"Error reading existing manual file: {e}")
        return {}, {}
    remembered = {}
    if len(links) == len(names):  # a file that was never fixed doesn't tell us anything
        remembered = {_link_key(link): (link, name) for link, name in zip(links, names)}
    return remembered, {_link_key(link): link for link in ignored}


def _pair_pages(pages: list[dict], remembered: dict, ignored: dict, course_name: str):
    """Pairs each page's links with names: remembered fixes first, the rest in order when the counts match.

    Returns (link, name, vod mapping) pairs, and (links, names, vod mapping) for pages that still don't match.
    """
    pairs, unresolved = [], []
    for page in pages:
        links, names, vod_mapping = page["links"], page["names"], page["vod_mapping"]
        fixed = [(link, remembered[_link_key(link)][1]) for link in links if _link_key(link) in remembered]
        open_links = [link for link in links if _link_key(link) not in remembered and _link_key(link) not in ignored]
        open_names = list(names)
        for _, name in fixed:
            if name in open_names:
                open_names.remove(name)

        if fixed:
            print(f"Using {len(fixed)} names from your manual fixes.")
        pairs += [(link, name, vod_mapping) for link, name in fixed]
        if not open_links or len(open_links) == len(open_names):
            if open_links and not fixed:
                print(f"Found {len(open_links)} matching links and names.")
            pairs += [(link, name, vod_mapping) for link, name in zip(open_links, open_names)]
        else:
            print(
                f"Warning: Mismatch in counts for {course_name} - {len(open_links)} links and {len(open_names)} names"
            )
            unresolved.append((open_links, open_names, vod_mapping))
    return pairs, unresolved


def _pair_with_manual_fixes(pages: list[dict], folder: str, course_name: str, hooks: DownloadHooks):
    """Pairs material links with names for all takes of a course, asking for a manual fix where they don't line up.

    Teachers don't always write titles the way the name pattern expects, so the links and names
    found on a page can differ in number. The course's MANUAL_FIX file remembers how you paired
    them, so only new materials ever need fixing. Returns the pairs and how many links were left out.
    """
    manual_file_path = manual_fix_path(folder, course_name)
    remembered, ignored = _load_manual_fixes(manual_file_path)
    pairs, unresolved = _pair_pages(pages, remembered, ignored, course_name)
    if not unresolved:
        return pairs, 0

    # One file for every take that doesn't match; earlier fixes stay at the top
    open_links = [link for links, _, _ in unresolved for link in links]
    write_manual_fix_file(
        manual_file_path,
        [link for link, _ in remembered.values()] + open_links,
        [name for _, name in remembered.values()] + [name for _, names, _ in unresolved for name in names],
        list(ignored.values()),
    )
    if not hooks.resolve_mismatch(manual_file_path):
        print("Skipping the materials whose names couldn't be matched.")
        return pairs, len(open_links)

    # Read the corrected file
    print(f"\nReading {manual_file_path} for your manual edits...")
    try:
        links, names, ignored_links = read_manual_fix_file(manual_file_path)
    except OSError as e:
        print(f"An error occurred during manual name resolution: {e}")
        return pairs, len(open_links)

    print(f"Found {len(links)} links and {len(names)} names in your file.")
    if len(links) != len(names):
        print("ERROR: The number of links and names in the file still do not match.")
        print("Skipping those materials for now. Please fix the file and try again.")
        return pairs, len(open_links)

    # Links you removed from the list are skipped from now on
    kept = {_link_key(link) for link in links}
    ignored_links += [link for link in open_links if _link_key(link) not in kept and link not in ignored_links]
    write_manual_fix_file(manual_file_path, links, names, ignored_links)
    print(f"Lists match. Manual naming file {os.path.basename(manual_file_path)} kept for your reference.")
    print("-" * 25)

    remembered, ignored = _load_manual_fixes(manual_file_path)
    fixed_pages = [{"links": links, "names": [], "vod_mapping": vods} for links, _, vods in unresolved]
    fixed_pairs, still_open = _pair_pages(fixed_pages, remembered, ignored, course_name)
    return pairs + fixed_pairs, sum(len(links) for links, _, _ in still_open)


def course_folder(output: str, name: str, semester: str = "", by_semester: bool = False) -> str:
    """Absolute folder for a course: output/<name>, or output/<semester>/<name> with by_semester."""
    parts = [output or os.getcwd()]
    if by_semester and semester:
        parts.append(sanitize_folder_name(semester))
    parts.append(sanitize_folder_name(name) or "Untitled")
    return os.path.abspath(os.path.join(*parts))


def _move_existing_folder(folder: str, group: dict, output: str, pages: list[dict]):
    """Reuses a folder the course already has under an older name or layout, instead of downloading it all again.

    That happens when a course gets numbered because another course shares its name, or when
    switching --by-semester on or off. A folder counts when most of the files in it are this
    course's materials, so a course that grew since then still finds its old folder.
    """
    if os.path.exists(folder):
        return
    expected = {sanitize_filename(name) for page in pages for name in page["names"]}
    if not expected:
        return

    names = dict.fromkeys(n for n in [group["name"]] + [take.get("title", "") for take in group["takes"]] if n)
    semester = group.get("semester", "")
    for name in names:
        for candidate in (course_folder(output, name), course_folder(output, name, semester, True)):
            if os.path.normcase(candidate) == os.path.normcase(folder) or not os.path.isdir(candidate):
                continue
            try:
                stems = {
                    os.path.splitext(entry)[0]
                    for entry in os.listdir(candidate)
                    if not entry.startswith("MANUAL_FIX_") and not entry.endswith((".part", ".ytdl"))
                }
            except OSError:
                continue
            matches = len(expected & stems)
            if matches and 2 * matches >= len(stems):
                os.makedirs(os.path.dirname(folder), exist_ok=True)
                try:
                    os.rename(candidate, folder)
                except OSError as e:
                    raise RuntimeError(
                        f"Could not rename {candidate} to {folder} ({e}). Close any open files in it and try again."
                    ) from e
                print(f"Moved {candidate} to {folder}")
                old_parent = os.path.dirname(candidate)
                if os.path.normcase(old_parent) != os.path.normcase(os.path.abspath(output or os.getcwd())):
                    try:
                        os.rmdir(old_parent)  # a semester folder that is empty now
                    except OSError:
                        pass
                return


def download_course_group(
    session: requests.Session,
    group: dict,
    delay: int = 1,
    output: str = "",
    by_semester: bool = False,
    hooks: DownloadHooks | None = None,
) -> Counter:
    """Downloads every take of a course (see group_courses) into one folder.

    Files already in the folder are skipped without asking the server, so a retake only adds
    what's new. Returns counts of files downloaded, skipped, failed and unmatched (left out).
    """
    hooks = hooks or DownloadHooks()
    output = output or ""
    if output and not os.path.exists(output):
        raise FileNotFoundError(f"Output directory {output} does not exist.")

    takes = group["takes"]
    pages = []
    for take in takes:
        hooks.check_cancel()
        try:
            pages.append(fetch_course_page(session, take["url"]))
        except requests.RequestException as e:
            if len(takes) == 1:
                raise
            print(f"Could not open {take['url']}: {e}")
    if not pages:
        raise RuntimeError(f"Could not open any page of {group['name']}")
    if len(takes) > 1:
        print(f"{group['name']} was taken {len(takes)} times, merging them into one folder.")

    folder = course_folder(output, group["name"], group.get("semester", ""), by_semester)
    _move_existing_folder(folder, group, output, pages)
    os.makedirs(folder, exist_ok=True)
    print(f"Saving materials in: {folder}")

    pairs, unmatched = _pair_with_manual_fixes(pages, folder, group["name"], hooks)
    stats = Counter(unmatched=unmatched)
    for link, name, vod_mapping in pairs:
        full_url = urljoin(BASE_URL + "/", link)
        stats[download_file(session, full_url, name, delay, vod_mapping, folder=folder, hooks=hooks)] += 1
    return stats


def download_course(
    session: requests.Session,
    course_url: str,
    course_name: str = "",
    delay: int = 1,
    output: str = "",
    hooks: DownloadHooks | None = None,
) -> Counter:
    """Downloads all materials for a given course."""

    # FIX for TypeError: Handle NoneType passed from argparse
    if output is None:
        output = ""

    group = {"key": course_url, "name": course_name or "Material", "id": "", "semester": "", "takes": [{"url": course_url}]}
    return download_course_group(session, group, delay=delay, output=output, hooks=hooks)


def describe_stats(stats: Counter) -> str:
    """A summary like '3 downloaded, 40 already there, 1 failed'."""
    parts = [f"{stats['downloaded']} downloaded", f"{stats['skipped']} already there"]
    if stats["failed"]:
        parts.append(f"{stats['failed']} failed")
    if stats["unmatched"]:
        parts.append(f"{stats['unmatched']} left out (names not matched)")
    return ", ".join(parts)


def sanitize_course_title(course_title: str) -> tuple[str, str]:
    """Splits '(|CSEN702|) Microprocessors (315)' into ('CSEN702', 'Microprocessors')."""
    match = COURSE_TITLE_RE.match(course_title.strip())
    if not match:  # rows without a course code, like 'Bachelor Thesis Topics - MET'
        return "", " ".join(course_title.split())

    course_id = sanitize_filename(match.group("code"))
    course_id = re.sub(r"[()]+", "", course_id)  # Remove brackets from course_id
    return course_id, " ".join(match.group("name").split())


def _season_header(table) -> tuple[str, str]:
    """Season id and title from the 'Season : 69 , Title: Summer 2026 Round 1' text above a course table."""
    header = table.find_previous(string=re.compile(r"Season\s*:"))
    if header is None:
        return "", ""
    text = ""
    for piece in [header, *header.find_all_next(string=True, limit=10)]:
        if table in piece.parents:
            break
        text = f"{text} {piece.strip()}".strip()
        match = SEASON_HEADER_RE.search(text)
        if match and match.group(2).strip():
            return match.group(1), " ".join(match.group(2).split())
    return "", ""


def get_course_list(session: requests.Session, verbose: bool = True) -> list[dict[str, str]]:
    """Extracts all course names and their links from the All Courses page.

    Courses come newest season first, like on the CMS, with folder names and semesters
    worked out by annotate_courses.
    """
    response = session.get(COURSES_URL)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Find all semester tables
    tables = soup.find_all(
        "table", class_="table table-hover table-striped table-bordered"
    )

    courses = []

    # Process each table (semester)
    for table in tables:
        header_season_id, season_title = _season_header(table)

        # Iterate through course rows (skip header row)
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            try:
                # Extract course ID and season ID
                course_id = cols[3].get_text(strip=True)
                season_id = cols[4].get_text(strip=True)

                # Construct course URL
                course_url = f"{BASE_URL}/apps/student/CourseViewStn.aspx?id={course_id}&sid={season_id}"

                # Extract course name - more robust approach
                course_name = ""

                # Look for the first non-empty text in the row
                for col in cols:
                    if col.find("a"):
                        course_name = col.find("a").get_text(strip=True)
                        break
                    elif col.find("span"):
                        course_name = col.find("span").get_text(strip=True)
                        break
                    elif col.get_text(strip=True) and len(col.get_text(strip=True)) > 2:
                        # If it's a reasonable length text, use it
                        course_name = col.get_text(strip=True)
                        break

                # If we still don't have a name, try to get it from the first column
                if not course_name:
                    first_col = cols[0]
                    if first_col.find("a"):
                        course_name = first_col.find("a").get_text(strip=True)
                    else:
                        course_name = first_col.get_text(strip=True)

                # The "Active" column says "Canceled" for takes that were dropped
                status = next(
                    (
                        col.get_text(strip=True)
                        for col in cols
                        if col.get_text(strip=True).lower() in ("active", "canceled", "cancelled")
                    ),
                    "",
                )

                course_code, course_name = sanitize_course_title(course_name)

                # Add to courses list
                if verbose:
                    print(f"Found course: {course_name} (ID: {course_code})")
                courses.append(
                    {
                        "url": course_url,
                        "name": course_name,
                        "id": course_code,
                        "title": course_name,
                        "season": season_title if header_season_id == season_id else "",
                        "season_id": season_id,
                        "semester": "",
                        "canceled": status.lower().startswith("cancel"),
                    }
                )

            except Exception as e:
                print(f"Error processing row: {e}")
                continue

    return annotate_courses(courses)


def season_id_of(course: dict) -> str:
    """The course's season id; older courses.json entries only have it in the URL."""
    if course.get("season_id"):
        return str(course["season_id"])
    return parse_qs(urlparse(course.get("url", "")).query).get("sid", [""])[0]


def course_key(course: dict) -> str:
    """What identifies a course across seasons: its code, else the CMS course id in its URL."""
    code = str(course.get("id") or "").strip().upper()
    if code:
        return code
    cms_id = parse_qs(urlparse(course.get("url", "")).query).get("id", [""])[0]
    return f"cms:{cms_id}" if cms_id else course.get("url", "")


def semester_labels(courses: list[dict]) -> dict[str, str]:
    """Maps season ids to 'Semester N' or 'Semester N - Summer', counting from the oldest season."""
    titles = {}
    for course in reversed(courses):  # the CMS lists the newest season first
        season = season_id_of(course)
        if season and not titles.get(season):
            titles[season] = course.get("season", "")

    labels, semester, summers = {}, 0, Counter()
    for season, title in titles.items():
        if "summer" in title.lower():
            summers[semester] += 1
            extra = f" {summers[semester]}" if summers[semester] > 1 else ""
            labels[season] = f"Semester {semester} - Summer{extra}"
        else:
            semester += 1
            labels[season] = f"Semester {semester}"
    return labels


def annotate_courses(courses: list[dict]) -> list[dict]:
    """Gives all takes of a course one folder name and one semester (in place) and returns the list.

    Repeated and summer takes share the folder of the first take (canceled takes don't count).
    Different courses that share a name are numbered from first taken to last, for example
    'Advanced Computer lab 1' (CSEN704) and 'Advanced Computer lab 2' (CSEN903).
    """
    labels = semester_labels(courses)
    takes = defaultdict(list)  # course key -> its takes, oldest first
    for course in reversed(courses):
        takes[course_key(course)].append(course)
    homes = {key: next((t for t in group if not t.get("canceled")), group[0]) for key, group in takes.items()}

    position = {id(course): i for i, course in enumerate(reversed(courses))}
    same_name = defaultdict(list)
    for key, home in homes.items():
        same_name[" ".join((home.get("title") or home["name"]).split()).casefold()].append(key)

    for keys in same_name.values():
        keys.sort(key=lambda k: position[id(homes[k])])
        for number, key in enumerate(keys, 1):
            home = homes[key]
            base_name = home.get("title") or home["name"]
            semester = labels.get(season_id_of(home), "")
            for take in takes[key]:
                take.setdefault("title", take["name"])
                take["name"] = f"{base_name} {number}" if len(keys) > 1 else base_name
                take["semester"] = semester
    return courses


def group_courses(courses: list[dict]) -> list[dict]:
    """Merges the takes of each course into one entry {'key', 'name', 'id', 'semester', 'takes'}, newest take first."""
    groups = {}
    for course in courses:
        key = course_key(course)
        if key not in groups:
            groups[key] = {
                "key": key,
                "name": course["name"],
                "id": course.get("id", ""),
                "semester": course.get("semester", ""),
                "takes": [],
            }
        groups[key]["takes"].append(course)
    return list(groups.values())


def _url_identity(url: str) -> tuple[str, str]:
    query = parse_qs(urlparse(url).query)
    return query.get("id", [""])[0], query.get("sid", [""])[0]


def refresh_course_definitions(saved: list[dict], current: list[dict]) -> list[dict]:
    """Updates courses.json entries from the CMS's current list (folder numbering, seasons).

    A name you changed by hand in courses.json is kept, and entries the CMS doesn't list stay as they are.
    """
    by_url = {_url_identity(course["url"]): course for course in current}
    refreshed = []
    for entry in saved:
        identity = _url_identity(entry.get("url", ""))
        latest = by_url.get(identity) if any(identity) else None
        if latest is None:
            refreshed.append(entry)
            continue
        updated = dict(latest)
        if entry.get("name") not in (latest.get("title"), latest["name"]):
            updated["name"] = entry["name"]
        refreshed.append(updated)
    return refreshed
