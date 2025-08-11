import os
import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime
import json

# ----------- Data Persistence -----------

DATA_FILE = "bot_data.json"

def save_data():
    global lists, rank_roles, custom_parameters, guild_settings
    data_to_save = {
        "lists": {},
        "rank_roles": rank_roles,
        "custom_parameters": custom_parameters,
        "guild_settings": guild_settings
    }
    for ch_id, channel_lists in lists.items():
        data_to_save["lists"][str(ch_id)] = {}
        for role_id, tl in channel_lists.items():
            data_to_save["lists"][str(ch_id)][str(role_id)] = {
                "team_role_id": tl.team_role_id,
                "hidden_roles": list(tl.hidden_roles),
                "message_id": tl.message_id,
                "last_updated": tl.last_updated.isoformat() if tl.last_updated else None
            }
    with open(DATA_FILE, "w") as f:
        json.dump(data_to_save, f, indent=4)

def load_data():
    global lists, rank_roles, custom_parameters, guild_settings
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        rank_roles = data.get("rank_roles", {})
        custom_parameters = data.get("custom_parameters", {})
        guild_settings = data.get("guild_settings", {})

        lists.clear()
        for ch_id_str, channel_lists in data.get("lists", {}).items():
            ch_id = int(ch_id_str)
            lists[ch_id] = {}
            for role_id_str, tl_data in channel_lists.items():
                role_id = int(role_id_str)
                tl = TeamList(tl_data["team_role_id"])
                tl.hidden_roles = set(tl_data.get("hidden_roles", []))
                tl.message_id = tl_data.get("message_id")
                last_updated = tl_data.get("last_updated")
                if last_updated:
                    tl.last_updated = datetime.fromisoformat(last_updated)
                else:
                    tl.last_updated = None
                lists[ch_id][role_id] = tl
    except FileNotFoundError:
        pass  # No saved data yet

# ----------- Bot Data Structures -----------

lists = {}  # {channel_id: {team_role_id: TeamList}}
rank_roles = {}  # {guild_id: {role_id: {'priority': int, 'name': str}}}
custom_parameters = {}  # {guild_id: {param_name: [role_ids]}}
guild_settings = {}  # {guild_id: {'embed_color': int}}

class TeamList:
    def __init__(self, team_role_id):
        self.team_role_id = team_role_id
        self.hidden_roles = set()
        self.message_id = None
        self.last_updated = None

# Load saved data at startup
load_data()
# ----------- Discord Bot Setup -----------

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True
intents.presences = False

bot = commands.Bot(command_prefix='!', intents=intents)

# ----------- Utility Functions -----------

def get_guild_color(guild_id):
    if guild_id in guild_settings and 'embed_color' in guild_settings[guild_id]:
        return guild_settings[guild_id]['embed_color']
    return 0x3498db  # default blue

def get_member_rank_role(member, guild_id):
    if guild_id not in rank_roles:
        return None, 999
    guild_rank_roles = rank_roles[guild_id]
    member_rank_roles = []
    for role in member.roles:
        if role.id in guild_rank_roles:
            priority = guild_rank_roles[role.id]['priority']
            member_rank_roles.append((role, priority))
    if not member_rank_roles:
        return None, 999
    return min(member_rank_roles, key=lambda x: x[1])

def get_member_custom_info(member, guild_id):
    if guild_id not in custom_parameters:
        return ""
    info_parts = []
    for param_name, role_ids in custom_parameters[guild_id].items():
        member_roles = [r.id for r in member.roles]
        matching_roles = [r for r in role_ids if r in member_roles]
        if matching_roles:
            role_names = [member.guild.get_role(r).name for r in matching_roles if member.guild.get_role(r)]
            if role_names:
                info_parts.append(f"{param_name}: {', '.join(role_names)}")
    return " | ".join(info_parts)

async def safe_delete_message(message):
    try:
        await message.delete()
    except:
        pass

async def send_private_response(ctx, embed):
    await ctx.author.send(embed=embed)
    await safe_delete_message(ctx.message)

