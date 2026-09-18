import sqlite3
import re

query = ""
if not re.search(r'[\"\*\?\+\-]', query):
    query = f'"{query}"'
print(f"'{query}'")
