#!/usr/bin/env python3
"""
Canvas Course Downloader
========================

Downloads the content of a Canvas course's **Modules** section and saves each
item as an HTML file (and optionally a PDF), organized into folders by module.

It now handles every common module item type, not just Pages:
  - Pages
  - Assignments  (instructions / description)
  - Discussions  (the prompt / first post)
  - Quizzes      (description / instructions)
  - External URLs and external tools (saved as a link-out page)
  - Files        (downloaded as the actual file, unless --no-files)
It also grabs the course **Syllabus** by default.

It uses the official Canvas REST API with a personal access token, so it's fast
and reliable and never needs your password.

QUICK START
-----------
1. Generate a Canvas access token:
     Canvas -> Account (left sidebar) -> Settings ->
     "Approved Integrations" -> "+ New Access Token". Copy it (shown once).

2. Install the one dependency:
     python3 -m pip install requests

3. Run it (replace the values):
     python3 get_course.py \
         --base-url https://sandiego.instructure.com \
         --course-id 12345 \
         --token YOUR_TOKEN_HERE

   Pages are saved as HTML, which is all you need. If you specifically want
   PDF copies too, install WeasyPrint (pip install weasyprint, plus
   'brew install pango gdk-pixbuf libffi' on macOS) and add the --pdf flag.

USEFUL FLAGS
------------
  --out DIR         Where to save everything (default: ./canvas_export)
  --pdf             Also make a PDF of each page (needs WeasyPrint; optional)
  --no-files        Don't download File items (skip binary downloads)
  --no-syllabus     Don't download the course syllabus
  --all-pages       Also download Pages that aren't listed in any module
  --course-id ID    Repeatable: pass more than once for several courses
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import requests

# Optional PDF support (imported lazily; HTML still works without it).
try:
    from weasyprint import HTML as _WeasyHTML  # noqa: N814
    _PDF_AVAILABLE = True
    _PDF_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    _WeasyHTML = None
    _PDF_AVAILABLE = False
    _PDF_IMPORT_ERROR = exc


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
          line-height: 1.6; color: #1a1a1a; max-width: 820px; margin: 2rem auto;
          padding: 0 1.25rem; }}
  h1.page-title {{ font-size: 1.7rem; border-bottom: 2px solid #eee;
                   padding-bottom: .4rem; margin-bottom: 1.2rem; }}
  .page-meta {{ color: #666; font-size: .85rem; margin-bottom: 1.5rem; }}
  .kind-badge {{ display: inline-block; background: #eef3fb; color: #0b5cad;
                 border-radius: 4px; padding: .1rem .5rem; font-size: .75rem;
                 font-weight: 600; text-transform: uppercase; letter-spacing: .03em; }}
  img, table {{ max-width: 100%; }}
  table {{ border-collapse: collapse; }}
  table, th, td {{ border: 1px solid #ccc; }}
  th, td {{ padding: .4rem .6rem; }}
  pre {{ background: #f5f5f5; padding: .8rem; overflow-x: auto; }}
  a {{ color: #0b5cad; }}
</style>
</head>
<body>
<h1 class="page-title">{title}</h1>
<div class="page-meta"><span class="kind-badge">{kind}</span>
  &nbsp; Module: {module} &middot; <a href="{source_url}">View in Canvas</a></div>
<div class="page-body">
{body}
</div>
</body>
</html>
"""

EMPTY_BODY = "<em>(No text content on this item in Canvas.)</em>"

DISCUSSION_CSS = """
<style>
  .disc-reply { border-left: 3px solid #d6e2f2; margin: .8rem 0 .8rem 0;
                padding: .2rem 0 .2rem 1rem; }
  .disc-author { font-weight: 600; color: #0b5cad; }
  .disc-date { color: #888; font-size: .8rem; margin-left: .4rem; }
  .disc-deleted { color: #aaa; font-style: italic; }
</style>
"""


def _fmt_date(iso):
    if not iso:
        return ""
    return iso.replace("T", " ").replace("Z", " UTC")[:19]