async def post_or_update_list(channel, team_list):
    guild = channel.guild
    team_role = guild.get_role(team_list.team_role_id)
    if not team_role:
        return
    
    members = [m for m in team_role.members if not m.bot]
    filtered_members = [m for m in members if not any(r.id in team_list.hidden_roles for r in m.roles)]
    filtered_members.sort(key=lambda m: get_member_rank_role(m, guild.id)[1])

    embed = discord.Embed(
        title=f"👥 {team_role.name} Members",
        color=get_guild_color(guild.id),
        timestamp=datetime.utcnow()
    )
    if not filtered_members:
        embed.description = "_No members found._"
    else:
        member_list = []
        for i, member in enumerate(filtered_members, 1):
            rank_role, _ = get_member_rank_role(member, guild.id)
            rank_name = rank_role.name if rank_role else "No Rank"
            custom_info = get_member_custom_info(member, guild.id)
            custom_text = f" | {custom_info}" if custom_info else ""
            member_list.append(f"`{i:2d}.` {member.mention} **({rank_name})**{custom_text}")
        embed.description = "\n".join(member_list)

    embed.set_footer(text=f"Total Members: {len(filtered_members)} | Last Updated")
    embed.timestamp = datetime.utcnow()

    if guild.id in rank_roles and rank_roles[guild.id]:
        rank_info = []
        for role_id, info in sorted(rank_roles[guild.id].items(), key=lambda x: x[1]['priority'])[:10]:
            role = guild.get_role(role_id)
            if role:
                rank_info.append(f"`{info['priority']}` {role.name}")
        if rank_info:
            embed.add_field(name="🏆 Rank Priority", value="\n".join(rank_info), inline=True)
    
    try:
        if team_list.message_id:
            try:
                msg = await channel.fetch_message(team_list.message_id)
                await msg.edit(embed=embed)
            except discord.NotFound:
                msg = await channel.send(embed=embed)
                team_list.message_id = msg.id
        else:
            msg = await channel.send(embed=embed)
            team_list.message_id = msg.id
        
        team_list.last_updated = datetime.utcnow()
        save_data()
    except discord.Forbidden:
        pass

async def update_server_lists(guild):
    for channel_id, channel_lists in lists.items():
        channel = guild.get_channel(channel_id)
        if channel:
            for team_list in channel_lists.values():
                await post_or_update_list(channel, team_list)
                await asyncio.sleep(0.5) 
# ----------- Periodic update task -----------

@tasks.loop(minutes=5)
async def update_lists_task():
    for channel_id, channel_lists in lists.items():
        try:
            channel = bot.get_channel(channel_id)
            if channel:
                for team_list in channel_lists.values():
                    if (not team_list.last_updated or
                        (datetime.utcnow() - team_list.last_updated).total_seconds() > 240):
                        await post_or_update_list(channel, team_list)
                        await asyncio.sleep(1)
        except Exception as e:
            print(f"Error updating lists: {e}")

# ----------- Bot Events -----------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}!")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    if not update_lists_task.is_running():
        update_lists_task.start()
    for guild in bot.guilds:
        await send_startup_message(guild)

