# MicroCRM

A personal flat-file relationship manager and meeting prep assistant in pure Python stdlib. Stores contacts and interaction logs in Markdown frontmatter and CSV files without external databases. Provides a CLI to add contacts, log interactions with timestamps and tags, list upcoming follow-ups, and generate quick meeting briefing sheets.

## Features

- **Zero dependencies** — pure Python standard library, no external packages required.
- **Markdown frontmatter contacts** — each contact is a single `.md` file with YAML-like frontmatter fields.
- **CSV interaction logs** — interactions are appended to a simple CSV with slug, timestamp, summary, and tags.
- **Follow-up tracking** — list contacts with follow-up dates within a configurable window.
- **Meeting briefings** — generate a quick briefing sheet for any contact, including recent interactions.

## File layout

```
examples/micro-crm/
├── crm.py              # CLI and library
├── test_crm.py         # Deterministic unit tests
├── README.md           # This file
├── contacts/           # Contact files (one .md per contact)
│   ├── alice-chen.md
│   ├── bob-santos.md
│   └── clara-nguyen.md
└── interactions.csv    # Created on first interaction log
```

## Contact file format

Each contact is a Markdown file with frontmatter between `---` delimiters. The body holds free-form notes.

```markdown
---
name: Alice Chen
email: alice@example.com
tags: engineer, mentor, python
follow_up: 2024-03-15
---
Met at PyCon 2023. Strong background in distributed systems and async Python. Offered to review routing code.
```

## Interactions CSV format

Interactions are stored in a CSV with a header row. Each row records one interaction.

```
slug,timestamp,summary,tags
alice-chen,2024-02-01T10:30:00,Discussed routing,call
```

## CLI

Run from the repository root:

```bash
# Add a contact
python examples/micro-crm/crm.py add-contact \
  --name "Alice Chen" \
  --email alice@example.com \
  --tags "engineer, mentor" \
  --follow-up 2024-03-15 \
  --notes "Met at PyCon 2023."

# Log an interaction
python examples/micro-crm/crm.py log \
  --slug alice-chen \
  --summary "Discussed routing" \
  --tags call

# List upcoming follow-ups (default 30-day window)
python examples/micro-crm/crm.py followups --days 30

# Generate a meeting briefing
python examples/micro-crm/crm.py briefing --slug alice-chen

# List all contacts
python examples/micro-crm/crm.py list
```

## Running tests

```bash
python3 -m unittest examples/micro-crm/test_crm.py -v
```

## Python API

The `crm` module exposes the following public functions:

- `parse_frontmatter(text)` — Split text on the first pair of `---` lines; return `(fields_dict, body)`.
- `render_contact_file(fields, body)` — Render frontmatter and body back into a Markdown file.
- `load_contact(contacts_dir, slug)` — Load a contact from `<dir>/<slug>.md`; raises `FileNotFoundError` if missing.
- `save_contact(contacts_dir, slug, fields, notes)` — Save a contact to `<dir>/<slug>.md`.
- `list_contacts(contacts_dir)` — List all `.md` files in the contacts directory, sorted by name.
- `add_contact(contacts_dir, name, email, tags, follow_up, notes)` — Derive a slug, save the contact, and return the slug.
- `log_interaction(csv_path, slug, summary, tags, timestamp=None)` — Append an interaction row to the CSV; uses the current UTC time when `timestamp` is omitted.
- `load_interactions(csv_path)` — Load all interactions from the CSV; returns an empty list if the file does not exist.
- `get_interactions_for(csv_path, slug)` — Filter interactions by slug and sort ascending by timestamp.
- `list_followups(contacts_dir, within_days=30, now=None)` — List contacts with follow-up dates within the given window, sorted by date.
- `generate_briefing(contacts_dir, csv_path, slug)` — Generate a meeting briefing sheet string for a contact.