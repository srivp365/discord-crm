import os  # default module

import discord
from discord.commands import Option
from dotenv import load_dotenv

load_dotenv()  # load all the variables from the env file
bot = discord.Bot()


@bot.event
async def on_ready():
    print(f"{bot.user} is ready and online!")


@bot.slash_command(name="hello", description="Say hello to the bot")
async def hello(ctx: discord.ApplicationContext):
    await ctx.respond("Hey!")


# A command to add people
@bot.slash_command(name="add-person", description="Add a person to your contacts")
async def add_person(
    ctx: discord.ApplicationContext,
    name: discord.Option(discord.SlashCommandOptionType.string),
    common_location: discord.Option(discord.SlashCommandOptionType.string),
    note: discord.Option(discord.SlashCommandOptionType.string, required=False),
):
    forum_channel = bot.get_channel(1525865745504931940)
    if note:
        content = f"Meeting Spot: {common_location} \n Note: {note}"
    else:
        content = f"Meeting Spot: {common_location}"

    thread = await forum_channel.create_thread(
        name=name,
        content=content,
    )
    await ctx.respond(f"Post created successfully: {thread.mention}!", ephemeral=True)


bot.run(os.getenv("TOKEN"))  # run the bot with the token
