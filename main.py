import os  # default module

import discord #type:ignore
from discord.ext import tasks #type:ignore
from dotenv import load_dotenv #type:ignore
import datetime
from db.db import add_person_db, get_birthdays, schedule_person, get_next_contact_date, delete_person_from_db, daily_digest, adjust_interval

load_dotenv()  # load all the variables from the env file
bot = discord.Bot()
TARGET_TIME = datetime.time(hour=8, minute=0, tzinfo=datetime.timezone.utc)
TIER_ORDER = ["close", "core", "active", "dormant"]
INTERACTION_CHOICES=["great", "neutral", "flat"]
USER_ID = int(os.environ["USER_ID"])
BIRTHDAYS_CHANNEL = int(os.environ["BIRTHDAYS_CHANNEL"])
DEBRIEF_CHANNEL = int(os.environ["DEBRIEF_CHANNEL"])
FORUM_CHANNEL = int(os.environ["FORUM_CHANNEL"])

@bot.event
async def on_ready():
    daily_debrief.start()
    print(f"{bot.user} is ready and online!")

# bot loop that sends out the daily debrief at 8 am
@tasks.loop(time=TARGET_TIME)
async def daily_debrief():
    channel = bot.get_channel(BIRTHDAYS_CHANNEL)
    await channel.send(f"Good morning!, <@{USER_ID}>!, Here's a brief, to keep in touch with your peeps")
    birthday_people = get_birthdays()
    if len(birthday_people) < 1:
        await channel.send("Today is nobody's birthday")
    for person in birthday_people:
        await channel.send(f"Today is {person}'s birthday!, wish them Happy Birthday 🥳")

    await channel.send(f"Today, you should reach out to the following people to keep in touch: {daily_digest()}")

# a list for auto completeting the tier portion of the add person query
async def get_TIER(ctx : discord.AutocompleteContext):
    return [TIER for TIER in TIER_ORDER if ctx.value.lower() in TIER.lower()]

async def get_interaction_choice(ctx : discord.AutocompleteContext):
    return [CHOICE for CHOICE in INTERACTION_CHOICES if ctx.value.lower() in CHOICE.lower()]


# slash command that shows the daily debrief
@bot.slash_command(name="daily_debrief", description="Force a debrief, in case you miss the scheduled one!")
async def daily_debrief_force(ctx: discord.ApplicationContext):
    channel = bot.get_channel(DEBRIEF_CHANNEL)
    await ctx.defer()
    await ctx.respond(f"Good morning <@{USER_ID}>!, Here's a brief, to keep in touch with your peeps")
    birthday_people = get_birthdays()
    if len(birthday_people) < 1:
        await channel.send("Today is nobody's birthday")
    for person in birthday_people:
        await channel.send(f"Today is {person}'s birthday!, wish them Happy Birthday 🥳")

    await channel.send(f"Today, you should reach out to the following people to keep in touch: {daily_digest()}")



@bot.slash_command(name="hello", description="Say hello to the bot")
async def hello(ctx: discord.ApplicationContext):
    await ctx.respond(f"Hey {ctx.author.mention}!, you called?")

@bot.slash_command(name="birthday_list", description="Grab a list of birthdays today")
async def list_birthdays(ctx: discord.ApplicationContext):
    channel = bot.get_channel(BIRTHDAYS_CHANNEL)
    await ctx.respond(f"Gimme a sec <@{USER_ID}>, grabbing birthdays for the next 6 months")
    birthday_people = get_birthdays()
    if len(birthday_people) < 1:
        await channel.send("No birthdays for the next 6 months 🫩")
        return
    list_people = ', '.join(birthday_people)
    await channel.send(f"Alright!, here's your list: {list_people}")

# A command to add people
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

    forum_channel = bot.get_channel(FORUM_CHANNEL)
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
    thread = await forum_channel.create_thread(
        name=name,
        content=content,
    )


    schedule_person(add_person_db(name, common_location, birthday, tier, thread.id), datetime.datetime.now(datetime.timezone.utc).date())
    await ctx.respond(f"Post created successfully: {thread.mention}!, I've scheduled your next chat with {thread.name} on {get_next_contact_date(thread.id)}", ephemeral=True)

@bot.slash_command(
    name="interaction-update", description="Tell the bot how your interaction went, so it schedules your next chat"
)
async def interaction_update(
    ctx: discord.ApplicationContext,
    outcome: discord.Option(str, "Pick a choice for how your interaction went", autocomplete=get_interaction_choice), #type:ignore

):
    await ctx.defer(ephemeral=True)
    thread_id = ctx.channel.id
    adjust_interval(thread_id, outcome)
    schedule_person(thread_id, datetime.datetime.now(datetime.timezone.utc).date())
    next_date = get_next_contact_date(thread_id)
    await ctx.respond(f"Got it! Next scheduled chat: {next_date}", ephemeral=True)



# A command to update/edit people
@bot.slash_command(
    name="add-note", description="Add a note to a person in your contacts"
)
async def add_note(
    ctx: discord.ApplicationContext,
    thread_id: discord.Option(discord.SlashCommandOptionType.string), #type:ignore
    note: discord.Option(discord.SlashCommandOptionType.string), #type:ignore
):
    try:
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
    except:
        await ctx.respond(f"Failed to add note to {thread.name}", ephemeral=True) #type:ignore



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



bot.run(os.getenv("TOKEN"))  # run the bot with the token