def render_entries(entries, users, depth=0):
    """Recursively render discussion entries (and their replies) to HTML."""
    if not entries:
        return ""
    out = []
    for e in entries:
        if e.get("deleted"):
            out.append('<div class="disc-reply"><span class="disc-deleted">'
                       '(deleted post)</span></div>')
            continue
        author = users.get(e.get("user_id"), "Unknown")
        date = _fmt_date(e.get("created_at"))
        msg = e.get("message") or "<em>(empty)</em>"
        replies = render_entries(e.get("replies", []), users, depth + 1)
        out.append(
            f'<div class="disc-reply">'
            f'<div><span class="disc-author">{author}</span>'
            f'<span class="disc-date">{date}</span></div>'
            f'<div>{msg}</div>{replies}</div>'
        )
    return "".join(out)


def build_discussion_html(topic, view):
    """Combine the opening prompt with the full threaded student discussion."""
    users = {p.get("id"): (p.get("display_name") or p.get("name") or "Unknown")
             for p in view.get("participants", [])}
    entries = view.get("view", [])
    n = _count_entries(entries)
    prompt = topic.get("message") or "<em>(No prompt text.)</em>"
    thread = render_entries(entries, users)
    return (
        f"{DISCUSSION_CSS}"
        f"<h2>Prompt</h2>{prompt}"
        f"<hr><h2>Discussion &mdash; {n} post(s)</h2>"
        f"{thread or '<p><em>No posts.</em></p>'}"
    )


def _count_entries(entries):
    total = 0
    for e in entries or []:
        total += 1
        total += _count_entries(e.get("replies", []))
    return total


def sanitize(name, fallback="untitled"):
    if not name:
        name = fallback
    name = str(name).strip()
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(". ")
    return (name or fallback)[:150]


class CanvasClient:
    def __init__(self, base_url, token, delay=0.15):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.delay = delay

    def _get(self, url, params=None, stream=False):
        full = url if url.startswith("http") else f"{self.base_url}/api/v1{url}"
        resp = self.session.get(full, params=params, timeout=120, stream=stream)
        if resp.status_code == 401:
            raise SystemExit(
                "ERROR 401 Unauthorized: the token was rejected. Check it's valid "
                "and that --base-url matches your school."
            )
        if resp.status_code == 404:
            raise SystemExit(
                f"ERROR 404 Not Found: {full}\nCheck the course ID and your access."
            )
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def paginated(self, url, params=None):
        params = dict(params or {})
        params.setdefault("per_page", 100)
        next_url, first = url, True
        while next_url:
            resp = self._get(next_url, params=params if first else None)
            first = False
            data = resp.json()
            if isinstance(data, list):
                for item in data:
                    yield item
            else:
                yield data
            next_url = resp.links.get("next", {}).get("url")

    def get_modules_with_items(self, cid):
        return list(self.paginated(f"/courses/{cid}/modules",
                                   params={"include[]": "items"}))

    def get_page(self, cid, page_url):
        return self._get(f"/courses/{cid}/pages/{page_url}").json()

    def get_assignment(self, cid, aid):
        return self._get(f"/courses/{cid}/assignments/{aid}").json()

    def get_discussion(self, cid, did):
        return self._get(f"/courses/{cid}/discussion_topics/{did}").json()

    def get_discussion_view(self, cid, did):
        """Full threaded view: every entry + nested replies, plus participants."""
        return self._get(f"/courses/{cid}/discussion_topics/{did}/view").json()

    def get_quiz(self, cid, qid):
        return self._get(f"/courses/{cid}/quizzes/{qid}").json()

    def get_file(self, cid, fid):
        return self._get(f"/courses/{cid}/files/{fid}").json()

    def get_all_pages(self, cid):
        return list(self.paginated(f"/courses/{cid}/pages"))

    def get_course(self, cid, syllabus=False):
        params = {"include[]": "syllabus_body"} if syllabus else None
        try:
            return self._get(f"/courses/{cid}", params=params).json()
        except Exception:
            return {"id": cid, "name": f"course_{cid}"}

    def download_binary(self, url, dest_path):
        # Use a plain request so a locked/missing file raises a normal
        # exception (caught by callers) instead of killing the whole run.
        resp = self.session.get(url, timeout=300, stream=True)
        resp.raise_for_status()
        time.sleep(self.delay)
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)

    # --- extra content: files area, grades, submissions -------------------
    def get_self(self):
        return self._get("/users/self").json()

    def get_all_courses(self, include_concluded=True):
        """List every course the user is enrolled in, active first.
        Skips courses Canvas has restricted by date (no access)."""
        seen, courses = set(), []
        states = ["active"]
        if include_concluded:
            states.append("completed")
        for state in states:
            try:
                for c in self.paginated("/courses",
                                        params={"enrollment_state": state}):
                    cid = c.get("id")
                    if cid in seen:
                        continue
                    if c.get("access_restricted_by_date"):
                        continue
                    if not c.get("name"):
                        continue
                    seen.add(cid)
                    courses.append(c)
            except Exception as exc:
                print(f"  ! could not list {state} courses: {exc}")
        return courses

    def get_folders(self, cid):
        return list(self.paginated(f"/courses/{cid}/folders"))

    def get_files(self, cid):
        return list(self.paginated(f"/courses/{cid}/files"))

    def get_self_enrollments(self, cid):
        return list(self.paginated(f"/courses/{cid}/enrollments",
                                   params={"user_id": "self"}))

    def get_self_submissions(self, cid):
        return list(self.paginated(
            f"/courses/{cid}/students/submissions",
            params={"student_ids[]": "self",
                    "include[]": ["submission_comments", "rubric_assessment",
                                  "assignment"]},
        ))


