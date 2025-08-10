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

# Data structures
lists = {}  # {channel_id: {team_role_id: TeamList}}
rank_roles = {}  # {guild_id: {role_id, role_id, ...}}

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
                await channel.send("🤖 **Bot is now online and ready!**\n*Use `!addlist @RoleName` or `/addlist` to create member lists.*\n*Use `!addrank @RankRole` to set which roles count as ranks.*")
            except discord.Forbidden:
                pass

def get_member_rank_role(member, guild_id):
    """Get the highest rank role for a member based on server settings"""
    if guild_id not in rank_roles:
        return None
    
    guild_rank_roles = rank_roles[guild_id]
    member_rank_roles = [role for role in member.roles if role.id in guild_rank_roles]
    
    if not member_rank_roles:
        return None
    
    # Return the highest position rank role
    return max(member_rank_roles, key=lambda r: r.position)

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

    # Sort by highest rank role position (only considering rank roles)
    def sort_key(member):
        rank_role = get_member_rank_role(member, guild.id)
        return rank_role.position if rank_role else 0
    
    filtered_members.sort(key=sort_key, reverse=True)

    if not filtered_members:
        content = f"**{team_role.name} Members (sorted by rank):**\n_No members found._"
    else:
        content = f"**{team_role.name} Members (sorted by rank):**\n"
        for m in filtered_members:
            rank_role = get_member_rank_role(m, guild.id)
            role_name = rank_role.name if rank_role else "No Rank"
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

# Rank Role Management Commands
@bot.command()
async def addrank(ctx, role: discord.Role):
    """Add a role to the list of rank roles"""
    guild_id = ctx.guild.id
    if guild_id not in rank_roles:
        rank_roles[guild_id] = set()
    
    rank_roles[guild_id].add(role.id)
    await ctx.send(f"✅ **{role.name}** is now considered a rank role!")
    
    # Update all existing lists in this server
    for channel_id, channel_lists in lists.items():
        channel = ctx.guild.get_channel(channel_id)
        if channel:
            for team_list in channel_lists.values():
                await post_or_update_list(channel, team_list)

@bot.command()
async def removerank(ctx, role: discord.Role):
    """Remove a role from the list of rank roles"""
    guild_id = ctx.guild.id
    if guild_id in rank_roles and role.id in rank_roles[guild_id]:
        rank_roles[guild_id].remove(role.id)
        await ctx.send(f"✅ **{role.name}** is no longer considered a rank role!")
        
        # Update all existing lists in this server
        for channel_id, channel_lists in lists.items():
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                for team_list in channel_lists.values():
                    await post_or_update_list(channel, team_list)
    else:
        await ctx.send(f"❌ **{role.name}** is not currently a rank role!")

@bot.command()
async def listranks(ctx):
    """Show all rank roles for this server"""
    guild_id = ctx.guild.id
    if guild_id not in rank_roles or not rank_roles[guild_id]:
        await ctx.send("❌ No rank roles set for this server!\n*Use `!addrank @RoleName` to add rank roles.*")
        return
    
    guild_rank_roles = rank_roles[guild_id]
    role_names = []
    
    for role_id in guild_rank_roles:
        role = ctx.guild.get_role(role_id)
        if role:
            role_names.append(role.name)
    
    if role_names:
        content = "**🏆 Rank Roles for this server:**\n" + "\n".join(f"• {name}" for name in sorted(role_names))
        await ctx.send(content)
    else:
        await ctx.send("❌ No valid rank roles found!")

# Existing Team List Commands
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

# Slash Commands
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

@bot.tree.command(name="addrank", description="Add a role to the list of rank roles")
async def slash_addrank(interaction: discord.Interaction, role: discord.Role):
    guild_id = interaction.guild.id
    if guild_id not in rank_roles:
        rank_roles[guild_id] = set()
    
    rank_roles[guild_id].add(role.id)
    await interaction.response.send_message(f"✅ **{role.name}** is now considered a rank role!")
    
    # Update all existing lists in this server
    for channel_id, channel_lists in lists.items():
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            for team_list in channel_lists.values():
                await post_or_update_list(channel, team_list)

@bot.tree.command(name="removerank", description="Remove a role from the list of rank roles")
async def slash_removerank(interaction: discord.Interaction, role: discord.Role):
    guild_id = interaction.guild.id
    if guild_id in rank_roles and role.id in rank_roles[guild_id]:
        rank_roles[guild_id].remove(role.id)
        await interaction.response.send_message(f"✅ **{role.name}** is no longer considered a rank role!")
        
        # Update all existing lists in this server
        for channel_id, channel_lists in lists.items():
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                for team_list in channel_lists.values():
                    await post_or_update_list(channel, team_list)
    else:
        await interaction.response.send_message(f"❌ **{role.name}** is not currently a rank role!")

@bot.tree.command(name="listranks", description="Show all rank roles for this server")
async def slash_listranks(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in rank_roles or not rank_roles[guild_id]:
        await interaction.response.send_message("❌ No rank roles set for this server!\n*Use `/addrank` to add rank roles.*")
        return
    
    guild_rank_roles = rank_roles[guild_id]
    role_names = []
    
    for role_id in guild_rank_roles:
        role = interaction.guild.get_role(role_id)
        if role:
            role_names.append(role.name)
    
    if role_names:
        content = "**🏆 Rank Roles for this server:**\n" + "\n".join(f"• {name}" for name in sorted(role_names))
        await interaction.response.send_message(content)
    else:
        await interaction.response.send_message("❌ No valid rank roles found!")

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