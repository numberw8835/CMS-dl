# 📚 GUC CMS Downloader

🚀 **Easily download course materials** from the German University in Cairo's CMS.

## ⚙️ Prerequisites

- Python 3.x
- `requests` library (install using pip: `pip install requests`)
- A GUC account with access to the courses you want to download

## 🎯 Usage

### 🔑 First-time setup

**For easy use:**

1. Create a file named `.guc_account.json` in your home directory (`~/.guc_account.json`) and add your GUC credentials:

   ```json
   {
     "username": "your_username",
     "password": "your_password"
   }
   ```

2. If you have a list of courses you just want to sync automatically without needing to go to the CMS manually, create a file named `courses.json` in the same directory as this script, containing the courses you want to download. Here's an example:

   ```json
   [
       {
           "name": "Course Name",
           "url": "https://cms.guc.edu.eg/apps/student/CourseViewStn.aspx?id..."
       },
       ...
   ]
   ```

This remembers the courses you want to keep track of, note they don't need to be from the same semester 😉

### 📥 Downloading course materials

To download the courses listed in `courses.json`, simply run:

```bash
python main.py --sync
```

This will download all the courses from your account and save them in separate folders named after each course.

### 🔍 Getting available courses

If you're not sure what courses are available, retrieve a list of all courses associated with your account by running:

```bash
python main.py --get-courses
```

This will create/update `courses.json` file with the list of courses. You can then edit this file to select only the courses you want to download.

> Note: This doesn't download the entire CMS yet, this only downloads and **Index** of the courses. If you do wish to download a course from the index, simply modify the `courses.json` to only have the courses you need, then use the `--sync` option.

### 🚀 Downloading a course directly

Let's say you just want to download a single course, you can use these features:

```bash
python main.py -c "course_url"
```

Or use our newest feature: download by course ID 🌟

```bash
python main.py -C CSEN901
```

Instead of manually having to go to the site to grab the URL, you can simply refer to it by its ID.

### ⏳ Specifying delay between downloads

To specify the delay (in seconds) between downloading each course, use the `-d` flag:

```bash
python main.py --sync -d 5
```

This will wait for 5 seconds between downloading each course.

> Note: Please have mercy on the poor servers of the CMS; they can't handle all the traffic. Make sure to use this with caution (i.e., make the delay longer than 1 or 3, do at least 5).