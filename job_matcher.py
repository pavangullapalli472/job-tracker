"""
Job Matcher — score and rank job listings against Pavan's resume profile.
Uses only Python standard library (no extra installs needed).

Usage:
  python job_matcher.py --input jobs.csv          # Score all jobs in a CSV file
  python job_matcher.py --desc "job text here"    # Score a single pasted description
  python job_matcher.py --input jobs.csv --add    # Add top matches to jobs.db

CSV format expected (header row required):
  title, company, description[, url]

Output:
  Ranked list of jobs with match score and matched keywords
"""

import argparse
import csv
import io
import re
import sqlite3
import sys
from datetime import date

# ── Resume profile ────────────────────────────────────────────────────────────
# Extracted from Pavan Kumar G's resumes (Automation Analytics & Fulfillment Technology)
# Keywords are grouped by weight: higher weight = more critical to the role fit.

PROFILE = {
    # Must-have technical skills (highest weight)
    "core_skills": {
        "weight": 5,
        "keywords": [
            "sql", "power bi", "scada", "wms", "wcs",
            "data analytics", "data analysis", "kpi", "dashboard",
            "warehouse management", "warehouse automation",
        ],
    },
    # Strong secondary skills
    "tools": {
        "weight": 3,
        "keywords": [
            "python", "excel", "google sheets", "tableau", "looker",
            "google apps script", "confluence", "power query",
        ],
    },
    # Domain experience
    "domain": {
        "weight": 3,
        "keywords": [
            "supply chain", "logistics", "fmcg", "distribution", "ecommerce",
            "fulfillment", "warehouse", "3pl", "inventory", "automation",
        ],
    },
    # Role types that match his profile
    "role_keywords": {
        "weight": 4,
        "keywords": [
            "analyst", "analytics", "reporting", "insights", "operations analyst",
            "data analyst", "systems analyst", "flow analyst", "business analyst",
        ],
    },
    # Soft skills / practices
    "practices": {
        "weight": 2,
        "keywords": [
            "agile", "scrum", "uat", "root cause analysis", "process improvement",
            "stakeholder", "incident", "sop", "documentation",
        ],
    },
}

# Jobs are a good match if they hit this score threshold
GOOD_MATCH_THRESHOLD = 10

# ── Scoring ───────────────────────────────────────────────────────────────────

def score_job(text: str) -> tuple[int, list[str]]:
    """
    Score a job description against the resume profile.
    Returns (total_score, list_of_matched_keywords).
    Matching is case-insensitive; each keyword only counts once.
    """
    text_lower = text.lower()
    total_score = 0
    matched = []

    for group in PROFILE.values():
        weight = group["weight"]
        for keyword in group["keywords"]:
            # Use word boundary matching so "sql" doesn't match "nosql" unexpectedly
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, text_lower):
                total_score += weight
                matched.append(keyword)

    return total_score, matched


def score_jobs(jobs: list[dict]) -> list[dict]:
    """
    Score a list of job dicts (each must have 'title', 'company', 'description').
    Returns the list sorted by score descending, with 'score' and 'matched' added.
    """
    for job in jobs:
        # Score against combined title + description so title keywords count too
        combined_text = f"{job.get('title', '')} {job.get('description', '')}"
        score, matched = score_job(combined_text)
        job["score"] = score
        job["matched"] = matched

    return sorted(jobs, key=lambda j: j["score"], reverse=True)


# ── Input parsing ─────────────────────────────────────────────────────────────

def load_csv(filepath: str) -> list[dict]:
    """
    Load jobs from a CSV file.
    Required columns: title, company, description
    Optional columns: url
    """
    jobs = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Normalise header names to lowercase with no extra spaces
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

        required = {"title", "company", "description"}
        missing = required - set(reader.fieldnames)
        if missing:
            print(f"[ERROR] CSV is missing required columns: {', '.join(missing)}")
            print(f"        Found columns: {', '.join(reader.fieldnames)}")
            sys.exit(1)

        for row in reader:
            jobs.append({
                "title": row.get("title", "").strip(),
                "company": row.get("company", "").strip(),
                "description": row.get("description", "").strip(),
                "url": row.get("url", "").strip(),
            })

    return jobs


# ── Output ────────────────────────────────────────────────────────────────────

