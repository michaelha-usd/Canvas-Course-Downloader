# Canvas Course Downloader

Save your Canvas course material to your own computer — pages, assignments,
discussions (with all the student replies), quizzes, files, the syllabus, your
grades, and your own submitted work.

There are two scripts:

| Script | Use it when you want... |
|--------|-------------------------|
| `get_course.py` | **one** course |
| `get_all_courses.py`  | **every** course you're enrolled in |

---

## Setup (do this once)

### 1. Install the requirement

Open the Terminal in VS Code (menu: **Terminal → New Terminal**) and paste:

```
python3 -m pip install requests
```

> That's the only thing you need. Pages are saved as HTML, which opens in any
> web browser.

### 2. Get your Canvas access token

A token is like a temporary password that lets the script read your Canvas.

1. Log in to Canvas.
2. Click **Account** (left sidebar) → **Settings**.
3. Scroll to **Approved Integrations** → click **+ New Access Token**.
4. Give it any name, leave the expiry blank, click **Generate Token**.
5. **Copy the token now** — Canvas only shows it once.

> Keep your token private. Don't paste it into emails or chats — only into your
> own Terminal.

---

## Download ONE course

You need two things: the course ID and your token.

- **Course ID** = the number in the course's web address:
  `https://sandiego.instructure.com/courses/`**`12345`**

Then run this (replace the two ALL-CAPS parts):

```
python3 get_course.py --base-url https://sandiego.instructure.com --course-id COURSE_ID --token YOUR_TOKEN
```

Real example:

```
python3 get_course.py --base-url https://sandiego.instructure.com --course-id 12345 --token 99999~abcdef123456
```

That saves the modules and syllabus. To also grab everything else (all files,
your grades, your submitted work), add `--everything`:

```
python3 get_course.py --base-url https://sandiego.instructure.com --course-id 12345 --everything --token YOUR_TOKEN
```

---

## Download ALL your courses

Same idea, but no course ID needed — it finds them for you.

**First, preview the list** (this downloads nothing, just shows what it found):

```
python3 get_all_courses.py --base-url https://sandiego.instructure.com --token YOUR_TOKEN --list-only
```

**Then download everything from every course:**

```
python3 get_all_courses.py --base-url https://sandiego.instructure.com --token YOUR_TOKEN --everything
```

> This can be a big download if you have many courses. Running `--list-only`
> first lets you see how many courses there are before you commit.

---

## Where your files end up

Everything is saved in a new folder called `canvas_export`, next to the script.
It's organized like this:

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

## Common options

Add any of these to the end of your command:

| Option | What it does |
|--------|--------------|
| `--everything` | Also get all files, your grades, and your submitted work |
| `--active-only` | (all-courses only) Skip old/finished courses |
| `--list-only` | (all-courses only) Just show the courses, download nothing |
| `--out FOLDER` | Save somewhere other than `canvas_export` |

---

## Troubleshooting

**"error: unrecognized arguments: —token ..."**
Your dashes got auto-corrected. It must be **two short dashes** `--token`, not
one long dash `—token`. Copy the command straight from this guide instead of
typing the dashes.

**Two commands ran as one / "no such option: --base-url"**
You pasted a second command onto the same line. Run one command, press **Enter**,
wait for it to finish, then run the next.

**"can't open file ... No such file or directory"**
Your Terminal isn't in the right folder. In VS Code use **File → Open Folder**
and open the folder that contains the scripts, then open a new Terminal.

**A yellow "NotOpenSSLWarning / LibreSSL" message**
Harmless — ignore it. It doesn't affect the download.

---

## Why some presentation / Panopto pages look blank

Some pages — especially recorded lectures or Panopto/"presentation" pages —
will open with a big **empty box** where the video or slides should be. This is
normal and expected. Here's why:

The professor didn't put the actual video or slides *into* the Canvas page. They
**embedded a player** that points to a separate system (Panopto, or Canvas's own
presentation tool). That player only works while you're logged into Canvas — it
can't load from a file on your computer, so it shows up blank. The video and
slides themselves live in that other system, which Canvas won't let the script
reach.

**The good news:** these pages usually still include the parts that *are*
downloadable — like a **transcript PDF** and an **audio (MP3)** file, shown as
links near the bottom of the page. Those links work: click them (while logged
into Canvas) and they open or download the real content. If you ran with
`--everything`, any transcript that's a normal course file is also sitting in
that course's `_all-files` folder.

So a "blank" presentation page isn't broken — the player just can't run outside
Canvas. To watch the actual recording, use the link on the page to open it in
Canvas, where the professor may also offer a download button.

## What Canvas will NOT let you download

The script can only get what your student account is allowed to see. Canvas
does not allow downloading:

- quiz **questions** (only the quiz instructions/description)
- other students' grades or private work
- instructor-only materials
- replies in a discussion that requires you to post first, until you've posted
