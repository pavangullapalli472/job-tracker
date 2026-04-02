# Job Tracker CLI

A command-line tool to track job applications, built with Python's built-in `sqlite3` and `argparse` — no extra installs needed.

## Quick Start

```bash
# Run any command
python job_tracker.py add          # Add a new application
python job_tracker.py list         # View all applications
python job_tracker.py update <id>  # Update status by ID
python job_tracker.py search       # Filter by company or status
python job_tracker.py dashboard    # Summary stats
```

## Project Structure

```
job_tracker.py   # Main CLI — all logic lives here
jobs.db          # SQLite database (auto-created, git-ignored)
```

## Key Rules

1. **No secrets in code:** Never hardcode passwords or API keys. Use environment variables if needed in the future.

2. **Database file:** `jobs.db` is git-ignored — never commit it. It's auto-created on first run.

3. **Dependencies:** This project uses only Python standard library. Do not add third-party packages without a good reason.

4. **Valid statuses:** Only these values are allowed — `Applied`, `Phone Screen`, `Interview`, `Offer`, `Rejected`, `Withdrawn`. Defined in `STATUSES` list at the top of `job_tracker.py`.

5. **Code style:** Keep code simple and readable with comments. Prefer clarity over cleverness — this is a learning project.

## Code Style

- **Comments:** Explain the *why*, not just the *what*
- **Functions:** One function = one job
- **SQL queries:** Use parameterized queries (`?` placeholders) — never string-format SQL directly

## Git Workflow

**Commit format:**
```
feat: add new feature
fix: fix a bug
docs: update documentation
refactor: restructure code without changing behavior
```

## .gitignore

Make sure these are always ignored:
```
jobs.db
.env
.env.*
__pycache__/
*.pyc
```
