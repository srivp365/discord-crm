import os  # default module

import discord #type:ignore
from discord.ext import tasks #type:ignore
from dotenv import load_dotenv #type:ignore
import datetime
from db.db import add_person_db, get_birthdays, schedule_person, get_next_contact_date, delete_person_from_db, daily_digest, adjust_interval, get_today_birthdays, init_setup, get_all_guild_settings
from db.cache import get_guild_settings, invalidate_settings

load_dotenv()  # load all the variables from the env file
bot = discord.Bot()
TARGET_TIME = datetime.time(hour=8, minute=0, tzinfo=datetime.timezone.utc)
TIER_ORDER = ["close", "core", "active", "dormant"]
INTERACTION_CHOICES=["great", "neutral", "flat"]







@bot.event
async def on_ready():
    daily_debrief.start() #type:ignore
    print(f"{bot.user} is ready and online!")

# bot loop that sends out the daily debrief at 8 am
@tasks.loop(time=TARGET_TIME)
async def daily_debrief():
    all_settings = await get_all_guild_settings()

    for settings in all_settings:
        user = settings["owner_id"]
        debrief_channel = bot.get_channel(settings["digest_channel_id"])
        await debrief_channel.send(f"Good morning!, <@{user}>!, Here's a brief, to keep in touch with your peeps")
        birthday_people = get_today_birthdays(user)
        if len(birthday_people) < 1:
            await debrief_channel.send("Today is nobody's birthday")
        for person in birthday_people:
            await debrief_channel.send(f"Today is {person}'s birthday!, wish them Happy Birthday 🥳")

        await debrief_channel.send(f"Today, you should reach out to the following people to keep in touch: {daily_digest(user)}")

# List functions for auto complete on slash commands
async def get_TIER(ctx : discord.AutocompleteContext):
    return [TIER for TIER in TIER_ORDER if ctx.value.lower() in TIER.lower()]

async def get_interaction_choice(ctx : discord.AutocompleteContext):
    return [CHOICE for CHOICE in INTERACTION_CHOICES if ctx.value.lower() in CHOICE.lower()]

# A command to setup the bot
@bot.slash_command(
    name="setup", description="Initial Setup Wizard"
)
async def setup(
    ctx: discord.ApplicationContext,
    forum_channel: discord.Option(discord.SlashCommandOptionType.channel), #type:ignore
    birthday_channel: discord.Option(discord.SlashCommandOptionType.channel), #type:ignore
    digest_channel: discord.Option(discord.SlashCommandOptionType.channel), #type:ignore
    digest_hour: discord.Option(discord.SlashCommandOptionType.string), #type:ignore
    daily_capacity: discord.Option(discord.SlashCommandOptionType.string), #type:ignore

):

    await ctx.defer()
    init_setup(str(ctx.author.id), str(ctx.guild.id), str(forum_channel.id), str(birthday_channel.id), str(digest_channel.id), digest_hour, daily_capacity)
    invalidate_settings(ctx.guild.id)
    await ctx.respond(f"Alright <@{ctx.author.id}>!, you're setup to use the app. Hope you like it. Feel free to reach out to me (the creator) via discord <@{782998240081084416}>")




# slash command that shows the daily debrief
@bot.slash_command(name="daily_debrief", description="Force a debrief, in case you miss the scheduled one!")
async def daily_debrief_force(ctx: discord.ApplicationContext):
    await ctx.defer()
    settings = await get_guild_settings(ctx.guild.id)
    if settings is None:
        await ctx.respond("This server hasn't run `/setup` yet.")
        return
    channel = bot.get_channel(settings["digest_channel_id"])
    user = settings["owner_id"]
    await ctx.respond(f"Good morning <@{ctx.author.id}>!, Here's a brief, to keep in touch with your peeps")
    birthday_people = get_today_birthdays(user)
    if len(birthday_people) < 1:
        await channel.send("Today is nobody's birthday")
    for person in birthday_people:
        await channel.send(f"Today is {person}'s birthday!, wish them Happy Birthday 🥳")

    await channel.send(f"Today, you should reach out to the following people to keep in touch: {daily_digest(ctx.author.id)}")



@bot.slash_command(name="hello", description="Say hello to the bot")
async def hello(ctx: discord.ApplicationContext):
    await ctx.respond(f"Hey {ctx.author.mention}!, you called?")

@bot.slash_command(name="birthday_list", description="Grab a list of birthdays today")
async def list_birthdays(ctx: discord.ApplicationContext):
    await ctx.defer()
    settings = await get_guild_settings(ctx.guild.id)
    if settings is None:
        await ctx.respond("This server hasn't run `/setup` yet.")
        return
    channel = bot.get_channel(settings["birthdays_channel_id"])
    user = settings["owner_id"]

    await ctx.respond(f"Gimme a sec <@{ctx.author.id}>, grabbing birthdays for the next 6 months")
    birthday_people = get_birthdays(user)
    if len(birthday_people) < 1:
        await channel.send("No birthdays for the next 6 months 🫩")
        return
    list_people = ', '.join(f"{name} ({birthday})" for name, birthday in birthday_people)
    await channel.send(f"Alright!, here's your list: {list_people}")