def write_html(module_dir, filename, title, kind, module, source_url, body,
               client, make_pdf):
    module_dir.mkdir(parents=True, exist_ok=True)
    html_doc = HTML_TEMPLATE.format(
        title=title, kind=kind, module=module,
        source_url=source_url, body=body or EMPTY_BODY,
    )
    html_path = module_dir / f"{filename}.html"
    html_path.write_text(html_doc, encoding="utf-8")
    if make_pdf and _PDF_AVAILABLE:
        try:
            _WeasyHTML(string=html_doc, base_url=client.base_url).write_pdf(
                str(module_dir / f"{filename}.pdf"))
        except Exception as exc:
            print(f"      (PDF skipped: {exc})")
    return html_path


def save_module_item(client, cid, item, module_name, out_dir, make_pdf,
                     index, include_files):
    """Fetch and save one module item based on its type. Returns label or None."""
    itype = item.get("type")
    title = item.get("title") or f"item-{index}"
    source_url = item.get("html_url", "")
    module_dir = out_dir / sanitize(module_name, "no-module")
    fname = f"{index:02d} - {sanitize(title)}"

    try:
        if itype == "Page":
            page = client.get_page(cid, item["page_url"])
            write_html(module_dir, fname, page.get("title", title), "Page",
                       module_name, page.get("html_url", source_url),
                       page.get("body"), client, make_pdf)
            return "page"

        if itype == "Assignment":
            a = client.get_assignment(cid, item["content_id"])
            write_html(module_dir, fname, a.get("name", title), "Assignment",
                       module_name, a.get("html_url", source_url),
                       a.get("description"), client, make_pdf)
            return "assignment"

        if itype in ("Discussion", "DiscussionTopic"):
            d = client.get_discussion(cid, item["content_id"])
            body = d.get("message")
            label = "discussion"
            try:
                view = client.get_discussion_view(cid, item["content_id"])
                body = build_discussion_html(d, view)
                label = f"discussion ({_count_entries(view.get('view', []))} posts)"
            except Exception as exc:
                print(f"      (couldn't load full thread, saved prompt only: {exc})")
            write_html(module_dir, fname, d.get("title", title), "Discussion",
                       module_name, d.get("html_url", source_url),
                       body, client, make_pdf)
            return label

        if itype == "Quiz":
            q = client.get_quiz(cid, item["content_id"])
            write_html(module_dir, fname, q.get("title", title), "Quiz",
                       module_name, q.get("html_url", source_url),
                       q.get("description"), client, make_pdf)
            return "quiz"

        if itype in ("ExternalUrl", "ExternalTool"):
            ext = item.get("external_url") or source_url
            body = (f'<p>This module item links to an external resource:</p>'
                    f'<p><a href="{ext}">{ext}</a></p>')
            write_html(module_dir, fname, title, "External Link",
                       module_name, ext, body, client, make_pdf)
            return "link"

        if itype == "File":
            if not include_files:
                return None
            f = client.get_file(cid, item["content_id"])
            display = f.get("display_name") or f.get("filename") or title
            module_dir.mkdir(parents=True, exist_ok=True)
            dest = module_dir / f"{index:02d} - {sanitize(display, display)}"
            client.download_binary(f["url"], dest)
            return "file"

        if itype == "SubHeader":
            return None  # just a text label in Canvas, no content

        # Unknown/other type: record a stub so nothing is silently lost.
        write_html(module_dir, fname, title, itype or "Item",
                   module_name, source_url,
                   f"<p>Module item of type <code>{itype}</code>. "
                   f"<a href='{source_url}'>Open in Canvas</a>.</p>",
                   client, make_pdf)
        return "other"

    except KeyError as exc:
        print(f"    ! '{title}' ({itype}) missing field {exc}; skipped")
        return None
    except Exception as exc:
        print(f"    ! could not save '{title}' ({itype}): {exc}")
        return None


