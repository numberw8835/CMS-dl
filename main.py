import argparse
from cms_auth import authenticate
from cms_config import load_credentials, save_credentials, load_course_definitions
from cms_modules import download_course

def main():
    parser = argparse.ArgumentParser(description="Download course materials from GUC CMS")
    parser.add_argument("-c", "--course", help="URL of the course page to download materials from")
    parser.add_argument("--update", action="store_true", help="Updates the courses")
    parser.add_argument("-u", "--username", help="Your GUC username")
    parser.add_argument("-p", "--password", help="Your GUC password")
    parser.add_argument("-d", "--delay", type=int, default=1, help="Delay between downloads (default: 1s)")

    args = parser.parse_args()

    if not args.update and not args.course:
        parser.error("Either --course or --update is required")

    # Handle credentials
    username = args.username
    password = args.password
    
    if not (username and password):
        username, password = load_credentials()
        if not (username and password):
            print("Error: Credentials not provided and ~/.guc_account.json not found")
            return

    # Authenticate
    try:
        session = authenticate(username, password)
        print("Authentication successful!")
    except ValueError as e:
        print(f"Authentication failed: {e}")
        return
    
    # Save credentials
    save_credentials(username, password)

    try:
        if args.course:
            download_course(session, args.course, delay=args.delay)
        elif args.update:
            courses = load_course_definitions()
            print(f"Updating {len(courses)} courses...")
            for course in courses:
                print(f"Updating {course['name']}...")
                download_course(session, course["url"], course["name"], delay=args.delay)
    except Exception as e:
        print(f"Failed to download course materials: {e}")

if __name__ == "__main__":
    main()