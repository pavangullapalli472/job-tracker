"""
Job Application Tracker CLI
Uses Python's built-in sqlite3 and argparse — no extra installs needed.

Usage:
  python job_tracker.py add               # Add a new job application
  python job_tracker.py list              # View all applications
  python job_tracker.py update <id>       # Update status of an application
  python job_tracker.py dashboard         # Summary stats dashboard
"""

import sqlite3
import argparse
from datetime import date

# ── Database setup ────────────────────────────────────────────────────────────

DB_FILE = "jobs.db"

# Valid status values — keeps data consistent
STATUSES = ["Applied", "Phone Screen", "Interview", "Offer", "Rejected", "Withdrawn"]


def get_connection():
    """Open (or create) the SQLite database and return a connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["company"]
    return conn


def init_db():
    """Create the jobs table if it doesn't already exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company     TEXT    NOT NULL,
            role        TEXT    NOT NULL,
            salary      TEXT,           -- stored as text so "$120k" or "120000" both work
            date_applied TEXT   NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'Applied'
        )
    """)
    conn.commit()
    conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def print_table(rows):
    """Print a list of job rows as a formatted table in the terminal."""
    if not rows:
        print("  No applications found.")
        return

    # Column headers and their widths
    headers = ["ID", "Company", "Role", "Salary", "Date Applied", "Status"]
    # Calculate the widest value in each column (including the header itself)
    widths = [len(h) for h in headers]
    for row in rows:
        values = [str(row["id"]), row["company"], row["role"],
                  row["salary"] or "—", row["date_applied"], row["status"]]
        for i, v in enumerate(values):
            widths[i] = max(widths[i], len(v))

    # Build a format string like "  {:<4}  {:<20}  ..." for each column
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    separator = "  " + "  ".join("-" * w for w in widths)

    print(fmt.format(*headers))
    print(separator)
    for row in rows:
        values = [str(row["id"]), row["company"], row["role"],
                  row["salary"] or "—", row["date_applied"], row["status"]]
        print(fmt.format(*values))


def prompt_status(current=None):
    """Show a numbered menu of statuses and return the user's choice."""
    print("\n  Status options:")
    for i, s in enumerate(STATUSES, 1):
        marker = " ← current" if s == current else ""
        print(f"    {i}. {s}{marker}")
    while True:
        choice = input("  Pick a number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(STATUSES):
            return STATUSES[int(choice) - 1]
        print("  Invalid choice, try again.")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(_args):
    """Interactively collect job details and insert a new row."""
    print("\n── Add New Application ──────────────────────────────")

    company = input("  Company name : ").strip()
    if not company:
        print("  Company name is required.")
        return

    role = input("  Role/Title   : ").strip()
    if not role:
        print("  Role is required.")
        return

    salary = input("  Salary (optional, press Enter to skip): ").strip() or None

    # Default date to today; let user override
    today = date.today().isoformat()  # e.g. "2026-03-29"
    date_input = input(f"  Date applied (YYYY-MM-DD) [{today}]: ").strip()
    date_applied = date_input if date_input else today

    status = prompt_status()

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO jobs (company, role, salary, date_applied, status) VALUES (?, ?, ?, ?, ?)",
        (company, role, salary, date_applied, status)
    )
    conn.commit()
    new_id = cursor.lastrowid  # SQLite gives us the auto-generated ID
    conn.close()

    print(f"\n  ✓ Added application #{new_id} — {role} at {company}\n")


def cmd_list(_args):
    """Fetch and display all job applications sorted by date (newest first)."""
    print("\n── All Applications ─────────────────────────────────")
    conn = get_connection()
    rows = conn.execute("SELECT * FROM jobs ORDER BY date_applied DESC").fetchall()
    conn.close()
    print()
    print_table(rows)
    print()


def cmd_update(args):
    """Update the status of a specific job by its ID."""
    job_id = args.id

    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    if not row:
        print(f"\n  No application found with ID {job_id}.\n")
        conn.close()
        return

    print(f"\n── Update Status ────────────────────────────────────")
    print(f"  Job  : {row['role']} at {row['company']}")
    print(f"  Current status: {row['status']}")

    new_status = prompt_status(current=row["status"])

    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
    conn.commit()
    conn.close()

    print(f"\n  ✓ Status updated to '{new_status}'\n")


