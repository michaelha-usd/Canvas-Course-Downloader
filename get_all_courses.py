#!/usr/bin/env python3
"""
Download ALL Canvas courses at once
===================================

Companion to get_course.py. Instead of passing a course ID, this
script asks Canvas for every course you're enrolled in and downloads each one
into its own folder, reusing all the same logic (modules, syllabus, and
optionally the full Files area, grades, and your submissions).

QUICK START
-----------
1. Same token as before (Canvas -> Account -> Settings -> New Access Token).

2. Preview which courses would be downloaded (recommended first step):
     python3 get_all_courses.py \
         --base-url https://sandiego.instructure.com \
         --token YOUR_TOKEN_HERE --list-only

3. Download everything from every course:
     python3 get_all_courses.py \
         --base-url https://sandiego.instructure.com \
         --token YOUR_TOKEN_HERE --everything

FLAGS
-----
  --list-only          Just print the courses it found; download nothing.
  --active-only        Only currently active courses (skip concluded/past ones).
  --everything         Full depth: files-area + grades + submissions + all-pages.
  --files-area         Download each course's entire Files area.
  --grades             Download grades summary + instructor feedback.
  --submissions        Download your own submitted work.
  --pdf                Also make a PDF of each page (needs WeasyPrint; optional).
  --no-files / --no-syllabus / --all-pages / --out DIR
                       Same meaning as in get_course.py.
"""

import argparse
import os

import get_course as dl


def main():
    p = argparse.ArgumentParser(
        description="Download every Canvas course you're enrolled in.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--base-url", required=True,
                   help="e.g. https://sandiego.instructure.com")
    p.add_argument("--token", default=os.environ.get("CANVAS_TOKEN"),
                   help="Canvas access token (or set CANVAS_TOKEN env var).")
    p.add_argument("--out", default="./canvas_export", help="Output directory.")
    p.add_argument("--list-only", action="store_true",
                   help="Only list the courses found; download nothing.")
    p.add_argument("--active-only", action="store_true",
                   help="Only active courses (skip concluded/past terms).")
    # Content depth (same switches as the single-course script)
    p.add_argument("--pdf", action="store_true",
                   help="Also make a PDF of each page (needs WeasyPrint libs). "
                        "Default is HTML only.")
    p.add_argument("--no-files", action="store_true",
                   help="Skip File items inside modules.")
    p.add_argument("--no-syllabus", action="store_true",
                   help="Skip the course syllabus.")
    p.add_argument("--all-pages", action="store_true",
                   help="Also download Pages not listed in any module.")
    p.add_argument("--files-area", action="store_true",
                   help="Download each course's entire Files area.")
    p.add_argument("--grades", action="store_true",
                   help="Download grades summary + instructor feedback.")
    p.add_argument("--submissions", action="store_true",
                   help="Download your own submitted work.")
    p.add_argument("--everything", action="store_true",
                   help="Shortcut for --files-area --grades --submissions --all-pages.")
    args = p.parse_args()

    if not args.token:
        p.error("No token provided. Use --token or set the CANVAS_TOKEN env var.")

    if args.everything:
        args.files_area = args.grades = args.submissions = args.all_pages = True

    client = dl.CanvasClient(args.base_url, args.token)

    print("Discovering your courses...")
    courses = client.get_all_courses(include_concluded=not args.active_only)
    if not courses:
        raise SystemExit(
            "No courses found. Check that the token is valid and that your "
            "account has course enrollments."
        )

    print(f"\nFound {len(courses)} course(s):")
    for c in courses:
        term = (c.get("term") or {}).get("name", "")
        print(f"  - {c['id']}: {c['name']}" + (f"  [{term}]" if term else ""))

    if args.list_only:
        print("\n(--list-only: nothing downloaded.)")
        return

    course_ids = [str(c["id"]) for c in courses]
    print(f"\nDownloading {len(course_ids)} course(s) into {args.out} ...\n")

    dl.run(
        base_url=args.base_url,
        token=args.token,
        course_ids=course_ids,
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
