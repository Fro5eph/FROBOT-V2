import os
import json
import discord
from discord.ext import commands

DATA_FILE = "lists.json"

# ----------- Data Persistence -----------
def load_lists():
    """Load lists from disk if file exists, otherwise return empty dict."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_lists():
    """Save current lists to disk."""
    with open(DATA_FILE, "w") as f:
        json.dump(lists, f, indent=4)

# Load stored lists at startup
lists = load_lists()

# ----------- Discord Bot Setup -----------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
intents.guild_messages = True
intents.guild_reactions = True
intents.guild_presences = False

# Disable default help command so we can use our own
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')

@bot.command(name='help')
async def help_command(ctx):
    help_text = (
        "**Available Commands:**\n"
        "`!newlist <title>` - Create a new list for this channel.\n"
        "`!add <item>` - Add an item to this channel's list.\n"
        "`!showlist` - Show the current list.\n"
        "`!clearlist` - Clear the current list.\n"
        "`!help` - Show this help message."
    )
    await ctx.send(help_text)

@bot.command(name='newlist')
async def new_list(ctx, *, title: str):
    channel_id = str(ctx.channel.id)  # Use string keys for JSON compatibility
    lists[channel_id] = {"title": title, "items": []}
    save_lists()
    await ctx.send(f"New list **{title}** created for this channel!")

@bot.command(name='add')
async def add_item(ctx, *, item: str):
    channel_id = str(ctx.channel.id)
    if channel_id not in lists:
        await ctx.send("No list found for this channel. Use `!newlist <title>` first.")
        return
    lists[channel_id]["items"].append(item)
    save_lists()
    await ctx.send(f"Added `{item}` to the list.")

@bot.command(name='showlist')
async def show_list(ctx):
    channel_id = str(ctx.channel.id)
    if channel_id not in lists:
        await ctx.send("No list found for this channel. Use `!newlist <title>` first.")
        return
    title = lists[channel_id]["title"]
    items = lists[channel_id]["items"]
    if not items:
        await ctx.send(f"The list **{title}** is currently empty.")
        return
    formatted_items = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
    await ctx.send(f"**{title}**\n{formatted_items}")

@bot.command(name='clearlist')
async def clear_list(ctx):
    channel_id = str(ctx.channel.id)
    if channel_id not in lists:
        await ctx.send("No list found for this channel. Use `!newlist <title>` first.")
        return
    lists[channel_id]["items"].clear()
    save_lists()
    await ctx.send(f"List **{lists[channel_id]['title']}** has been cleared.")

# ----------- Run Bot -----------
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
