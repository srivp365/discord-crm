import os
from dataclasses import dataclass
import libsql #type:ignore
from dotenv import load_dotenv #type:ignore
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet


load_dotenv()  # load all the variables from the env file

KEY = os.environ["ENCRYPTION_KEY"].encode()
cipher = Fernet(KEY)

DAILY_CAPACITY = 3
SEARCH_WINDOW = 7
TIER_DEFAULTS = {
    "close": 4,
    "core": 14,
    "active": 24,
    "dormant": 49,
}
TIER_ORDER = ["close", "core", "active", "dormant"]

# define a person mini class to make it easier to manage responses
@dataclass
class Person:
    id: int
    name: str
    common_location: str
    birthday: str
    tier: str
    interval: int
    flat_streak: int
    thread_id: str
    next_contact_date: str


    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        id, name, common_location, birthday, tier, interval, flat_streak, thread_id, next_contact_date = row
        return cls(
            id=id,
            name=decrypt(name),
            common_location=decrypt(common_location),
            birthday=birthday,   # not encrypted, per what we settled on last message
            tier=tier,
            interval=interval,
            flat_streak=flat_streak,
            thread_id=thread_id,
            next_contact_date = next_contact_date
        )

def encrypt(value: str) -> str:
    if value is None:
        return None
    return cipher.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    if value is None:
        return None
    return cipher.decrypt(value.encode()).decode()


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


def init_setup(owner_id, guild_id, forum_channel_id, birthdays_channel_id, digest_channel_id, digest_hour, daily_capacity):
    execute_with_retry(
        "INSERT INTO guild_settings (owner_id, guild_id, forum_channel_id, birthdays_channel_id, digest_channel_id, digest_hour, daily_capacity, created_at) VALUES (?, ?, ?, ?, ?, ? ,?)",
        (owner_id, guild_id, forum_channel_id, birthdays_channel_id, digest_channel_id, digest_hour, daily_capacity)
    )


def get_person(thread_id):
    row = execute_with_retry(
        "SELECT id, name, common_location, birthday, tier, interval, flat_streak, thread_id, next_contact_date FROM people WHERE thread_id = ?",
        (str(thread_id),)
    ).fetchone()
    return Person.from_row(row)


def add_person_db(name, common_location, birthday, tier, thread_id):
    interval = TIER_DEFAULTS[tier]
    last_connected = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = execute_with_retry(
        "INSERT INTO people (name, common_location, birthday, tier, thread_id, interval, last_conected) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *", # typo on purpose because I named the column wrong :sob:
        (encrypt(name), encrypt(common_location), encrypt(birthday), tier, str(thread_id), interval, last_connected), # explicit casting to fix thread_id truncation error
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

# interesting logic suggested by Claude, combine year and date into a single number using month * 100 + day
def get_birthdays():
    today_utc = datetime.now(timezone.utc)
    today_key = today_utc.month * 100 + today_utc.day
    six_month_date = today_utc + timedelta(weeks=24)
    six_month_key = six_month_date.month * 100 + six_month_date.day

    if today_key <= six_month_key:
        query = """
            SELECT name, birthday FROM people
            WHERE (birth_month * 100 + birth_day) BETWEEN ? AND ?
        """
        params = (today_key, six_month_key)
    else:
        query = """
            SELECT name, birthday FROM people
            WHERE (birth_month * 100 + birth_day) >= ?
                OR (birth_month * 100 + birth_day) <= ?
        """
        params = (today_key, six_month_key)

    return execute_with_retry(query, params).fetchall()

def get_today_birthdays():
    today_utc = datetime.now(timezone.utc)

    query = "SELECT name FROM people WHERE birth_month = ? AND birth_day = ?"
    params = (today_utc.month, today_utc.day)

    return execute_with_retry(query, params).fetchall()


def schedule_person(thread_id, today):
    person = get_person(thread_id)
    if person is None:
        return

    ideal = today + timedelta(days=person.interval)

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
               (candidate.strftime("%Y-%m-%d"), person.id)
           )
           conn.commit()


           return


    best = min(
        (ideal + timedelta(days=o) for o in offsets if ideal + timedelta(days=o) > today ),
        key = count_scheduled
    )

    execute_with_retry(
       "UPDATE people SET next_contact_date = (?) WHERE id == (?)",
       (best.strftime("%Y-%m-%d"), person.id)
    )
    conn.commit()

    return

def adjust_interval(thread_id, outcome):
    person = get_person(thread_id)
    if person is None:
        return

    if outcome == "great":
        person.interval = max(1, int(person.interval * 0.8))
        person.flat_streak = 0
    elif outcome == "neutral":
        person.flat_streak = 0
    elif outcome == "flat":
        person.interval = min(int(person.interval * 1.3), 180)
        person.flat_streak += 1
        if person.flat_streak >= 3:
            person.tier = demote(person.tier)
            person.flat_streak = 0

    execute_with_retry(
        "UPDATE people SET interval = ?, tier = ?, flat_streak = ? WHERE id = ?",
        (person.interval, person.tier, person.flat_streak, person.id)
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
        (str(person_thread),)
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
