# Fix for FTS5 operator handling in SnipVault
# FTS5 syntax does NOT treat "AND", "OR", "NOT" as operators if not uppercase,
# and it supports basic quoting.
# Let's try matching everything if query is empty.

import sqlite3
import re

# Mocking the behavior to test
def mock_search(query):
    if not query.strip():
        return "SELECT ALL"
    
    # FTS operators are AND, OR, NOT, NEAR, *, +, -
    # If the query contains any of these as FTS operators, don't wrap it.
    
    # Simple check for FTS special chars 
    if re.search(r'[\"\*\?\+\-]', query):
        return f"MATCH {query}"
        
    # Check for FTS operator words
    if re.search(r'\b(AND|OR|NOT|NEAR)\b', query, re.I):
        return f"MATCH {query}"
        
    return f"MATCH \"{query}\""

print(f"Empty: {mock_search('')}")
print(f"Hello: {mock_search('hello')}")
print(f"Hello AND World: {mock_search('hello AND world')}")
print(f"Hello * World: {mock_search('hello * world')}")
