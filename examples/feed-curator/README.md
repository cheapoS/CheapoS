# FeedCurator Example

A zero‑cost RSS/Atom feed aggregator and daily markdown digest generator written using only the Python standard library.

## Features
- Fetch RSS 2.0 and Atom feeds (mockable for deterministic tests).
- Deduplicate entries across feeds by normalized URL and simple title similarity.
- Cluster stories by shared words (minimum four characters).
- Render a clean daily markdown digest.

## CLI
```bash
# Fetch all feeds listed in ``feeds.json`` and write JSON entries
python examples/feed-curator/curator.py fetch --out entries.json

# Deduplicate entries JSON
python examples/feed-curator/curator.py deduplicate --in entries.json --out uniq.json

# Render markdown digest
python examples/feed-curator/curator.py render --in uniq.json --out digest.md
```

The commands are pure Python and have no external dependencies.

## Running the tests
```bash
python3 -m unittest examples/feed-curator/test_curator.py -v
```
All tests should pass.
