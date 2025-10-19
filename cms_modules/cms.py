import re
import os
from time import sleep
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE_URL = "https://cms.guc.edu.eg"

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
        print(f"File {full_filename} already exists, skipping download.")
        return
    
    response = session.get(file_url, stream=True)
    sleep(delay)  # Add delay to prevent server stress
    response.raise_for_status()
    
    # Get the total file size
    total_size = int(response.headers.get('content-length', 0))
    
    # Save the file with progress bar
    with open(full_filename, 'wb') as f:
        if total_size > 0:
            # Use tqdm for progress bar
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=sanitized_filename) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        else:
            # If no content-length header, write without progress bar
            f.write(response.content)

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

    # Download each material
    if len(material_links) == len(material_names):
        for link, name in zip(material_links, material_names):
            full_url = f"{BASE_URL}{link}"
            download_file(session, full_url, name, delay)
    else:
        
        print(f"Warning: Mismatch in counts - {len(material_links)} links and {len(material_names)} names")
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
            name = material_names[i] if i < len(material_names) else f"unnamed_{i+1}"
            print(f"Link: {BASE_URL}{link} | Name: {name}")
            
        for i, link in enumerate(material_links):
            full_url = f"{BASE_URL}{link}"
            name = f"{link.split('/')[-1]}"
            print(f"Downloading {name} from {full_url}")
            download_file(session, full_url, name, delay)
    
    # Go back to parent dir, if name provided
    if course_name:
        os.chdir("..")