async def send_startup_message(guild):
    channel = None
    if guild.me:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages and ch.name.lower() in ['general', 'main', 'chat', 'bot-commands', 'bots']:
                channel = ch
                break
        if not channel:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
    if channel:
        try:
            embed = discord.Embed(
                title="🤖 Bot Online!",
                description=(
                    "**Team Member List Bot is ready!**\n\n"
                    "**Quick Start:**\n"
                    "• `!addrank @Role 1` - Add a rank role with priority\n"
                    "• `!addlist @TeamRole` - Create a member list\n"
                    "• `!help` - View all commands"
                ),
                color=get_guild_color(guild.id),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Use !botinfo for detailed information")
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass
            # --- RANK MANAGEMENT COMMANDS ---

@bot.command(name='addrank')
async def addrank(ctx, role: discord.Role, priority: int = None):
    if priority is None:
        embed = discord.Embed(
            title="❌ Missing Priority",
            description="Please specify a priority number!\nExample: `!addrank @Captain 2`",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)
        return
    if not 1 <= priority <= 100:
        embed = discord.Embed(
            title="❌ Invalid Priority",
            description="Priority must be between 1 and 100!",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)
        return
    guild_id = ctx.guild.id
    if guild_id not in rank_roles:
        rank_roles[guild_id] = {}
    rank_roles[guild_id][role.id] = {'priority': priority, 'name': role.name}
    embed = discord.Embed(
        title="✅ Rank Role Added",
        description=f"**{role.name}** is now a rank role with priority `{priority}`\n*Lower numbers = higher priority*",
        color=0x2ecc71
    )
    await send_private_response(ctx, embed)
    save_data()
    await update_server_lists(ctx.guild)

@bot.command(name='removerank')
async def removerank(ctx, role: discord.Role):
    guild_id = ctx.guild.id
    if guild_id in rank_roles and role.id in rank_roles[guild_id]:
        del rank_roles[guild_id][role.id]
        embed = discord.Embed(
            title="✅ Rank Role Removed",
            description=f"**{role.name}** is no longer a rank role!",
            color=0x2ecc71
        )
        await send_private_response(ctx, embed)
        save_data()
        await update_server_lists(ctx.guild)
    else:
        embed = discord.Embed(
            title="❌ Not Found",
            description=f"**{role.name}** is not currently a rank role!",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)

@bot.command(name='listranks')
async def listranks(ctx):
    guild_id = ctx.guild.id
    if guild_id not in rank_roles or not rank_roles[guild_id]:
        embed = discord.Embed(
            title="❌ No Rank Roles",
            description="No rank roles set for this server!\n*Use `!addrank @RoleName 1` to add rank roles.*",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)
        return
    embed = discord.Embed(
        title="🏆 Server Rank Roles",
        color=get_guild_color(guild_id)
    )
    sorted_ranks = sorted(rank_roles[guild_id].items(), key=lambda x: x[1]['priority'])
    rank_list = []
    for role_id, info in sorted_ranks:
        role = ctx.guild.get_role(role_id)
        if role:
            rank_list.append(f"`{info['priority']:2d}.` {role.mention} - **{role.name}**")
    embed.description = "\n".join(rank_list) if rank_list else "No valid rank roles found!"
    embed.set_footer(text="Lower numbers = higher priority")
    await send_private_response(ctx, embed)

# --- CUSTOM PARAMETERS COMMANDS ---

@bot.command(name='addparam')
async def addparam(ctx, param_name: str, *roles: discord.Role):
    if not roles:
        embed = discord.Embed(
            title="❌ Missing Roles",
            description="Please specify at least one role!\nExample: `!addparam Specialty @Medic @Engineer`",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)
        return
    guild_id = ctx.guild.id
    if guild_id not in custom_parameters:
        custom_parameters[guild_id] = {}
    custom_parameters[guild_id][param_name] = [role.id for role in roles]
    role_mentions = ", ".join([role.mention for role in roles])
    embed = discord.Embed(
        title="✅ Custom Parameter Added",
        description=f"**{param_name}:** {role_mentions}",
        color=0x2ecc71
    )
    await send_private_response(ctx, embed)
    save_data()
    await update_server_lists(ctx.guild)

@bot.command(name='removeparam')
async def removeparam(ctx, param_name: str):
    guild_id = ctx.guild.id
    if guild_id in custom_parameters and param_name in custom_parameters[guild_id]:
        del custom_parameters[guild_id][param_name]
        embed = discord.Embed(
            title="✅ Parameter Removed",
            description=f"Custom parameter **{param_name}** has been removed!",
            color=0x2ecc71
        )
        await send_private_response(ctx, embed)
        save_data()
        await update_server_lists(ctx.guild)
    else:
        embed = discord.Embed(
            title="❌ Not Found",
            description=f"Custom parameter **{param_name}** not found!",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)

# --- LIST MANAGEMENT COMMANDS ---

@bot.command(name='addlist')
async def addlist(ctx, team_role: discord.Role):
    channel_lists = lists.setdefault(ctx.channel.id, {})
    if team_role.id in channel_lists:
        embed = discord.Embed(
            title="❌ List Exists",
            description=f"List for **{team_role.name}** already exists in this channel.",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)
        return
    team_list = TeamList(team_role.id)
    channel_lists[team_role.id] = team_list
    embed = discord.Embed(
        title="✅ List Created",
        description=f"Member list for **{team_role.name}** has been created!",
        color=0x2ecc71
    )
    await send_private_response(ctx, embed)
    save_data()
    await post_or_update_list(ctx.channel, team_list)

@bot.command(name='removelist')
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
        embed = discord.Embed(
            title="✅ List Removed",
            description=f"List for **{team_role.name}** has been removed.",
            color=0x2ecc71
        )
        save_data()
    else:
        embed = discord.Embed(
            title="❌ Not Found",
            description="List not found in this channel.",
            color=0xe74c3c
        )
    await send_private_response(ctx, embed)

@bot.command(name='hiderole')
async def hiderole(ctx, team_role: discord.Role, role_to_hide: discord.Role):
    channel_lists = lists.get(ctx.channel.id, {})
    team_list = channel_lists.get(team_role.id)
    if not team_list:
        embed = discord.Embed(
            title="❌ List Not Found",
            description="List for that team role not found in this channel.",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)
        return
    team_list.hidden_roles.add(role_to_hide.id)
    embed = discord.Embed(
        title="✅ Role Hidden",
        description=f"Members with **{role_to_hide.name}** are now hidden from **{team_role.name}** list.",
        color=0x2ecc71
    )
    await send_private_response(ctx, embed)
    save_data()
    await post_or_update_list(ctx.channel, team_list)

@bot.command(name='unhiderole')
async def unhiderole(ctx, team_role: discord.Role, role_to_unhide: discord.Role):
    channel_lists = lists.get(ctx.channel.id, {})
    team_list = channel_lists.get(team_role.id)
    if not team_list:
        embed = discord.Embed(
            title="❌ List Not Found",
            description="List for that team role not found in this channel.",
            color=0xe74c3c
        )
        await send_private_response(ctx, embed)
        return
    team_list.hidden_roles.discard(role_to_unhide.id)
    embed = discord.Embed(
        title="✅ Role Unhidden",
        description=f"Members with **{role_to_unhide.name}** are now visible in **{team_role.name}** list.",
        color=0x2ecc71
    )
    await send_private_response(ctx, embed)
    save_data()
    await post_or_update_list(ctx.channel, team_list)

# --- SETTINGS & INFO COMMANDS ---

@bot.command(name='setcolor')
async def setcolor(ctx, hex_color: str):
    try:
        if not hex_color.startswith('#'):
            hex_color = '#' + hex_color
            
