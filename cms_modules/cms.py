import re
import os
from time import sleep
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://cms.guc.edu.eg"
COURSES_URL = BASE_URL + "/apps/student/ViewAllCourseStn"

def get_extension(file_url):
    """Extracts the file extension from a URL."""
    parts = file_url.split('.')
    return '.' + parts[-1] if len(parts) > 1 else ".error"

def download_file(session, file_url, save_filename, delay=1):
    """Downloads a file and saves it, checking if it already exists."""
    # Generate full file name with extension
    file_extension = get_extension(file_url)

    # Sanitize the filename to remove invalid characters
    sanitized_filename = re.sub(r'[\\/*?:"<>|]', "", save_filename)
    full_filename = sanitized_filename + file_extension

    # Check if file already exists
    if os.path.exists(full_filename):
        print(f"✅ File {full_filename} already exists, skipping download.")
        return

    try:
        response = session.get(file_url, stream=True)
        sleep(delay)  # Add delay to prevent server stress
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to download {file_url}: {str(e)}")
        return

    # Get the total file size
    total_size = int(response.headers.get('content-length', 0))

    # Save the file with progress bar
    with open(full_filename, 'wb') as f:
        if total_size > 0:
            # Use tqdm for progress bar
            with tqdm(total=total_size, unit='B', unit_scale=True,
                      desc=f"📥 Downloading {sanitized_filename}") as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
            print(f"✅ Successfully downloaded: {full_filename}")
        else:
            # If no content-length header, write without progress bar
            f.write(response.content)
            print(f"⚠️ Downloaded file with unknown size: {sanitized_filename}")

def get_material_links(page_content):
    """Parses HTML to find links to course materials."""
    links = []
    for line in page_content.splitlines():
        if "href='/Uploads" in line:
            link = line.split("href='")[1].split("'")[0]
            links.append(link)
    return links

def get_material_names(page_content):
    """Parses HTML to find names of course materials using a regex pattern."""
    soup = BeautifulSoup(page_content, 'html.parser')
    names = []
    
    # Flexible pattern: any number of spaces, number, any number of spaces, dash, any number of spaces, letter
    pattern = r'^\s*\d+\s*-\s*[a-zA-Z]'

    for line in soup.get_text(separator='\n').splitlines():
        cleaned_line = line.strip()
        
        # Check if the start of the line matches the pattern
        if re.match(pattern, cleaned_line):
            names.append(cleaned_line)
            
    return names

def download_course(session, course_url, course_name = "", delay = 1):
    """Downloads all materials for a given course."""
    response = session.get(course_url)
    response.raise_for_status()
    page_html = response.text

    # Extract the names and links
    material_links = get_material_links(page_html)
    material_names = get_material_names(page_html)

    # Create a folder for the course, if it was provided
    if course_name:
        os.makedirs(course_name, exist_ok=True)
        os.chdir(course_name)
        print(f"📂 Created directory: {course_name}")

    # Download each material
    if len(material_links) == len(material_names):
        for link, name in zip(material_links, material_names):
            full_url = f"{BASE_URL}{link}"
            download_file(session, full_url, name, delay)
    else:
        print(f"⚠️ Warning: Mismatch in counts - {len(material_links)} links and {len(material_names)} names")
        print("Generating default names for unnamed links... Don't blame me, blame the uni for their bad code.")
        print("-"*25)

        # Give an analysis of the found files and links
        for i, link in enumerate(material_links):
            if i < len(material_names):
                name = material_names[i]
            else:
                name = f"unnamed_{i+1}"
            print(f"Link: {BASE_URL}{link}, Name: {name}")

        print("-"*25)

        for i, link in enumerate(material_links):
            full_url = f"{BASE_URL}{link}"
            name = material_names[i] if i < len(material_names) else f"unnamed_{i+1}"
            download_file(session, full_url, name, delay)

    # Go back to parent dir, if name provided
    if course_name:
        os.chdir("..")

# Clean up filenames    
def sanitize_filename(name: str) -> str:    
    cleaned = re.sub(r'[\\/:\*\?"<>\|]+', '', name)    
    return re.sub(r'\s+', ' ', cleaned).strip()    

def sanitize_course_title(course_title):
    parts = course_title.split()
    
    # Remove the first and last items
    if len(parts) > 2:  # Make sure there are enough parts to remove first and last
        filtered_parts = parts[1:-1]
    else:
        filtered_parts = parts  # If less than 3 parts, keep all parts
    
    # Join the remaining parts back into a string
    course_title = ' '.join(filtered_parts)
    course_id = sanitize_filename(parts[0])
    
    return course_id, course_title

def get_course_list(session):
    """Extracts all course names and their links from the All Courses page."""
    response = session.get(COURSES_URL)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Find all semester tables
    tables = soup.find_all(
        "table",
        class_="table table-hover table-striped table-bordered"
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
                    if col.find('a'):
                        course_name = col.find('a').get_text(strip=True)
                        break
                    elif col.find('span'):
                        course_name = col.find('span').get_text(strip=True)
                        break
                    elif col.get_text(strip=True) and len(col.get_text(strip=True)) > 2:
                        # If it's a reasonable length text, use it
                        course_name = col.get_text(strip=True)
                        break

                # If we still don't have a name, try to get it from the first column
                if not course_name:
                    first_col = cols[0]
                    if first_col.find('a'):
                        course_name = first_col.find('a').get_text(strip=True)
                    else:
                        course_name = first_col.get_text(strip=True)

                course_id, course_name = sanitize_course_title(course_name)

                # Add to courses list
                print(f"📚 Found course: {course_name} (ID: {course_id})")
                courses.append({
                    "url": course_url,
                    "name": course_name,
                    "id": course_id
                })

            except Exception as e:
                print(f"❌ Error processing row: {e}")
                continue

    return courses