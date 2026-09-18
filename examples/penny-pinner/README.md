# PennyPinner

## Overview
PennyPinner is a zero‑cost read‑later bookmark manager built as an example application. It stores bookmarks in a SQLite database with an FTS5 virtual table, provides full‑text search, and can generate a deterministic three‑bullet digest for each saved page. An embedded Flask web reader serves a dark‑mode HTML view of a bookmark on port **8088**.

## Installation
```bash
# Clone the repository (if not already done)
git clone <repo-url>
cd <repo-dir>

# Install the required Python packages (Flask is optional for the web reader)
# Install Flask, the only dependency needed for the example
python3 -m pip install flask
```

## Running the Web Reader
The example ships a small Flask app that starts on port 8088.
```bash
# From the repository root
python examples/penny-pinner/app.py
```
Open a browser and navigate to `http://localhost:8088/`. Use the `/read/<id>` endpoint to view a specific bookmark, e.g. `http://localhost:8088/read/1`.

## Running Tests
The deterministic unit tests for the example live in `examples/penny-pinner/test_pinner.py`.
```bash
python3 -m unittest examples/penny-pinner/test_pinner.py -v
```
All tests should pass without external services.
