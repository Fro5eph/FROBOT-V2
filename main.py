import os
import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime

# Set up intents
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
intents.guild_messages = True
intents.guild_reactions = True
intents.presences = False

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

# Remove the default help command so we can define our own
bot.remove_command('help')

# Data structures
lists = {}  # {channel_id: {team_role_id: TeamList}}
rank_roles = {}  # {guild_id: {role_id: {'priority': int, 'name': str}}}
custom_parameters = {}  # {guild_id: {param_name: [role_ids]}}
guild_settings = {}  # {guild_id: {'embed_color': hex}}

class TeamList:
    def __init__(self, team_role_id):
        self.team_role_id = team_role_id
        self.hidden_roles = set()
        self.message_id = None
        self.last_updated = Noneasync def update_list(channel_id, guild):
    """Updates the list embed in the given channel."""
    if channel_id not in lists:
        return

    channel_lists = lists[channel_id]
    for team_role_id, team_list in channel_lists.items():
        role = guild.get_role(team_role_id)
        if not role:
            continue

        members = [m for m in guild.members if role in m.roles]
        members.sort(key=lambda m: m.top_role.position, reverse=True)

        embed_color = guild_settings.get(guild.id, {}).get('embed_color', 0x00ff00)
        embed = discord.Embed(
            title=f"Team: {role.name}",
            color=embed_color,
            timestamp=datetime.utcnow()
        )

        for member in members:
            embed.add_field(
                name=member.display_name,
                value=f"Top role: {member.top_role.name}",
                inline=False
            )

        try:
            channel = guild.get_channel(channel_id)
            if team_list.message_id:
                msg = await channel.fetch_message(team_list.message_id)
                await msg.edit(embed=embed)
            else:
                msg = await channel.send(embed=embed)
                team_list.message_id = msg.id

            team_list.last_updated = datetime.utcnow()

        except discord.NotFound:
            team_list.message_id = None
        except discord.Forbidden:
            print(f"Missing permissions to edit messages in {channel.name}")
        except discord.HTTPException as e:
            print(f"Failed to update list in {channel.name}: {e}")


@tasks.loop(minutes=5)
async def periodic_update():
    """Background loop to refresh all lists every 5 minutes."""
    for guild in bot.guilds:
        for channel_id in lists.keys():
            await update_list(channel_id, guild)


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    periodic_update.start()@bot.command(name="help")
async def help_command(ctx):
    """Custom help command."""
    embed = discord.Embed(
        title="Bot Commands",
        description="Here’s what I can do:",
        color=0x3498db
    )
    embed.add_field(name="!help", value="Shows this help message.", inline=False)
    embed.add_field(name="!createlist <@role>", value="Creates a team list for a specific role.", inline=False)
    embed.add_field(name="!updatelist", value="Manually updates the team list.", inline=False)
    embed.add_field(name="!setcolor <hex>", value="Sets the embed color. Example: `!setcolor #ff0000`", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="createlist")
async def create_list(ctx, role: discord.Role):
    """Creates a new team list for a role."""
    channel_id = ctx.channel.id
    guild_id = ctx.guild.id

    if channel_id not in lists:
        lists[channel_id] = {}

    lists[channel_id][role.id] = TeamList(role.id)
    await ctx.send(f"✅ Created list for role **{role.name}** in this channel.")
    await update_list(channel_id, ctx.guild)


@bot.command(name="updatelist")
async def update_list_command(ctx):
    """Manually update all lists in this channel."""
    await update_list(ctx.channel.id, ctx.guild)
    await ctx.send("🔄 Lists updated.")


@bot.command(name="setcolor")
async def set_color(ctx, hex_color: str):
    """Sets the embed color for this guild."""
    if not hex_color.startswith("#") or len(hex_color) != 7:
        await ctx.send("❌ Please provide a valid hex color. Example: `#ff0000`")
        return

    color_value = int(hex_color[1:], 16)
    guild_settings[ctx.guild.id] = {"embed_color": color_value}
    await ctx.send(f"✅ Embed color set to `{hex_color}`.")# Run the bot
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("❌ ERROR: DISCORD_BOT_TOKEN not found in environment variables.")
else:
    bot.run(TOKEN)