def save_syllabus(client, cid, course_dir, make_pdf):
    course = client.get_course(cid, syllabus=True)
    body = course.get("syllabus_body")
    if not body:
        print("  Syllabus: (empty or not available)")
        return 0
    write_html(course_dir, "00 - Syllabus", "Syllabus", "Syllabus",
               "(course syllabus)",
               f"{client.base_url}/courses/{cid}/assignments/syllabus",
               body, client, make_pdf)
    print("  Syllabus: saved")
    return 1


def save_all_files(client, cid, course_dir):
    """Download the entire course Files area, mirroring its folder structure."""
    print("  Files area: fetching folder list...")
    try:
        folders = client.get_folders(cid)
        files = client.get_files(cid)
    except Exception as exc:
        print(f"    ! could not list files: {exc}")
        return 0
    # Map folder id -> relative path (full_name looks like 'course files/Sub').
    folder_path = {}
    for f in folders:
        full = f.get("full_name", "course files")
        parts = [sanitize(p, "folder") for p in full.split("/")]
        folder_path[f.get("id")] = Path(*parts) if parts else Path("course files")
    base = course_dir / "_all-files"
    saved = 0
    print(f"  Files area: {len(files)} file(s)")
    for fl in files:
        if fl.get("locked_for_user"):
            continue
        rel = folder_path.get(fl.get("folder_id"), Path("course files"))
        dest_dir = base / rel
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = sanitize(fl.get("display_name") or fl.get("filename"), "file")
        dest = dest_dir / name
        if dest.exists() and dest.stat().st_size == (fl.get("size") or -1):
            saved += 1
            continue  # already downloaded, same size
        try:
            client.download_binary(fl["url"], dest)
            saved += 1
        except Exception as exc:
            print(f"    ! {name}: {exc}")
    print(f"  Files area: {saved} file(s) downloaded")
    return saved


def _render_comments(comments):
    if not comments:
        return ""
    rows = []
    for c in comments:
        who = c.get("author_name", "Unknown")
        when = _fmt_date(c.get("created_at"))
        text = (c.get("comment") or "").replace("\n", "<br>")
        rows.append(f'<div class="disc-reply"><span class="disc-author">{who}'
                    f'</span><span class="disc-date">{when}</span>'
                    f'<div>{text}</div></div>')
    return "<h3>Instructor / submission comments</h3>" + "".join(rows)


def _render_rubric(rubric):
    if not rubric:
        return ""
    rows = ["<h3>Rubric</h3><table><tr><th>Criterion</th><th>Points</th>"
            "<th>Comment</th></tr>"]
    for crit_id, val in rubric.items():
        pts = val.get("points", "")
        cmt = (val.get("comments") or "").replace("\n", "<br>")
        rows.append(f"<tr><td>{crit_id}</td><td>{pts}</td><td>{cmt}</td></tr>")
    rows.append("</table>")
    return "".join(rows)


