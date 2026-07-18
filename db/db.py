import os

import libsql #type:ignore
from dotenv import load_dotenv #type:ignore
from datetime import datetime, timezone, timedelta

load_dotenv()  # load all the variables from the env file

DAILY_CAPACITY = 3
SEARCH_WINDOW = 7
TIER_DEFAULTS = {
    "close": 4,
    "core": 14,
    "active": 24,
    "dormant": 49,
}
TIER_ORDER = ["close", "core", "active", "dormant"]



# establish a connection to db
conn = libsql.connect(
    database=os.environ["TURSO_DATABASE_URL"],
    auth_token=os.environ["TURSO_AUTH_TOKEN"],
)



# ensures that db connection timeouts don't break the app
def execute_with_retry(query, params=()):
    global conn
    try:
        return conn.execute(query, params)
    except ValueError as e:
        if "stream not found" in str(e):
            conn = libsql.connect(
                database=os.environ["TURSO_DATABASE_URL"],
                auth_token=os.environ["TURSO_AUTH_TOKEN"],
            )
            return conn.execute(query, params)
        raise


def add_person_db(name, common_location, birthday, tier, thread_id):
    row = execute_with_retry(
        "INSERT INTO people (name, common_location, birthday, tier, thread_id) VALUES (?, ?, ?, ?, ?) RETURNING *",
        (name, common_location, birthday, tier, str(thread_id)), # explicit casting to fix thread_id truncation error
    ).fetchone()
    conn.commit()
    return row


def delete_person_from_db(thread_id):
    cursor = execute_with_retry(
        "DELETE FROM people WHERE thread_id = ?",
        (str(thread_id),)
    )
    conn.commit()
    return cursor.rowcount > 0

def get_birthdays():
    # grab today's date
    today_utc = datetime.now(timezone.utc)
    today_month_day = today_utc.strftime("%m-%d")
    six_month_day = (today_utc + timedelta(weeks=24)).strftime("%m-%d")

    # grab birthdays
    todays_birthdays = execute_with_retry(
        "SELECT name FROM people WHERE strftime('%m-%d', birthday) BETWEEN ? AND ?",
        (today_month_day, six_month_day)
    ).fetchall()

    return todays_birthdays


def schedule_person(person, today):
    # calculates the ideal next contact date using person tier
   ideal =  today + timedelta(days=TIER_DEFAULTS[person[5]])

   offsets = [0]
   for i in range (1, SEARCH_WINDOW+1):
       offsets += [i, -i]

   for offset in offsets:
       candidate = ideal + timedelta(days=offset)
       if candidate <= today:
          continue
       if count_scheduled(candidate) < DAILY_CAPACITY:
           execute_with_retry(
               "UPDATE people SET next_contact_date = (?) WHERE id == (?)",
               (candidate.strftime("%Y-%m-%d"), person[0])
           )
           return


   best = min(
        (ideal + timedelta(days=o) for o in offsets if ideal + timedelta(days=o) > today ),
        key = count_scheduled
    )

   execute_with_retry(
       "UPDATE people SET next_contact_date = (?) WHERE id == (?)",
       (best.strftime("%Y-%m-%d"), person[0])
   )

   return


def adjust_interval(person, outcome):
    if outcome == "great":
        person.target_interval_days = max(1, int(person.target_interval_days * 0.8))
        person.flat_streak = 0
    elif outcome == "neutral":
        person.flat_streak = 0
    elif outcome == "flat":
        person.target_interval_days = min(int(person.target_interval_days * 1.3), 180)
        person.flat_streak += 1
        if person.flat_streak >= 3:
            person.tier = demote(person.tier)
            person.flat_streak = 0

    execute_with_retry(
        "UPDATE people SET target_interval_days = ?, tier = ?, flat_streak = ? WHERE id = ?",
        (person.target_interval_days, person.tier, person.flat_streak, person.id)
    )
    conn.commit()


# demote function to move drop someone down a tier
def demote(tier):
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]

# check how many people are scheduled for a given date
def count_scheduled(date):
    result = execute_with_retry(
        "SELECT COUNT(*) FROM people WHERE next_contact_date = ?",
        (date.strftime("%Y-%m-%d"),)
    ).fetchone()
    return result[0]

def get_next_contact_date(person_thread):
    row = execute_with_retry(
        "SELECT next_contact_date FROM people WHERE thread_id == ?",
        (person_thread,)
    ).fetchone()
    return row[0] if row else None


def daily_digest():
    today_utc = datetime.now(timezone.utc)
    today_month_day = today_utc.strftime("%Y-%m-%d")
    peeps = execute_with_retry(
        "SELECT name FROM people WHERE next_contact_date = ? ORDER BY tier LIMIT 2;",
        (today_month_day, )
    ).fetchall()
    if peeps is None or len(peeps) == 0:
        return "Nobody 🫠"
    names = [row[0] for row in peeps]
    return ", ".join(names)
