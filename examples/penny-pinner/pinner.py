import sqlite3
import re

class PennyPinner:
    def __init__(self, db_path="pinner.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS bookmarks USING fts5(url, title, content)")
        self.conn.row_factory = sqlite3.Row

    def add(self, url, title, content):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO bookmarks (url, title, content) VALUES (?, ?, ?)", (url, title, content))
        self.conn.commit()
        return cursor.lastrowid

    def search(self, query):
        cursor = self.conn.cursor()
        cursor.execute("SELECT *, rank FROM bookmarks WHERE bookmarks MATCH ? ORDER BY rank", (query,))
        return [dict(row) for row in cursor.fetchall()]

    def generate_digest(self, content):
        # Very simple extractive digest: pick 3 longest sentences (approximation)
        sentences = re.split(r'(?<=[.!?])\s+', content)
        # Simple sorting by length
        sentences.sort(key=len, reverse=True)
        return sentences[:3]