def save_grades_and_feedback(client, cid, course_dir, make_pdf):
    """Save a grades summary table + per-assignment instructor feedback."""
    print("  Grades: fetching submissions...")
    try:
        subs = client.get_self_submissions(cid)
    except Exception as exc:
        print(f"    ! could not fetch grades: {exc}")
        return 0

    # Course total (from enrollment), if available.
    total_line = ""
    try:
        for en in client.get_self_enrollments(cid):
            g = en.get("grades") or {}
            score = g.get("current_score")
            grade = g.get("current_grade")
            if score is not None or grade is not None:
                total_line = (f"<p><strong>Course total:</strong> "
                              f"{score if score is not None else ''}"
                              f"{' (' + grade + ')' if grade else ''}</p>")
                break
    except Exception:
        pass

    gdir = course_dir / "_grades"
    rows = ["<table><tr><th>Assignment</th><th>Score</th><th>Out of</th>"
            "<th>Grade</th><th>Status</th></tr>"]
    fb_count = 0
    for s in subs:
        a = s.get("assignment") or {}
        name = a.get("name", f"assignment {s.get('assignment_id')}")
        score = s.get("score")
        pts = a.get("points_possible")
        grade = s.get("grade")
        status = []
        if s.get("late"):
            status.append("late")
        if s.get("missing"):
            status.append("missing")
        if s.get("excused"):
            status.append("excused")
        rows.append(
            f"<tr><td>{name}</td><td>{'' if score is None else score}</td>"
            f"<td>{'' if pts is None else pts}</td>"
            f"<td>{grade or ''}</td><td>{', '.join(status)}</td></tr>"
        )
        comments = s.get("submission_comments") or []
        rubric = s.get("rubric_assessment") or {}
        if comments or rubric:
            body = _render_comments(comments) + _render_rubric(rubric)
            write_html(gdir, f"feedback - {sanitize(name)}", name,
                       "Feedback", "(grades)", a.get("html_url", ""),
                       body, client, make_pdf)
            fb_count += 1
    rows.append("</table>")
    summary = total_line + "".join(rows)
    write_html(gdir, "00 - Grades Summary", "Grades Summary", "Grades",
               "(grades)", f"{client.base_url}/courses/{cid}/grades",
               summary, client, make_pdf)
    print(f"  Grades: summary saved, feedback on {fb_count} assignment(s)")
    return 1 + fb_count


def save_my_submissions(client, cid, course_dir):
    """Download the user's own submitted attachments and text entries."""
    print("  My work: fetching submissions...")
    try:
        subs = client.get_self_submissions(cid)
    except Exception as exc:
        print(f"    ! could not fetch submissions: {exc}")
        return 0
    base = course_dir / "_my-submissions"
    saved = 0
    for s in subs:
        a = s.get("assignment") or {}
        name = sanitize(a.get("name", f"assignment {s.get('assignment_id')}"))
        if s.get("workflow_state") in (None, "unsubmitted"):
            continue
        adir = base / name
        wrote = False
        # Text entry
        if s.get("body"):
            adir.mkdir(parents=True, exist_ok=True)
            (adir / "text-entry.html").write_text(
                f"<html><body>{s['body']}</body></html>", encoding="utf-8")
            wrote = True
        # URL submission
        if s.get("url"):
            adir.mkdir(parents=True, exist_ok=True)
            (adir / "submitted-url.txt").write_text(s["url"], encoding="utf-8")
            wrote = True
        # File attachments
        for att in s.get("attachments", []) or []:
            adir.mkdir(parents=True, exist_ok=True)
            fname = sanitize(att.get("display_name") or att.get("filename"), "file")
            try:
                client.download_binary(att["url"], adir / fname)
                wrote = True
            except Exception as exc:
                print(f"    ! {name}/{fname}: {exc}")
        if wrote:
            saved += 1
    print(f"  My work: submissions saved for {saved} assignment(s)")
    return saved