@bot.slash_command(name="add-person", description="Add a person to your contacts")
async def add_person(
    ctx: discord.ApplicationContext,
    name: discord.Option(discord.SlashCommandOptionType.string), #type:ignore
    common_location: discord.Option(discord.SlashCommandOptionType.string), #type:ignore
    tier: discord.Option(str, "Pick a tier for how close they are with you", autocomplete=get_TIER), #type:ignore
    note: discord.Option(discord.SlashCommandOptionType.string, required=False), #type:ignore
    birthday: discord.Option(discord.SlashCommandOptionType.string, required=False), #type:ignore
):
    await ctx.defer(ephemeral=True)

    settings = await get_guild_settings(ctx.guild.id)
    if settings is None:
        await ctx.respond("This server hasn't run `/setup` yet.")
        return

    forum = bot.get_channel(settings["forum_channel_id"])
    if forum is None:
        await ctx.respond("Couldn't find the configured forum channel — check your `/setup` values.", ephemeral=True)
        return

    if note and birthday and tier:
        content = (
            f"First Contact: {common_location}\nNote: {note}\nBirthday: {birthday}\nTier: {tier}"
        )
    elif note and birthday:
        content = (
            f"First Contact: {common_location}\nNote: {note}\nBirthday: {birthday}"
        )
    elif note:
        content = f"First Contact: {common_location}\nNote: {note}"
    elif birthday:
        content = f"First Contact: {common_location}\nBirthday: {birthday}"
    elif tier:
        content = f"First Contact: {common_location}\nTier: {tier}"
    else:
        content = f"First Contact: {common_location}"

    thread = await forum.create_thread(
        name=name,
        content=content,
    )

    add_person_db(name, common_location, birthday, tier, thread.id, ctx.author.id)
    schedule_person(thread.id, datetime.datetime.now(datetime.timezone.utc).date(), int(settings["forum_channel_id"]), settings["owner_id"])
    await ctx.respond(f"Post created successfully: {thread.mention}!, I've scheduled your next chat with {thread.name} on {get_next_contact_date(thread.id)}", ephemeral=True)

@bot.slash_command(
    name="interaction-update", description="Tell the bot how your interaction went, so it schedules your next chat"
)
async def interaction_update(
    ctx: discord.ApplicationContext,

    outcome: discord.Option(str, "Pick a choice for how your interaction went", autocomplete=get_interaction_choice), #type:ignore

):
    await ctx.defer(ephemeral=True)
    settings = await get_guild_settings(ctx.guild.id)
    if settings is None:
        await ctx.respond("This server hasn't run `/setup` yet.")
        return

    thread_id = ctx.channel.id
    adjust_interval(thread_id, outcome)
    schedule_person(thread_id, datetime.datetime.now(datetime.timezone.utc).date(), int(settings["forum_channel_id"]), settings["owner_id"])
    next_date = get_next_contact_date(thread_id)
    await ctx.respond(f"Got it! Next scheduled chat: {next_date}", ephemeral=True)



# A command to update/edit people
@bot.slash_command(
    name="add-note", description="Add a note to a person in your contacts"
)
async def add_note(
    ctx: discord.ApplicationContext,
    note: discord.Option(discord.SlashCommandOptionType.string), #type:ignore
):
    try:
        thread_id = ctx.channel.id
        # Convert the ID string to an integer
        channel_id = int(thread_id)

        # Fetch the forum post (threads are treated as channels)
        thread = await bot.fetch_channel(channel_id)

        # Verify the channel is actually a thread/forum post
        if isinstance(thread, discord.Thread):
            await thread.send(f"Update: {note}")
            await ctx.respond(
                f"Successfully sent message to post: {thread.name}", ephemeral=True
            )
        else:
            await ctx.respond(
                "The provided ID is not a forum post/thread.", ephemeral=True
            )
    except discord.HTTPException as e:
        await ctx.respond(f"Failed to add note: {e}", ephemeral=True)


# A command to delete people
@bot.slash_command(
    name="delete-person", description="Delete a person in your contacts"
)
async def delete_person(
    ctx: discord.ApplicationContext,
):
    await ctx.defer()


    thread_id = ctx.channel.id
    thread_name = ctx.channel.name

    deleted = delete_person_from_db(thread_id=thread_id)

    if not deleted:
        await ctx.respond("This doesn't look like a contact thread — nothing was deleted.")
        return

    await ctx.respond(f"Alright! Removed {thread_name} from your database. Deleting thread now.")
    await ctx.channel.delete()

# clear bot messages, written by AI
@bot.slash_command(
    name="clear-bot-messages", description="Delete the bot's last 'count' messages in this channel"
)
async def clear_bot_messages(ctx: discord.ApplicationContext, count: discord.Option(discord.SlashCommandOptionType.integer)):
    await ctx.defer(ephemeral=True)

    deleted = await ctx.channel.purge(
        limit=100,  # scan up to 100 recent messages looking for matches
        check=lambda m: m.author == bot.user,
    )
    deleted = deleted[:count]  # purge deletes everything matching within the scan window — trim to last 10

    await ctx.respond(f"Deleted {len(deleted)} of my messages.", ephemeral=True)


bot.run(os.getenv("TOKEN"))  # run the bot with the token
