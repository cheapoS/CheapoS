# SnipVault

A fast, keyboard-friendly code snippet bank with local SQLite storage, automatic language detection, and tag indexing.

## Features
## Installation

The SnipVault example ships with no external dependencies. Just run:

```bash
python3 -m pip install -r requirements-club.txt
```


- **SQLite Backend**: Efficient, local storage using SQLite with FTS5 for fast full-text search.
- **Language Detection**: Automatic language detection based on simple heuristics.
- **Tag Indexing**: Easy categorization of snippets.
- **CLI-based**: Manage snippets directly from the terminal.


## Usage

```bash
# Display help
python3 examples/snip-vault/vault.py --help

# Add a snippet
python3 examples/snip-vault/vault.py add --title "Hello World" --code "print('Hello World')" --language python --tags python,hello

# Search snippets
python3 examples/snip-vault/vault.py search "Hello"

# Tag a snippet
python3 examples/snip-vault/vault.py tag 1 --tags foo,bar

# Export snippets to JSON
python3 examples/snip-vault/vault.py export --output snippets.json

# Copy a snippet to stdout / clipboard
python3 examples/snip-vault/vault.py copy 1
```

## Running Tests

```bash
python3 -m unittest examples/snip-vault/test_vault.py -v
```
