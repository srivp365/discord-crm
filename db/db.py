from calendar import month
import os

import libsql
from dotenv import load_dotenv
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



def add_person_db(name, common_location, birthday, tier, thread_id):
    row = conn.execute(
        "INSERT INTO people (name, common_location, birthday, tier, thread_id) VALUES (?, ?, ?, ?, ?) RETURNING *",
        (name, common_location, birthday, tier, thread_id),
    ).fetchone()
    conn.commit()
    return row


def delete_person_from_db(thread_id):
    conn.execute(
        "DELETE FROM people WHERE thread_id = ?",
        (thread_id,)
    )

def get_birthdays():
    # grab today's date
    today_utc = datetime.now(timezone.utc)
    today_month_day = today_utc.strftime("%m-%d")
    six_month_day = (today_utc + timedelta(weeks=24)).strftime("%m-%d")

    # grab birthdays
    todays_birthdays = conn.execute(
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
           conn.execute(
               "UPDATE people SET next_contact_date = (?) WHERE id == (?)",
               (candidate.strftime("%Y-%m-%d"), person[0])
           )
           return


   best = min(
        (ideal + timedelta(days=o) for o in offsets if ideal + timedelta(days=o) > today ),
        key = count_scheduled
    )

   conn.execute(
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

    conn.execute(
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
    result = conn.execute(
        "SELECT COUNT(*) FROM people WHERE next_contact_date = ?",
        (date.strftime("%Y-%m-%d"),)
    ).fetchone()
    return result[0]

def get_next_contact_date(person_thread):
    row = conn.execute(
        "SELECT next_contact_date FROM people WHERE thread_id == ?",
        (person_thread,)
    ).fetchone()
    return row[0] if row else None


def daily_digest():
    peeps = conn.execute(
        "SELECT name FROM people WHERE next_contact_date = today() ORDER BY tier LIMIT 2;"
    ).fetchone()
    return peeps[0]