def print_results(ranked_jobs: list[dict], top_n: int = None):
    """Print ranked job results to the terminal."""
    jobs_to_show = ranked_jobs[:top_n] if top_n else ranked_jobs
    total = len(ranked_jobs)

    print(f"\n{'='*60}")
    print(f"  JOB MATCH RESULTS  ({total} job(s) scored)")
    print(f"{'='*60}")

    for i, job in enumerate(jobs_to_show, 1):
        score = job["score"]
        matched = job["matched"]
        url_line = f"  URL:     {job['url']}" if job.get("url") else ""

        # Visual indicator for match quality
        if score >= GOOD_MATCH_THRESHOLD * 2:
            indicator = "★★★  STRONG MATCH"
        elif score >= GOOD_MATCH_THRESHOLD:
            indicator = "★★   GOOD MATCH"
        elif score >= GOOD_MATCH_THRESHOLD // 2:
            indicator = "★    WEAK MATCH"
        else:
            indicator = "     LOW MATCH"

        print(f"\n#{i}  {indicator}  (score: {score})")
        print(f"  Role:    {job['title']}")
        print(f"  Company: {job['company']}")
        if url_line:
            print(url_line)
        if matched:
            print(f"  Matched: {', '.join(matched)}")
        else:
            print("  Matched: (none)")

    print(f"\n{'='*60}\n")


# ── Add to tracker ────────────────────────────────────────────────────────────

def add_to_tracker(jobs: list[dict], min_score: int):
    """
    Add jobs above min_score to jobs.db (the job tracker database).
    Skips jobs that are already in the database (same title + company).
    """
    eligible = [j for j in jobs if j["score"] >= min_score]

    if not eligible:
        print(f"No jobs met the minimum score of {min_score} to add to tracker.")
        return

    conn = sqlite3.connect("jobs.db")
    conn.row_factory = sqlite3.Row

    # Ensure the table exists (mirrors job_tracker.py schema)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            company   TEXT NOT NULL,
            title     TEXT NOT NULL,
            status    TEXT NOT NULL DEFAULT 'Applied',
            date      TEXT NOT NULL,
            notes     TEXT
        )
    """)

    added = 0
    skipped = 0
    for job in eligible:
        # Check for duplicates
        existing = conn.execute(
            "SELECT id FROM applications WHERE LOWER(company) = LOWER(?) AND LOWER(title) = LOWER(?)",
            (job["company"], job["title"])
        ).fetchone()

        if existing:
            skipped += 1
            continue

        notes = f"Score: {job['score']} | Matched: {', '.join(job['matched'])}"
        conn.execute(
            "INSERT INTO applications (company, title, status, date, notes) VALUES (?, ?, ?, ?, ?)",
            (job["company"], job["title"], "Applied", str(date.today()), notes)
        )
        added += 1

    conn.commit()
    conn.close()

    print(f"Added {added} job(s) to jobs.db  ({skipped} skipped — already tracked)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score job listings against your resume profile.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python job_matcher.py --input jobs.csv
  python job_matcher.py --input jobs.csv --top 5
  python job_matcher.py --input jobs.csv --add --min-score 10
  python job_matcher.py --desc "Data Analyst role at Coles, requires SQL and Power BI..."
        """,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input", metavar="FILE",
        help="Path to a CSV file with columns: title, company, description[, url]"
    )
    source.add_argument(
        "--desc", metavar="TEXT",
        help='A single job description as a quoted string'
    )
    parser.add_argument(
        "--top", type=int, metavar="N",
        help="Show only the top N results (default: show all)"
    )
    parser.add_argument(
        "--add", action="store_true",
        help="Add matched jobs to jobs.db (the job tracker database)"
    )
    parser.add_argument(
        "--min-score", type=int, default=GOOD_MATCH_THRESHOLD, metavar="N",
        help=f"Minimum score required to add to tracker (default: {GOOD_MATCH_THRESHOLD})"
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Load jobs from the chosen source
    if args.input:
        jobs = load_csv(args.input)
        if not jobs:
            print("[ERROR] No jobs found in the CSV file.")
            sys.exit(1)
        print(f"Loaded {len(jobs)} job(s) from {args.input}")
    else:
        # Single description mode — treat it as one anonymous job
        jobs = [{"title": "Pasted Job", "company": "Unknown", "description": args.desc, "url": ""}]

    # Score and rank
    ranked = score_jobs(jobs)

    # Display results
    print_results(ranked, top_n=args.top)

    # Optionally add to tracker
    if args.add:
        add_to_tracker(ranked, min_score=args.min_score)


if __name__ == "__main__":
    main()
