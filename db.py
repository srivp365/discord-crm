import os

import libsql
from dotenv import load_dotenv
from datetime import datetime, timezone


load_dotenv()  # load all the variables from the env file



# establish a connection to db
conn = libsql.connect(
    database=os.environ["TURSO_DATABASE_URL"],
    auth_token=os.environ["TURSO_AUTH_TOKEN"],
)


conn.execute("ALTER TABLE people ADD last_conected TEXT")


def add_person_db(name, common_location, birthday):
    conn.execute(
        "INSERT INTO people (name, common_location, birthday) VALUES (?, ?, ?)",
        (name, common_location, birthday),
    )
    conn.commit()

def get_birthdays():
    # grab today's date
    today_utc = datetime.now(timezone.utc)
    today_month_day = today_utc.strftime("%m-%d")

    # grab birthdays
    todays_birthdays = conn.execute(
        "SELECT name FROM people WHERE strftime('%m-%d', birthday) = ?",
        (today_month_day,)
    ).fetchall()

    print(f"These are the birthdays!: {todays_birthdays}")
    return todays_birthdays
