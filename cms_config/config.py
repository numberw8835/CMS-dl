# config.py
import json
import os
import sys

CREDENTIALS_PATH = os.path.expanduser("~/.guc_account.json")
SETTINGS_PATH = os.path.expanduser("~/.guc_cms_settings.json")  # GUI preferences
COURSES_FILE = "courses.json"
HOME_COURSES_PATH = os.path.expanduser("~/.guc_cms_courses.json")  # the sync list when the program folder can't hold it


def app_dir() -> str:
    """Folder that holds main.py, or the executable when running a PyInstaller build."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def courses_file_path() -> str:
    """courses.json in the current directory if it exists there, otherwise next to the app.

    An AppImage's program folder is read-only (or a temporary copy), so there the sync list lives
    in the home folder instead, next to the other settings.
    """
    if os.path.exists(COURSES_FILE):
        return os.path.abspath(COURSES_FILE)
    if os.environ.get("APPIMAGE") or not os.access(app_dir(), os.W_OK):
        return HOME_COURSES_PATH
    return os.path.join(app_dir(), COURSES_FILE)


def load_credentials() -> tuple[str | None, str | None]:
    """Load credentials from ~/.guc_account.json or prompt for input."""
    if os.path.exists(CREDENTIALS_PATH):
        try:
            with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("username"), data.get("password")
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass

    return None, None


def save_credentials(username: str, password: str):
    """Save credentials to ~/.guc_account.json."""
    try:
        with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
            json.dump({"username": username, "password": password}, f)
        if os.name != "nt":
            os.chmod(CREDENTIALS_PATH, 0o600)  # the password is stored in plain text
        return True
    except Exception as e:
        print(f"Warning: Could not save credentials: {e}")
        return False


def load_course_definitions(config_path: str | None = None) -> list[dict[str, str]]:
    """Load course definitions from courses.json (current directory first, then next to the app)."""
    config_path = config_path or courses_file_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)  # pyright: ignore[reportAny]
        except json.JSONDecodeError as e1:
            print(f"Error: Could not parse courses.json: {e1}")
            return []
        except FileNotFoundError as e2:
            print(f"Error: courses.json not found: {e2}")
            return []
        except Exception as e3:
            print(f"Error: Could not load courses.json: {e3}")
            return []
    return []


def save_course_definitions(courses: list[dict], config_path: str | None = None) -> str:
    """Write courses to courses.json and return the path it was written to."""
    config_path = config_path or courses_file_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)
    return config_path


def load_settings() -> dict:
    """Load GUI preferences (download folder, theme, ...); empty if none are saved yet."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def save_settings(settings: dict) -> bool:
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"Warning: Could not save settings: {e}")
        return False
