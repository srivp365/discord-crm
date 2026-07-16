import os  # default module

import discord
from discord.ext import tasks
from discord.commands import Option
from dotenv import load_dotenv
import datetime
from db.db import add_person_db, get_birthdays

load_dotenv()  # load all the variables from the env file
bot = discord.Bot()
client = discord.Client()
target_time = datetime.time(hour=8, minute=0, tzinfo=datetime.timezone.utc)

@bot.event
async def on_ready():
    print(f"{bot.user} is ready and online!")

# bot loop that sends out birthday message at the right time
@tasks.loop(time=target_time)
async def birthdays():
    channel_id = 1525865399680368652
    channel = bot.get_channel(channel_id)
    await channel.send(f"Good morning!, {client.user}")
    birthday_people = get_birthdays()
    if len(birthday_people) < 1:
        await channel.send("Today is nobody's birthday")
    for person in birthday_people:
        await channel.send(f"Today is {person}'s birthday!, wish them Happy Birthday 🥳")


@bot.slash_command(name="hello", description="Say hello to the bot")
async def hello(ctx: discord.ApplicationContext):
    await ctx.respond("Hey!")

@bot.slash_command(name="birthday_list", description="Grab a list of birthdays today")
async def list_birthdays(ctx: discord.ApplicationContext):
    channel_id = 1525865399680368652
    channel = bot.get_channel(channel_id)
    await channel.send(f"Good morning!, {client.user}")
    birthday_people = get_birthdays()
    print(birthday_people)
    if len(birthday_people) < 1:
        await channel.send("Today is nobody's birthday")
    for person in birthday_people:
        await channel.send(f"Today is {person}'s birthday!, wish them Happy Birthday 🥳")

# A command to add people
@bot.slash_command(name="add-person", description="Add a person to your contacts")
async def add_person(
    ctx: discord.ApplicationContext,
    name: discord.Option(discord.SlashCommandOptionType.string),
    common_location: discord.Option(discord.SlashCommandOptionType.string),
    note: discord.Option(discord.SlashCommandOptionType.string, required=False),
    birthday: discord.Option(discord.SlashCommandOptionType.string, required=False),
):

    forum_channel = bot.get_channel(1525865745504931940)
    if note and birthday:
        content = (
            f"First Contact: {common_location} \n Note: {note} \n Birthday: {birthday}"
        )
    elif note:
        content = content = f"First Contact: {common_location} \n Note: {note}"
    elif birthday:
        content = f"First Contact: {common_location}\nBirthday: {birthday}"
    else:
        content = f"First Contact: {common_location}"
    thread = await forum_channel.create_thread(
        name=name,
        content=content,
    )

    add_person_db(name, common_location, birthday)
    await ctx.respond(f"Post created successfully: {thread.mention}!", ephemeral=True)


# A command to update/edit people
@bot.slash_command(
    name="add-note", description="Add a note to a person in your contacts"
)
async def add_note(
    ctx: discord.ApplicationContext,
    thread_id: discord.Option(discord.SlashCommandOptionType.string),
    note: discord.Option(discord.SlashCommandOptionType.string),
):
    try:
        # Convert the ID string to an integer
        channel_id = int(thread_id)

        # Fetch the forum post (threads are treated as channels)
        thread = await bot.fetch_channel(channel_id)

        # Verify the channel is actually a thread/forum post
        if isinstance(thread, discord.Thread):
            await thread.send(note)
            await ctx.respond(
                f"Successfully sent message to post: {thread.name}", ephemeral=True
            )
        else:
            await ctx.respond(
                "The provided ID is not a forum post/thread.", ephemeral=True
            )
    except:
        await ctx.respond(f"Failed to add note to {thread.name}", ephemeral=True)


bot.run(os.getenv("TOKEN"))  # run the bot with the token