def cmd_search(args):
    """Filter applications by company name (partial match) and/or status."""
    company_filter = args.company  # e.g. "Google" or None
    status_filter  = args.status   # e.g. "Applied" or None

    # Build the WHERE clause dynamically based on which filters were provided
    conditions = []
    params = []

    if company_filter:
        # LIKE with % allows partial matches — "goo" matches "Google"
        conditions.append("LOWER(company) LIKE LOWER(?)")
        params.append(f"%{company_filter}%")

    if status_filter:
        conditions.append("LOWER(status) = LOWER(?)")
        params.append(status_filter)

    query = "SELECT * FROM jobs"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY date_applied DESC"

    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    # Show what we searched for so the output is self-explanatory
    filters = []
    if company_filter:
        filters.append(f"company='{company_filter}'")
    if status_filter:
        filters.append(f"status='{status_filter}'")
    label = ", ".join(filters) if filters else "all"

    print(f"\n── Search Results ({label}) ───────────────────────────")
    print()
    print_table(rows)
    print(f"\n  {len(rows)} result(s) found.\n")


def cmd_dashboard(_args):
    """Show a summary dashboard with counts by status and key stats."""
    conn = get_connection()

    # Total count
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    # Count per status
    status_counts = conn.execute(
        "SELECT status, COUNT(*) as count FROM jobs GROUP BY status ORDER BY count DESC"
    ).fetchall()

    # Most recent application
    latest = conn.execute(
        "SELECT company, role, date_applied FROM jobs ORDER BY date_applied DESC LIMIT 1"
    ).fetchone()

    # Active applications (not Rejected or Withdrawn)
    active = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status NOT IN ('Rejected', 'Withdrawn')"
    ).fetchone()[0]

    conn.close()

    # ── Print the dashboard ────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════╗")
    print("║        JOB APPLICATION DASHBOARD         ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Total applications : {total:<20}║")
    print(f"║  Active (in-flight) : {active:<20}║")
    if latest:
        last_str = f"{latest['role']} @ {latest['company']}"
        # Truncate if too long to keep table width consistent
        last_str = last_str[:38] if len(last_str) > 38 else last_str
        print(f"║  Latest             : {last_str:<20}║")
        print(f"║  Date               : {latest['date_applied']:<20}║")
    print("╠══════════════════════════════════════════╣")
    print("║  BY STATUS                               ║")
    print("╠══════════════════════════════════════════╣")

    if status_counts:
        for row in status_counts:
            # Build a simple bar: one █ per application
            bar = "█" * row["count"]
            line = f"  {row['status']:<14} {row['count']:>3}  {bar}"
            # Pad to fixed width inside the box
            print(f"║{line:<42}║")
    else:
        print("║  No data yet.                            ║")

    print("╚══════════════════════════════════════════╝")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Make sure the database and table exist before anything else runs
    init_db()

    # argparse handles the subcommand routing
    parser = argparse.ArgumentParser(
        prog="job_tracker",
        description="Track your job applications from the terminal."
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # Each subparser maps a command name to a function
    subparsers.add_parser("add",       help="Add a new job application")
    subparsers.add_parser("list",      help="View all applications")
    subparsers.add_parser("dashboard", help="Summary stats dashboard")

    # 'update' needs an extra argument: the job ID
    update_parser = subparsers.add_parser("update", help="Update status of an application")
    update_parser.add_argument("id", type=int, help="ID of the application to update")

    # 'search' accepts optional --company and/or --status filters
    search_parser = subparsers.add_parser("search", help="Filter applications by company or status")
    search_parser.add_argument("--company", help="Filter by company name (partial match)")
    search_parser.add_argument("--status",  help="Filter by status (e.g. Applied, Interview)")

    args = parser.parse_args()

    # Route to the right function based on the subcommand
    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "search":
        cmd_search(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