def run(base_url, token, course_ids, out_dir, make_pdf, include_all_pages,
        include_files, include_syllabus, include_files_area, include_grades,
        include_submissions):
    client = CanvasClient(base_url, token)
    out_dir = Path(out_dir).expanduser().resolve()

    if make_pdf and not _PDF_AVAILABLE:
        print(f"NOTE: PDF requested but WeasyPrint unavailable ({_PDF_IMPORT_ERROR}).")
        print("      Saving HTML only. See README for installing PDF libraries.\n")
        make_pdf = False

    grand_total = 0

    def _one_course(cid):
        course = client.get_course(cid)
        cname = sanitize(course.get("name"), f"course_{cid}")
        course_dir = out_dir / f"{cname} ({cid})"
        print(f"\n=== Course: {course.get('name')} (ID {cid}) ===")
        print(f"    Saving to: {course_dir}")

        count = 0
        if include_syllabus:
            count += save_syllabus(client, cid, course_dir, make_pdf)

        modules = client.get_modules_with_items(cid)
        if not modules:
            print("    (No modules found in this course.)")

        seen_pages = set()
        for module in modules:
            mname = module.get("name", "Unnamed module")
            items = module.get("items", []) or []
            savable = [i for i in items if i.get("type") != "SubHeader"]
            if not savable:
                continue
            print(f"  Module: {mname}  ({len(savable)} item(s))")
            for idx, item in enumerate(items, start=1):
                if item.get("type") == "Page" and item.get("page_url"):
                    seen_pages.add(item["page_url"])
                label = save_module_item(client, cid, item, mname, course_dir,
                                         make_pdf, idx, include_files)
                if label:
                    count += 1
                    print(f"    + [{label}] {sanitize(item.get('title',''))}")

        if include_all_pages:
            extras = [p for p in client.get_all_pages(cid)
                      if p.get("url") not in seen_pages]
            if extras:
                print(f"  Pages not in any module: {len(extras)}")
                edir = course_dir / "_pages-not-in-modules"
                for idx, p in enumerate(extras, start=1):
                    try:
                        page = client.get_page(cid, p["url"])
                        write_html(edir, f"{idx:02d} - {sanitize(page.get('title'))}",
                                   page.get("title"), "Page", "(not in a module)",
                                   page.get("html_url", ""), page.get("body"),
                                   client, make_pdf)
                        count += 1
                    except Exception as exc:
                        print(f"    ! {p.get('url')}: {exc}")

        if include_files_area:
            count += save_all_files(client, cid, course_dir)
        if include_grades:
            count += save_grades_and_feedback(client, cid, course_dir, make_pdf)
        if include_submissions:
            count += save_my_submissions(client, cid, course_dir)

        print(f"    Done: {count} item(s) saved for course {cid}.")
        return count

    for cid in course_ids:
        try:
            grand_total += _one_course(cid)
        except BaseException as exc:  # one bad course shouldn't stop the batch
            print(f"    ! Skipped course {cid}: {exc}")

    print(f"\nAll finished. {grand_total} item(s) total in {out_dir}")


def main():
    p = argparse.ArgumentParser(
        description="Download a Canvas course's modules (pages, assignments, "
                    "discussions, quizzes, files) plus the syllabus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url", required=True,
                   help="e.g. https://sandiego.instructure.com")
    p.add_argument("--course-id", required=True, action="append",
                   help="Course ID. Repeat for several courses.")
    p.add_argument("--token", default=os.environ.get("CANVAS_TOKEN"),
                   help="Canvas access token (or set CANVAS_TOKEN env var).")
    p.add_argument("--out", default="./canvas_export", help="Output directory.")
    p.add_argument("--pdf", action="store_true",
                   help="Also make a PDF of each page (needs WeasyPrint libs; "
                        "see README). Default is HTML only.")
    p.add_argument("--no-files", action="store_true",
                   help="Skip downloading File items.")
    p.add_argument("--no-syllabus", action="store_true",
                   help="Skip the course syllabus.")
    p.add_argument("--all-pages", action="store_true",
                   help="Also download Pages not listed in any module.")
    p.add_argument("--files-area", action="store_true",
                   help="Download the ENTIRE course Files area (all folders).")
    p.add_argument("--grades", action="store_true",
                   help="Download your grades summary + instructor feedback.")
    p.add_argument("--submissions", action="store_true",
                   help="Download your own submitted work (attachments/text).")
    p.add_argument("--everything", action="store_true",
                   help="Shortcut: modules + syllabus + files-area + grades + submissions.")
    args = p.parse_args()

    if not args.token:
        p.error("No token provided. Use --token or set the CANVAS_TOKEN env var.")

    if args.everything:
        args.files_area = args.grades = args.submissions = args.all_pages = True

    run(
        base_url=args.base_url,
        token=args.token,
        course_ids=args.course_id,
        out_dir=args.out,
        make_pdf=args.pdf,
        include_all_pages=args.all_pages,
        include_files=not args.no_files,
        include_syllabus=not args.no_syllabus,
        include_files_area=args.files_area,
        include_grades=args.grades,
        include_submissions=args.submissions,
    )


if __name__ == "__main__":
    main()
