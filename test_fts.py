import sqlite3
conn = sqlite3.connect(':memory:')
conn.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
conn.execute("INSERT INTO t VALUES ('a'), ('b')")
curs = conn.cursor()
curs.execute("SELECT * FROM t WHERE t MATCH ?", (""))
res = curs.fetchall()
print(f"Results for MATCH '': {res}")

curs.execute("SELECT * FROM t WHERE t MATCH ?", ('""',))
res = curs.fetchall()
print(f"Results for MATCH '\"\"': {res}")
