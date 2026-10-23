import argparse
import multiprocessing
import os
import signal
import sys
import warnings
from collections import Counter

from cms_auth import authenticate
from cms_config import (
    courses_file_path,
    load_course_definitions,
    load_credentials,
    save_course_definitions,
    save_credentials,
)
from cms_modules import (
    __version__,
    describe_stats,
    download_course,
    download_course_group,
    get_course_list,
    group_courses,
    refresh_course_definitions,
)

# Suppress the messy resource tracker warnings
warnings.filterwarnings("ignore", category=UserWarning, module="multiprocessing.resource_tracker")


def use_utf8_output():
    """The emoji in messages crash Windows terminals that use a legacy code page (Git Bash, redirected output)."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def handle_sigint(signum, frame):
    print("\n🛑 Exiting...")
    if "session" in globals() and globals()["session"] is not None:
        globals()["session"].close()
    sys.exit(0)


def download_groups(session, groups, args) -> Counter:
    """Downloads each course, with repeated takes merged into one folder; one failure doesn't stop the rest."""
    totals = Counter()
    for group in groups:
        takes = len(group["takes"])
        print(f"⚙️ Syncing {group['name']}..." + (f" (taken {takes} times, merged)" if takes > 1 else ""))
        try:
            stats = download_course_group(
                session, group, delay=args.delay, output=args.output, by_semester=args.by_semester
            )
        except Exception as e:
            print(f"❌ Failed to sync {group['name']}: {e}")
            totals["failed_courses"] += 1
            continue
        print(f"   {describe_stats(stats)}")
        totals.update(stats)
    return totals


def main():
    use_utf8_output()
    signal.signal(signal.SIGINT, handle_sigint)
    parser = argparse.ArgumentParser(
        description="A tool to download course materials from GUC CMS 📚"
    )
    parser.add_argument(
        "-c",
        "--course-url",
        type=str,
        help="Specify the URL of the course page to download materials from",
    )
    parser.add_argument(
        "--course-name",
        type=str,
        default="Untitled",
        help="Specify the name of the course when using --course-url",
    )
    parser.add_argument(
        "-C",
        "--course-id",
        type=str,
        help="Alternatively, provide a course ID instead of the URL (every time you took it is merged into one folder)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Syncs the courses that are defined in the courses.json file",
    )
    parser.add_argument(
        "--get-courses",
        action="store_true",
        help="Retrieve a list of all available courses from the GUC CMS system",
    )
    parser.add_argument(
        "-u",
        "--username",
        type=str,
        help="Your GUC username, which is used for authentication 👤",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        help="Your GUC password, which is also used for authentication 🔒",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=int,
        default=1,
        help="Specify the delay between downloads in seconds (default: 1 second) ⏳",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Specify a directory path to save the downloaded courses. If not provided, the courses will be saved in the current working directory",
    )
    parser.add_argument("--version", action="version", version=f"cms-dl {__version__}")
    parser.add_argument(
        "--by-semester",
        action="store_true",
        help="Put courses in semester folders (Semester 1, Semester 2 - Summer, ...); existing course folders are moved, not downloaded again",
    )

    args, unknown = parser.parse_known_args()

    if unknown and any("multiprocessing" in str(arg) for arg in unknown):
        sys.exit(0)

    # Check for required flags only if we aren't a background process
    if not (args.sync or args.course_url or args.get_courses or args.course_id):
        parser.print_help()
        return

    if args.output and not os.path.isdir(args.output):
        print(f"\n❌ Output directory {args.output} does not exist.")
        return

    username = args.username
    password = args.password

    if not (username and password):
        print(
            "\n⚠️  Credentials not provided. Trying to load from ~/.guc_account.json..."
        )
        username, password = load_credentials()
        if not (username and password):
            print(
                "❌ Error: Credentials not provided and ~/.guc_account.json not found"
            )
            return

    try:
        session = authenticate(username, password)
        globals()["session"] = session
        print("\n✅ Authentication successful! 🔐")
    except ValueError as e:
        print(f"\n❌ Authentication failed: {e}")
        return

    save_credentials(username, password)
    try:
        if args.course_url:
            clean_url = args.course_url.replace('\\', '')

            print(f"\n📥 Downloading course from URL: {clean_url}...")
            stats = download_course(
                session,
                course_url=clean_url, # Use the clean version
                course_name=args.course_name,
                delay=args.delay,
                output=args.output)
            print(f"\n✅ Done: {describe_stats(stats)}")
        elif args.sync:
            courses = load_course_definitions()
            if not courses:
                print(f"\n❌ No courses to sync. Run --get-courses or create {courses_file_path()}")
                return
            # Pick up folder numbering and seasons from the CMS; a name edited in courses.json wins
            try:
                courses = refresh_course_definitions(courses, get_course_list(session, verbose=False))
            except Exception as e:
                print(f"⚠️ Could not refresh the course list ({e}), using courses.json as it is")
            groups = group_courses(courses)
            print(f"\n🔄 Syncing {len(groups)} courses...")
            totals = download_groups(session, groups, args)
            print(f"\n✅ Done: {describe_stats(totals)}")
        elif args.get_courses:
            print("\n🌐 Fetching all available courses from CMS...")
            courses = get_course_list(session)
            save_course_definitions(courses, "courses.json")
            merged = len(group_courses(courses))
            print(f"\n✅ Saved {len(courses)} courses to courses.json ({merged} after merging repeated courses)")
        elif args.course_id:
            courses = get_course_list(session, verbose=False)
            matches = [course for course in courses if str(course["id"]).upper() == args.course_id.upper()]
            if not matches:
                print(f"\n❌ Course with ID {args.course_id} not found!")
                return
            print(f"Downloading course with ID: {args.course_id}...")
            totals = download_groups(session, group_courses(matches), args)
            print(f"\n✅ Done: {describe_stats(totals)}")
    except Exception as e:
        print(f"\n⚠️ Failed to download course materials: {e}")
    finally:
        if "session" in globals() and globals()["session"] is not None:
            globals()["session"].close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
