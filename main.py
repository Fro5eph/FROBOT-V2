import os
import discord
from discord.ext import commands

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

# Data structure: {channel_id: {team_role_id: TeamList}}
lists = {}

class TeamList:
    def __init__(self, team_role_id):
        self.team_role_id = team_role_id
        self.hidden_roles = set()
        self.message_id = None

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}!")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # Send startup message to all servers
    for guild in bot.guilds:
        channel = None
        
        # Look for common channel names
        for ch in guild.text_channels:
            if ch.name.lower() in ['general', 'main', 'chat', 'bot-commands']:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        
        # If no common channel found, use the first channel the bot can send messages to
        if not channel:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        
        # Send the startup message
        if channel:
            try:
                await channel.send("🤖 **Bot is now online and ready!**\n*Use `!addlist @RoleName` or `/addlist` to create member lists.*")
            except discord.Forbidden:
                pass

async def post_or_update_list(channel, team_list):
    guild = channel.guild
    team_role = guild.get_role(team_list.team_role_id)
    if not team_role:
        await channel.send("⚠️ Team role not found!")
        return

    # Get members with the team role
    members = [m for m in team_role.members if not m.bot]

    # Filter out members with hidden roles
    filtered_members = [
        m for m in members
        if not any(r.id in team_list.hidden_roles for r in m.roles)
    ]

    # Sort by highest role position
    filtered_members.sort(
        key=lambda m: max(r.position for r in m.roles) if m.roles else 0,
        reverse=True
    )

    if not filtered_members:
        content = f"**{team_role.name} Members (sorted by rank):**\n_No members found._"
    else:
        content = f"**{team_role.name} Members (sorted by rank):**\n"
        for m in filtered_members:
            top_role = max(m.roles, key=lambda r: r.position) if m.roles else None
            role_name = top_role.name if top_role else "No Role"
            content += f"{m.display_name} ({role_name})\n"

    # Update or send new message
    try:
        if team_list.message_id:
            msg = await channel.fetch_message(team_list.message_id)
            await msg.edit(content=content)
        else:
            msg = await channel.send(content)
            team_list.message_id = msg.id
    except discord.NotFound:
        msg = await channel.send(content)
        team_list.message_id = msg.id

# Prefix Commands (!)
@bot.command()
async def addlist(ctx, team_role: discord.Role):
    channel_lists = lists.setdefault(ctx.channel.id, {})
    if team_role.id in channel_lists:
        await ctx.send(f"List for {team_role.name} already exists in this channel.")
        return

    team_list = TeamList(team_role.id)
    channel_lists[team_role.id] = team_list
    await ctx.send(f"List for **{team_role.name}** added!")
    await post_or_update_list(ctx.channel, team_list)

@bot.command()
async def removelist(ctx, team_role: discord.Role):
    channel_lists = lists.get(ctx.channel.id, {})
    team_list = channel_lists.pop(team_role.id, None)
    if team_list:
        if team_list.message_id:
            try:
                msg = await ctx.channel.fetch_message(team_list.message_id)
                await msg.delete()
            except discord.NotFound:
                pass
        await ctx.send(f"List for **{team_role.name}** removed.")
    else:
        await ctx.send("List not found in this channel.")

@bot.command()
async def hiderole(ctx, team_role: discord.Role, role_to_hide: discord.Role):
    channel_lists = lists.get(ctx.channel.id, {})
    team_list = channel_lists.get(team_role.id)
    if not team_list:
        await ctx.send("List for that team role not found in this channel.")
        return

    team_list.hidden_roles.add(role_to_hide.id)
    await ctx.send(f"Role **{role_to_hide.name}** hidden in list for **{team_role.name}**.")
    await post_or_update_list(ctx.channel, team_list)

@bot.command()
async def unhiderole(ctx, team_role: discord.Role, role_to_unhide: discord.Role):
    channel_lists = lists.get(ctx.channel.id, {})
    team_list = channel_lists.get(team_role.id)
    if not team_list:
        await ctx.send("List for that team role not found in this channel.")
        return

    team_list.hidden_roles.discard(role_to_unhide.id)
    await ctx.send(f"Role **{role_to_unhide.name}** unhidden in list for **{team_role.name}**.")
    await post_or_update_list(ctx.channel, team_list)

# Slash Commands (/)
@bot.tree.command(name="addlist", description="Add a member list for a role")
async def slash_addlist(interaction: discord.Interaction, team_role: discord.Role):
    channel_lists = lists.setdefault(interaction.channel.id, {})
    if team_role.id in channel_lists:
        await interaction.response.send_message(f"List for {team_role.name} already exists in this channel.")
        return

    team_list = TeamList(team_role.id)
    channel_lists[team_role.id] = team_list
    await interaction.response.send_message(f"List for **{team_role.name}** added!")
    await post_or_update_list(interaction.channel, team_list)

@bot.tree.command(name="removelist", description="Remove a member list for a role")
async def slash_removelist(interaction: discord.Interaction, team_role: discord.Role):
    channel_lists = lists.get(interaction.channel.id, {})
    team_list = channel_lists.pop(team_role.id, None)
    if team_list:
        if team_list.message_id:
            try:
                msg = await interaction.channel.fetch_message(team_list.message_id)
                await msg.delete()
            except discord.NotFound:
                pass
        await interaction.response.send_message(f"List for **{team_role.name}** removed.")
    else:
        await interaction.response.send_message("List not found in this channel.")

@bot.tree.command(name="hiderole", description="Hide members with a specific role from team lists")
async def slash_hiderole(interaction: discord.Interaction, team_role: discord.Role, role_to_hide: discord.Role):
    channel_lists = lists.get(interaction.channel.id, {})
    team_list = channel_lists.get(team_role.id)
    if not team_list:
        await interaction.response.send_message("List for that team role not found in this channel.")
        return

    team_list.hidden_roles.add(role_to_hide.id)
    await interaction.response.send_message(f"Role **{role_to_hide.name}** hidden in list for **{team_role.name}**.")
    await post_or_update_list(interaction.channel, team_list)

@bot.tree.command(name="unhiderole", description="Unhide members with a specific role from team lists")
async def slash_unhiderole(interaction: discord.Interaction, team_role: discord.Role, role_to_unhide: discord.Role):
    channel_lists = lists.get(interaction.channel.id, {})
    team_list = channel_lists.get(team_role.id)
    if not team_list:
        await interaction.response.send_message("List for that team role not found in this channel.")
        return

    team_list.hidden_roles.discard(role_to_unhide.id)
    await interaction.response.send_message(f"Role **{role_to_unhide.name}** unhidden in list for **{team_role.name}**.")
    await post_or_update_list(interaction.channel, team_list)

@bot.event
async def on_member_update(before, after):
    # If roles changed, update relevant lists
    if before.roles != after.roles:
        for channel_id, channel_lists in lists.items():
            channel = after.guild.get_channel(channel_id)
            if not channel:
                continue
            for team_list in channel_lists.values():
                team_role = after.guild.get_role(team_list.team_role_id)
                if team_role and (team_role in before.roles or team_role in after.roles):
                    await post_or_update_list(channel, team_list)

# Run the bot with token from environment
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))