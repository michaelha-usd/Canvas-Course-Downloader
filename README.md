# Canvas Course Downloader

Save your Canvas course material to your own computer — pages, assignments,
discussions (with all the student replies), quizzes, files, the syllabus, your
grades, and your own submitted work.

It uses Canvas's official API with your personal access token, so it's fast and
never needs your password.

---

## What's included

| File | What it's for |
|------|---------------|
| `canvas_downloader.ipynb` | **Notebook version — easiest.** Fill in a few values and click Run. No commands to type. |
| `get_course.py` | Command-line version for **one** course. |
| `get_all_courses.py` | Command-line version for **every** course you're enrolled in. |

Pick whichever you prefer — they do the same thing. The notebook is the simplest
if you'd rather not use a terminal; the scripts are handy if you like the
command line.

> **Important:** `get_course.py` is the engine — it does the actual work. The
> notebook and `get_all_courses.py` are just friendly front-ends that call into
> it, so **`get_course.py` must always be present in the same folder.** The
> notebook will **not** run on its own. Easiest is to download the whole
> project (green **Code → Download ZIP** button) so you get every file together.

---

## Requirements

- **Python 3.8 or newer** ([python.org/downloads](https://www.python.org/downloads/)).
- The **`requests`** library:

  ```
  pip install requests
  ```

  (If `pip` isn't found, try `pip3`. If Python commands aren't found on Windows,
  try `py` instead of `python`.)

- For the **notebook only**: any tool that runs Jupyter notebooks — JupyterLab,
  the classic Jupyter Notebook, or a code editor with notebook support. If you
  don't already have one:

  ```
  pip install jupyterlab
  jupyter lab
  ```

---

## Get your Canvas access token

A token is like a temporary password that lets the tool read your Canvas.

1. Log in to Canvas.
2. Click **Account** → **Settings**.
3. Scroll to **Approved Integrations** → **+ New Access Token**.
4. Give it any name, leave the expiry blank, click **Generate Token**.
5. **Copy the token now** — Canvas only shows it once.

> Keep your token private. Don't share it or commit it to GitHub.

You'll also need your **course ID** for single-course downloads — it's the number
in the course's web address: `https://sandiego.instructure.com/courses/`**`12345`**

---

## Option 1 — The notebook (easiest)

1. Open `canvas_downloader.ipynb` in Jupyter (or any notebook editor). It **must
   be in the same folder as `get_course.py`** — the notebook imports that file to
   do the work and will error with `ModuleNotFoundError: No module named
   'get_course'` if it's missing.
2. Run the cells from top to bottom.
3. In the settings cell, set:
   - `MODE` → `"one"` for a single course, or `"all"` for every course
   - `COURSE_ID` → your course number (for `MODE = "one"`)
   - `EVERYTHING` → `True` for the full archive, `False` for a lighter grab
4. A box will pop up for your token — paste it in.

You can also just use **Run All** — it's safe. Only the choice you set actually
downloads; the other path is skipped automatically.

---

## Option 2 — The command line

Replace the ALL-CAPS parts with your own values.

**One course:**

```
python get_course.py --base-url https://sandiego.instructure.com --course-id COURSE_ID --token YOUR_TOKEN
```

Add `--everything` to also get all files, your grades, and your submitted work:

```
python get_course.py --base-url https://sandiego.instructure.com --course-id 12345 --everything --token YOUR_TOKEN
```

**All your courses** — first preview the list (downloads nothing):

```
python get_all_courses.py --base-url https://sandiego.instructure.com --token YOUR_TOKEN --list-only
```

Then download them all:

```
python get_all_courses.py --base-url https://sandiego.instructure.com --token YOUR_TOKEN --everything
```

> Tip: if `python` isn't found, try `python3` (Mac/Linux) or `py` (Windows).

### Command-line options

| Option | What it does |
|--------|--------------|
| `--everything` | Also get all files, your grades, and your submitted work |
| `--active-only` | (all-courses only) Skip old/finished courses |
| `--list-only` | (all-courses only) Just show the courses, download nothing |
| `--out FOLDER` | Save somewhere other than `canvas_export` |

---

## Where your files end up

Everything is saved in a new folder called `canvas_export`, organized by course
and module:

```
canvas_export/
└── Biology 101 (12345)/
    ├── 00 - Syllabus.html
    ├── Week 1/
    │   ├── 01 - Overview.html
    │   ├── 02 - Homework 1.html
    │   └── 03 - Intro Discussion.html   ← includes all student replies
    ├── _all-files/        (with --everything)
    ├── _grades/           (with --everything)
    └── _my-submissions/   (with --everything)
```

Open any `.html` file in your web browser to read it.

---

## Why some presentation / Panopto pages look blank

Some pages — especially recorded lectures or Panopto/"presentation" pages — open
with a big **empty box** where the video or slides should be. This is normal.

The professor didn't put the actual video or slides *into* the Canvas page — they
**embedded a player** that points to a separate system (Panopto, or Canvas's own
presentation tool). That player only works while you're logged into Canvas, so it
can't load from a file on your computer.

**The good news:** these pages usually still include the parts that *are*
downloadable — such as a **transcript** and an **audio** file, shown as links
near the bottom of the page. Those links work when you're logged into Canvas. To
watch the actual recording, use the link on the page to open it in Canvas.

---

## What Canvas will NOT let you download

The tool can only get what your student account is allowed to see. Canvas does
not allow downloading:

- quiz **questions** (only the quiz instructions/description)
- other students' grades or private work
- instructor-only materials
- replies in a discussion that requires you to post first, until you've posted

---

## Troubleshooting

**`error: unrecognized arguments: —token ...`**
Your dashes got auto-corrected to a long dash. Options must use **two short
dashes** (`--token`), not one long dash (`—token`). Copy the command from this
README rather than retyping it.

**`no such option: --base-url`, or two commands seem to run at once**
You put two commands on one line. Run one command, press **Enter**, wait for it
to finish, then run the next.

**`can't open file ... No such file or directory`**
Your terminal isn't in the folder that contains the scripts. Navigate into that
folder first (`cd path/to/folder`), then run the command.

**A yellow `NotOpenSSLWarning` / `LibreSSL` message (Mac)**
Harmless — ignore it. It doesn't affect the download.

**`401 Unauthorized`**
Your token is wrong, expired, or was revoked. Generate a fresh one and try again.

**`ModuleNotFoundError: No module named 'get_course'`** (notebook or all-courses)
`get_course.py` isn't in the same folder. The notebook and `get_all_courses.py`
both rely on it. Put `get_course.py` next to whichever one you're running (the
simplest fix is to download the whole project so all files stay together).
