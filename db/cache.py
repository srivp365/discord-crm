from db.db import execute_with_retry

# the _ in this means it's to be used by the functions (since python doesn't have a private keyword)
_guild_settings_cache : dict[int, dict] = {}

async def get_guild_settings(guild_id):
    if guild_id in _guild_settings_cache:
        return _guild_settings_cache[guild_id]

    result = execute_with_retry(
        """SELECT forum_channel_id, birthdays_channel_id, digest_channel_id,
                  digest_hour, daily_capacity, owner_id
           FROM guild_settings WHERE guild_id = ?""",
        (str(guild_id),)
    )
    row = result.fetchone()
    if row is None:
        return None

    settings = {
        "forum_channel_id": int(row[0]),
        "birthdays_channel_id": int(row[1]),
        "digest_channel_id": int(row[2]),
        "digest_hour": int(row[4]),
        "daily_capacity": row[4],
        "owner_id": int(row[5]),
    }

    _guild_settings_cache[guild_id] = settings
    return settings
def invalidate_settings(guild_id):
    _guild_settings_cache.pop(guild_id, None)
