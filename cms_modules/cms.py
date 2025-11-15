from asyncio import SelectorEventLoop
from pickle import TUPLE
import re
import os
from time import sleep
from bs4 import BeautifulSoup
import requests
from requests.sessions import Request
from tqdm import tqdm

BASE_URL = "https://cms.guc.edu.eg"
COURSES_URL = BASE_URL + "/apps/student/ViewAllCourseStn"


def get_extension(file_url: str) -> str:
    """Extracts the file extension from a URL."""
    parts = file_url.split(".")
    return "." + parts[-1] if len(parts) > 1 else ".error"


# Clean up filenames
def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:\*\?"<>\|]+', "", name)
    return re.sub(r"\s+", " ", cleaned).strip()


def download_file(
    session: requests.Session, file_url: str, save_filename: str, delay: int = 1
):
    """Downloads a file and saves it, checking if it already exists."""
    # Generate full file name with extension
    file_extension = get_extension(file_url)

    # Sanitize the filename to remove invalid characters
    sanitized_filename = sanitize_filename(save_filename)
    full_filename = sanitized_filename + file_extension

    # Check if file already exists
    if os.path.exists(full_filename):
        print(f"File {full_filename} already exists, skipping download.")
        return

    try:
        response = session.get(file_url, stream=True)
        sleep(delay)  # Add delay to prevent server stress
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to download {file_url}: {str(e)}")
        return

    # Get the total file size
    total_size = int(response.headers.get("content-length", 0))

    # Save the file with progress bar
    with open(full_filename, "wb") as f:
        if total_size > 0:
            # Use tqdm for progress bar
            with tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=f"Downloading {sanitized_filename}",
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
            print(f"Successfully downloaded: {full_filename}")
        else:
            # If no content-length header, write without progress bar
            f.write(response.content)
            print(f"Downloaded file with unknown size: {sanitized_filename}")


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

    # Flexible pattern: any number of spaces, number, any number of spaces, dash, any number of spaces, letter
    pattern = r"^\s*\d+\s*-\s*[a-zA-Z]"

    for line in soup.get_text(separator="\n").splitlines():
        cleaned_line = line.strip()

        # Check if the start of the line matches the pattern
        if re.match(pattern, cleaned_line):
            names.append(cleaned_line)

    return names

def download_course(
    session: requests.Session,
    course_url: str,
    course_name: str = "",
    delay: int = 1,
    output: str = "",
):
    """Downloads all materials for a given course."""

    # FIX for TypeError: Handle NoneType passed from argparse
    if output is None:
        output = ""

    response = session.get(course_url)
    response.raise_for_status()
    page_html = response.text

    # Extract the names and links
    material_links = get_material_links(page_html)
    material_names = get_material_names(page_html)
    
    # Define at the top so it's always set
    original_directory = os.getcwd()

    # --- Directory Setup ---
    course_path = ""
    if output:
        if not os.path.exists(output):
            raise FileNotFoundError(f"Output directory {output} does not exist.")
    
    if course_name:
        course_path = os.path.join(output, course_name)
    elif output: # course_name is empty but output is not
        course_path = output
    else: # Both are empty
        course_path = os.path.join(os.getcwd(), "Material")
    
    os.makedirs(course_path, exist_ok=True)
    os.chdir(course_path)
    if course_name:
        print(f"Saving materials in: {course_path}")

    # --- Download Logic ---
    if len(material_links) == len(material_names):
        print(f"Found {len(material_links)} matching links and names.")
        for link, name in zip(material_links, material_names):
            full_url = f"{BASE_URL}{link}"
            download_file(session, full_url, name, delay)
    else:
        # --- NEW MANUAL MISMATCH RESOLUTION ---
        print(
            f"Warning: Mismatch in counts for {course_name} - {len(material_links)} links and {len(material_names)} names"
        )
        
        safe_course_name = sanitize_filename(course_name) if course_name else "UNKNOWN_COURSE"
        manual_file_name = f"MANUAL_FIX_{safe_course_name}.txt"
        
        # We are already inside the course directory
        manual_file_path = os.path.join(os.getcwd(), manual_file_name)

        try:
            # 1. Write the raw mismatch data to the file
            with open(manual_file_path, "w", encoding="utf-8") as f:
                f.write("[LINKS]\n")
                for link in material_links:
                    f.write(f"{BASE_URL}{link}\n")
                f.write("\n[NAMES]\n")
                for name in material_names:
                    f.write(f"{name}\n")

            # 2. Alert the user and wait
            print(f"\n[ACTION REQUIRED]")
            print(f"A file has been created: {manual_file_path}")
            print("Please open this file, edit the lists so they match (same number of items), and SAVE IT.")
            
            # --- SCRIPT STOPS HERE AND WAITS FOR YOU ---
            input(">>> Press Enter after you have SAVED the file to continue...")
            # --- SCRIPT RESUMES ONLY AFTER YOU PRESS ENTER ---

            # 3. Read the corrected file
            print(f"\nReading {manual_file_path} for your manual edits...")
            edited_links = []
            edited_names = []
            parsing_links = False
            parsing_names = False

            with open(manual_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    
                    if line == "[LINKS]":
                        parsing_links = True
                        parsing_names = False
                        continue
                    elif line == "[NAMES]":
                        parsing_links = False
                        parsing_names = True
                        continue
                    elif line.startswith("["): # Stop if another section starts
                        parsing_links = False
                        parsing_names = False
                        
                    if parsing_links and line:
                        edited_links.append(line)
                    elif parsing_names and line:
                        edited_names.append(line)

            print(f"Found {len(edited_links)} links and {len(edited_names)} names in your file.")

            # 4. Check for a match and download
            if len(edited_links) == len(edited_names):
                print(f"Lists match. Proceeding with download for {len(edited_links)} items...")
                print("-" * 25)
                for link, name in zip(edited_links, edited_names):
                    if not name:
                        print(f"Skipping download for link {link} as name is empty.")
                        continue
                    full_url = f"{BASE_URL}{link}"
                    download_file(session, full_url, name, delay)
            else:
                print("ERROR: The number of links and names in the file still do not match.")
                print("Aborting download for this course. Please try again.")
                
            print(f"Manual naming file {manual_file_name} kept for your reference.")

        except Exception as e:
            print(f"An error occurred during manual name resolution: {e}")
            print("Aborting download for this course.")
        
    # Go back to parent dir
    os.chdir(original_directory)

def sanitize_course_title(course_title: str) -> tuple[str, str]:
    parts = course_title.split()

    # Remove the first and last items
    if len(parts) > 2:  # Make sure there are enough parts to remove first and last
        filtered_parts = parts[1:-1]
    else:
        filtered_parts = parts  # If less than 3 parts, keep all parts

    # Join the remaining parts back into a string
    course_title = " ".join(filtered_parts)
    course_id = sanitize_filename(parts[0])
    course_id = re.sub(r"[()]+", "", course_id)  # Remove brackets from course_id

    return course_id, course_title


def get_course_list(session: requests.Session) -> list[dict[str, str]]:
    """Extracts all course names and their links from the All Courses page."""
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

                course_id, course_name = sanitize_course_title(course_name)

                # Add to courses list
                print(f"Found course: {course_name} (ID: {course_id})")
                courses.append(
                    {"url": course_url, "name": course_name, "id": course_id}
                )

            except Exception as e:
                print(f"Error processing row: {e}")
                continue

    return courses