# GUC CMS Downloader

This tool allows you to download course materials from the German University in Cairo's CMS.

## Prerequisites

- Python 3.x
- `requests` library (install using pip: `pip install requests`)
- A GUC account with access to the courses you want to download

## Usage

### First-time setup

1. Create a file named `.guc_account.json` in your home directory (`~/.guc_account.json`) and add your GUC credentials:

```json
{
  "username": "your_username",
  "password": "your_password"
}
```

2. Create a file named `courses.json` in the same directory as this script, containing the courses you want to download. Here's an example of what it should look like:

```json
[
    {
        "name": "Course Name",
        "url": "https://cms.guc.edu.eg/courses/CourseID"
    },
    ...
]
```

### Downloading course materials

To download the courses listed in `courses.json`, run the following command:

```
python main.py --sync
```

This will download all the courses from your account and save them in separate folders named after each course.

### Getting available courses

If you're not sure what courses are available, you can retrieve a list of all courses associated with your account by running:

```
python main.py --get-courses
```

This will create/update `courses.json` file with the list of courses. You can then edit this file to select only the courses you want to download.

### Specifying delay between downloads

You can specify the delay (in seconds) between downloading each course using the `-d` flag:

```
python main.py --sync -d 5
```

This will wait for 5 seconds between downloading each course.