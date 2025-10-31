import argparse
import json
import signal
import sys
from cms_auth import authenticate
from cms_config import load_credentials, save_credentials, load_course_definitions
from cms_modules import download_course, get_course_list

def handle_sigint(signum, frame):
    print("\n🛑 Exiting...")
    if 'session' in globals() and globals()['session'] is not None:
        globals()['session'].close()
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, handle_sigint)
    parser = argparse.ArgumentParser(description="Download course materials from GUC CMS 📚")
    parser.add_argument("-c", "--course", help="URL of the course page to download materials from")
    parser.add_argument("-C", "--course-id", help="Use the course ID instead of the URL")
    parser.add_argument("--sync", action="store_true", help="Syncs the courses in the courses.json file")
    parser.add_argument("--get-courses", action="store_true", help="Gets all available courses from the CMS")
    parser.add_argument("-u", "--username", help="Your GUC username 👤")
    parser.add_argument("-p", "--password", help="Your GUC password 🔒")
    parser.add_argument("-d", "--delay", type=int, default=1, help="Delay between downloads (default: 1s) ⏳")
    parser.add_argument("-o", "--output", help="Directory to save the downloaded courses")

    args = parser.parse_args()

    if not args.sync and not args.course and not args.get_courses and not args.course_id:
        parser.error("Either --course or --course-id or --sync is required, or even --get-courses 📝")

    username = args.username
    password = args.password

    if not (username and password):
        print("\n⚠️  Credentials not provided. Trying to load from ~/.guc_account.json...")
        username, password = load_credentials()
        if not (username and password):
            print("❌ Error: Credentials not provided and ~/.guc_account.json not found")
            return

    try:
        session = authenticate(username, password)
        globals()['session'] = session
        print("\n✅ Authentication successful! 🔐")
    except ValueError as e:
        print(f"\n❌ Authentication failed: {e}")
        return

    save_credentials(username, password)

    try:
        if args.course:
            download_course(session, args.course, delay=args.delay, output=args.output)
        elif args.sync:
            courses = load_course_definitions()
            print(f"\n🔄 Syncing {len(courses)} courses...")
            for course in courses:
                print(f"⚙️ Syncing {course['name']}...")
                download_course(session, course["url"], delay=args.delay, output=args.output)
        elif args.get_courses:
            print("\n🌐 Fetching all available courses from CMS...")
            courses = get_course_list(session)
            with open('courses.json', 'w') as f:
                json.dump(courses, f, indent=2)
            print(f"\n✅ Saved {len(courses)} courses to courses.json")
        elif args.course_id:
            courses = get_course_list(session)
            for course in courses:
                if course["id"] == args.course_id:
                    print(f"Downloading course with ID: {args.course_id}...")
                    download_course(session, course["url"], delay=args.delay, output=args.output)
                    break
            else:
                print(f"\n❌ Course with ID {args.course_id} not found!")
    except Exception as e:
        print(f"\n⚠️ Failed to download course materials: {e}")
    finally:
        if 'session' in globals() and globals()['session'] is not None:
            globals()['session'].close()

if __name__ == "__main__":
    main()