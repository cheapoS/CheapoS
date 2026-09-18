import sqlite3
import argparse
import json
import re
import sys
import os
import datetime

def detect_language(code: str) -> str:
    """Heuristic language detection."""
    code_lower = code.lower()
    
    # Python
    if re.search(r'(def\s+\w+|import\s+\w+|class\s+\w+|print\(|if __name__ ==)', code_lower):
        return "python"
    
    # Javascript
    if re.search(r'(function\s+\w+|const\s+\w+|let\s+\w+|var\s+\w+|console\.log\(|=>)', code_lower):
        return "javascript"
    
    # SQL
    if re.search(r'(select\s+|insert\s+into\s+|update\s+|delete\s+from\s+|create\s+table)', code_lower):
        return "sql"
    
    # Bash
    if re.search(r'(#!\/bin\/bash|echo\s+|export\s+|grep\s+|find\s+)', code_lower):
        return "bash"
        
    return "text"

class SnipVault:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cursor = self.conn.cursor()
        
        # Snippets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                code TEXT,
                language TEXT,
                tags TEXT,
                created_at DATETIME
            )
        ''')
        
        # FTS5 table
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS snippets_fts USING fts5(
                title,
                description,
                code,
                content='snippets',
                content_rowid='id'
            )
        ''')
        
        # Triggers to keep FTS index in sync
        cursor.executescript('''
            CREATE TRIGGER IF NOT EXISTS snippets_ai AFTER INSERT ON snippets BEGIN
              INSERT INTO snippets_fts(rowid, title, description, code)
              VALUES (new.id, new.title, new.description, new.code);
            END;
            CREATE TRIGGER IF NOT EXISTS snippets_ad AFTER DELETE ON snippets BEGIN
              INSERT INTO snippets_fts(snippets_fts, rowid, title, description, code)
              VALUES('delete', old.id, old.title, old.description, old.code);
            END;
            CREATE TRIGGER IF NOT EXISTS snippets_au AFTER UPDATE ON snippets BEGIN
              INSERT INTO snippets_fts(snippets_fts, rowid, title, description, code)
              VALUES('delete', old.id, old.title, old.description, old.code);
              INSERT INTO snippets_fts(rowid, title, description, code)
              VALUES (new.id, new.title, new.description, new.code);
            END;
        ''')
        self.conn.commit()

    def add(self, title: str, description: str, code: str, language: str = None, tags: str = ""):
        if language is None:
            language = detect_language(code)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO snippets (title, description, code, language, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, code, language, tags, datetime.datetime.now().isoformat()))
        snippet_id = cursor.lastrowid
        self.conn.commit()
        return snippet_id

    def search(self, query: str):
        # Empty query returns all snippets (FTS5 MATCH '' is invalid).
        if not query or not query.strip():
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM snippets ORDER BY id')
            return cursor.fetchall()
        # Don't wrap when the query already contains FTS operators.
        if not re.search(r'["\*\?\+\-]|\bAND\b|\bOR\b|\bNOT\b|\bNEAR\b', query, re.IGNORECASE):
            query = f'"{query}"'
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT s.* FROM snippets s
            JOIN snippets_fts f ON s.id = f.rowid
            WHERE snippets_fts MATCH ?
            ORDER BY rank
        ''', (query,))
        return cursor.fetchall()

    def copy(self, snippet_id: int) -> str:
        """Return a clipboard-friendly string with snippet title and code."""
        row = self.get(snippet_id)
        if row is None:
            raise KeyError(f"No snippet with id {snippet_id}")
        return f"# {row['title']}\n{row['code']}"

    def seed(self, json_path: str) -> int:
        """Import snippets from a JSON file. Returns count of added snippets."""
        with open(json_path, 'r') as f:
            items = json.load(f)
        count = 0
        for item in items:
            tags = item.get('tags', [])
            if isinstance(tags, list):
                tags = ','.join(tags)
            self.add(
                item.get('title', ''),
                item.get('description', ''),
                item.get('code', ''),
                item.get('language') or None,
                tags,
            )
            count += 1
        return count

    def tag(self, snippet_id: int, tags: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE snippets SET tags = ? WHERE id = ?', (tags, snippet_id))
        self.conn.commit()
    def get(self, snippet_id: int):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM snippets WHERE id = ?', (snippet_id,))
        return cursor.fetchone()

    def export(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM snippets')
        return cursor.fetchall()

    def close(self):
        """Close the database connection."""
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="SnipVault CLI")
    parser.add_argument("--db", default="snipvault.db", help="Path to database")
    subparsers = parser.add_subparsers(dest="subcommand")
    
    # Add
    parser_add = subparsers.add_parser("add")
    parser_add.add_argument("--title", required=True)
    parser_add.add_argument("--description")
    parser_add.add_argument("--code", required=True)
    parser_add.add_argument("--language")
    parser_add.add_argument("--tags")
    
    # Search
    parser_search = subparsers.add_parser("search")
    parser_search.add_argument("query")
    
    args = parser.parse_args()
    vault = SnipVault(args.db)
    
    if args.subcommand == "add":
        id = vault.add(args.title, args.description or "", args.code, args.language, args.tags)
        print(f"Added snippet {id}")
    elif args.subcommand == "search":
        results = vault.search(args.query)
        for r in results:
            print(f"{r['id']}: {r['title']} [{r['language']}]")

if __name__ == "__main__":
    main()
