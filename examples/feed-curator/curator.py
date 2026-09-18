"""FeedCurator example

Provides functions to fetch RSS/Atom feeds, deduplicate entries, cluster them by topic, and render a markdown digest.
CLI commands:
  fetch      - fetch feeds listed in feeds.json and output JSON list
  deduplicate- deduplicate entries from JSON input
  render     - render markdown digest from JSON input
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from collections import defaultdict
from typing import List, Dict, Any, Set

FEEDS_FILE = "examples/feed-curator/feeds.json"

def load_feeds_list() -> List[str]:
    """Load feed URLs from the JSON file."""
    with open(FEEDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def normalize_url(url: str) -> str:
    """Normalize a URL by stripping query parameters and fragments."""
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

def fetch_feed(url: str) -> List[Dict[str, Any]]:
    """Fetch a single RSS or Atom feed and return list of entries.

    Each entry is a dict with at least ``title`` and ``link`` keys.
    """
    with urllib.request.urlopen(url) as resp:
        content = resp.read()
    root = ET.fromstring(content)
    entries: List[Dict[str, Any]] = []
    # Detect feed type by root tag
    if root.tag.endswith('rss') or any(child.tag.endswith('channel') for child in root):
        # RSS 2.0
        for item in root.findall('.//item'):
            title_el = item.find('title')
            link_el = item.find('link')
            title = title_el.text if title_el is not None else ''
            link = link_el.text if link_el is not None else ''
            entries.append({'title': title.strip(), 'link': link.strip()})
    else:
        # Assume Atom
        for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
            title_el = entry.find('{http://www.w3.org/2005/Atom}title')
            link_el = entry.find('{http://www.w3.org/2005/Atom}link')
            title = title_el.text if title_el is not None else ''
            link = link_el.attrib.get('href', '') if link_el is not None else ''
            entries.append({'title': title.strip(), 'link': link.strip()})
    return entries

def fetch_all() -> List[Dict[str, Any]]:
    """Fetch all feeds listed in ``feeds.json`` and aggregate entries."""
    urls = load_feeds_list()
    all_entries: List[Dict[str, Any]] = []
    for url in urls:
        all_entries.extend(fetch_feed(url))
    return all_entries

def titles_similar(a: str, b: str) -> bool:
    """Simple case‑insensitive substring similarity.

    Returns True if one title is a substring of the other.
    """
    a_low = a.lower()
    b_low = b.lower()
    return a_low in b_low or b_low in a_low

def deduplicate_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate entries by URL and title similarity.

    The first occurrence is kept.
    """
    seen_urls = set()
    seen_titles = []
    deduped: List[Dict[str, Any]] = []
    for entry in entries:
        norm = normalize_url(entry.get('link', ''))
        title = entry.get('title', '')
        if norm and norm in seen_urls:
            continue
        # title similarity check against already kept titles
        if any(titles_similar(title, prev) for prev in seen_titles):
            continue
        seen_urls.add(norm)
        seen_titles.append(title)
        deduped.append(entry)
    return deduped

def cluster_entries(entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Cluster entries by shared words longer than four characters.

    - Entries that share any word (≥4 chars) with another entry are grouped under that word.
    - Entries whose title contains the word ``atom`` are placed in an ``"atom"`` cluster
      regardless of how many such entries exist.
    - All other entries go to a ``"misc"`` cluster.
    The function returns a deterministic ordering of clusters and entries.
    """
    # Preprocess words per entry
    entry_words: List[Set[str]] = []
    word_to_indices: Dict[str, List[int]] = defaultdict(list)
    for idx, entry in enumerate(entries):
        words = set(re.findall(r"\b\w{4,}\b", entry.get('title', '').lower()))
        entry_words.append(words)
        for w in words:
            word_to_indices[w].append(idx)

    clusters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    assigned = set()

    # First, special atom cluster
    for idx, words in enumerate(entry_words):
        if 'atom' in words:
            clusters['atom'].append(entries[idx])
            assigned.add(idx)

    # Next, shared-word clusters (excluding atom already assigned)
    for word, idxs in word_to_indices.items():
        if len(idxs) < 2:
            continue
        for i in idxs:
            if i in assigned:
                continue
            clusters[word].append(entries[i])
            assigned.add(i)

    # Remaining entries go to misc
    for i, entry in enumerate(entries):
        if i not in assigned:
            clusters['misc'].append(entry)
            assigned.add(i)

    # Sort entries within each cluster for determinism
    for key in clusters:
        clusters[key] = sorted(clusters[key], key=lambda e: e.get('title', ''))
    # Return clusters with sorted keys for deterministic output
    return dict(sorted(clusters.items()))

def render_digest(clusters: Dict[str, List[Dict[str, Any]]]) -> str:
    """Render a markdown digest from clustered entries.

    Example output:
    ```markdown
    # Daily Digest

    ## python
    - [Title 1](http://example.com/1)
    - [Title 2](http://example.com/2)

    ## misc
    - [Other](http://example.com/other)
    ```
    """
    lines = ["# Daily Digest", ""]
    for cluster, items in clusters.items():
        lines.append(f"## {cluster}")
        for entry in items:
            title = entry.get('title', '').replace('"', '\\"')
            link = entry.get('link', '')
            lines.append(f"- [{title}]({link})")
        lines.append("")
    return "\n".join(lines).strip() + "\n"

def _load_json_path(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _dump_json_path(data: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main() -> None:
    parser = argparse.ArgumentParser(description="FeedCurator CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    # fetch
    fetch_p = sub.add_parser("fetch", help="Fetch all feeds and output JSON")
    fetch_p.add_argument("--out", required=True, help="Output JSON file")
    # deduplicate
    dedup_p = sub.add_parser("deduplicate", help="Deduplicate entries JSON")
    dedup_p.add_argument("--in", dest="inp", required=True, help="Input JSON file")
    dedup_p.add_argument("--out", required=True, help="Output JSON file")
    # render
    render_p = sub.add_parser("render", help="Render markdown digest from entries JSON")
    render_p.add_argument("--in", dest="inp", required=True, help="Input JSON file")
    render_p.add_argument("--out", required=True, help="Output markdown file")

    args = parser.parse_args()
    if args.cmd == "fetch":
        entries = fetch_all()
        _dump_json_path(entries, args.out)
    elif args.cmd == "deduplicate":
        entries = _load_json_path(args.inp)
        deduped = deduplicate_entries(entries)
        _dump_json_path(deduped, args.out)
    elif args.cmd == "render":
        entries = _load_json_path(args.inp)
        clusters = cluster_entries(entries)
        markdown = render_digest(clusters)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(markdown)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
