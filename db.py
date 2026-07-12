import os

import libsql
from dotenv import load_dotenv

load_dotenv()  # load all the variables from the env file
conn = libsql.connect(
    database=os.environ["TURSO_DATABASE_URL"],
    auth_token=os.environ["TURSO_AUTH_TOKEN"],
)

conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)")
conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
conn.commit()

rows = conn.execute("SELECT * FROM users").fetchall()
print(rows)
