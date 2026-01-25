import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
import os
import json
import random
import time
import asyncio
import subprocess

# =====================
# CONFIG
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")
DB_FILE = "db.json"
SERVERS_FILE = "servers.json"
ORES_DIR = "ores"
SPAWN_INTERVAL = 60  # seconds

GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("REPLIT_GITHUB_TOKEN")

TUTORIAL_MESSAGE = (
    "🍌 **Welcome to Gargantuan Guesser!** 🍌\n\n"
    "🪨 Guess the ore by clicking the correct button.\n"
    "🏆 First correct guess wins **1 Banana**.\n"
    "🔥 Correct guesses build a **streak**.\n"
    "💥 Wrong guesses reset your streak.\n\n"
    "**🎉 Join our official Discord server:** [Click Here!](https://discord.gg/bananite)\n\n"
    "Commands to try:\n"
    "🥇 `/gargantuan leaderboard`\n"
    "👤 `/gargantuan profile`\n"
    "🖼 `/gargantuan index`"
)

# =====================
# DATABASES
# =====================
def load_json(file_path):
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write("{}")
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(file_path, "w") as f:
            f.write("{}")
        return {}

bananas_db = load_json(DB_FILE)
servers_db = load_json(SERVERS_FILE)

def get_user(uid):
    if uid not in bananas_db:
        bananas_db[uid] = {"bananas":0,"streak":0,"best_streak":0,"cooldown":0,"found":[]}
    else:
        bananas_db[uid].setdefault("best_streak",0)
        bananas_db[uid].setdefault("cooldown",0)
        bananas_db[uid].setdefault("found",[])
    return bananas_db[uid]

def save_db():
    with open(DB_FILE,"w") as f:
        json.dump(bananas_db,f,indent=4)

def save_servers():
    with open(SERVERS_FILE,"w") as f:
        json.dump(servers_db,f,indent=4)

# =====================
# PUSH TO GITHUB (Safe)
# =====================
def push_to_github():
    if not GITHUB_REPO or not GITHUB_TOKEN:
        print("❌ GitHub repo/token not set")
        return
    auth_repo = GITHUB_REPO.replace("https://", f"https://{GITHUB_TOKEN}@")
    try:
        subprocess.run(["git","add",DB_FILE,SERVERS_FILE], check=True)
    except subprocess.CalledProcessError as e:
        print("❌ Git add failed:", e)
    try:
        subprocess.run(["git","commit","-m","Update bot stats"], check=True)
    except subprocess.CalledProcessError:
        print("⚠️ Git commit failed (probably nothing to commit)")
    try:
        subprocess.run(["git","push",auth_repo,"HEAD:main"], check=True)
        print("✅ Data pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print("❌ Git push failed:", e)

# =====================
# BOT INIT
# =====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# =====================
# LOAD ORES
# =====================
ALL_ORES = []
ORE_FILE_MAP = {}
for file in os.listdir(ORES_DIR):
    if file.lower().endswith((".png",".webp")):
        name = file.rsplit(".",1)[0].replace("_"," ")
        ALL_ORES.append(name)
        ORE_FILE_MAP[name] = file

ALL_ORES = sorted(ALL_ORES)
LAST_10_ORES = []

# =====================
# FOOTER UTILITY
# =====================
def add_requester_footer(embed: discord.Embed, user: discord.User):
    embed.set_footer(text=f"Requested by {user}", icon_url=user.display_avatar.url)

# =====================
# ORE BUTTONS
# =====================
class OreView(View):
    def __init__(self, correct_ore):
        super().__init__(timeout=None)
        self.correct_ore = correct_ore
        self.answered = False
        self.message = None

class OreButton(Button):
    def __init__(self,label,view):
        super().__init__(label=label,style=discord.ButtonStyle.primary)
        self.view_ref = view

    async def callback(self,interaction: discord.Interaction):
        uid = str(interaction.user.id)
        user = get_user(uid)
        now = time.time()

        if self.view_ref.answered:
            await interaction.response.send_message("❌ Already guessed!",ephemeral=True)
            return

        if now < user["cooldown"]:
            await interaction.response.send_message("⏳ Wait 3 seconds before guessing.",ephemeral=True)
            return

        if self.label == self.view_ref.correct_ore:
            self.view_ref.answered = True
            user["bananas"] += 1
            user["streak"] += 1
            user["best_streak"] = max(user["best_streak"],user["streak"])
            if self.label not in user["found"]:
                user["found"].append(self.label)
            save_db()
            push_to_github()
            for b in self.view_ref.children:
                b.disabled = True
            await interaction.response.edit_message(
                content=(f"🍌 {interaction.user.mention} guessed it first!\n"
                         f"🔥 Streak: {user['streak']}\n"
                         f"The ore was **{self.view_ref.correct_ore}**"),
                view=self.view_ref
            )
        else:
            user["streak"] = 0
            user["cooldown"] = now + 3
            save_db()
            push_to_github()
            await interaction.response.send_message("❌ Incorrect guess! 3s cooldown.",ephemeral=True)

# =====================
# SPAWN SYSTEM
# =====================
CURRENT_VIEWS = {}
CURRENT_CORRECT = {}

async def spawn_ore(guild: discord.Guild, spawned_by: discord.User | None=None):
    guild_id = str(guild.id)
    if guild_id not in servers_db:
        return
    channel_id = servers_db[guild_id].get("spawn_channel")
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if not channel:
        return

    if guild.id in CURRENT_VIEWS and not CURRENT_VIEWS[guild.id].answered:
        for b in CURRENT_VIEWS[guild.id].children:
            b.disabled = True
        if CURRENT_VIEWS[guild.id].message:
            await CURRENT_VIEWS[guild.id].message.edit(view=CURRENT_VIEWS[guild.id])
        await channel.send(f"❌ Nobody got it right! Ore was **{CURRENT_CORRECT[guild.id]}**.")

    possible_ores = [o for o in ALL_ORES if o not in LAST_10_ORES]
    if not possible_ores:
        possible_ores = ALL_ORES.copy()
    correct = random.choice(possible_ores)
    LAST_10_ORES.append(correct)
    if len(LAST_10_ORES) > 10:
        LAST_10_ORES.pop(0)
    CURRENT_CORRECT[guild.id] = correct

    decoys = random.sample([o for o in ALL_ORES if o != correct],2)
    options = [correct]+decoys
    random.shuffle(options)

    view = OreView(correct)
    CURRENT_VIEWS[guild.id] = view
    for opt in options:
        view.add_item(OreButton(opt,view))

    file_path = os.path.join(ORES_DIR,ORE_FILE_MAP[correct])
    file = discord.File(file_path)
    embed = discord.Embed(title="🪨 Guess the ore!")
    if spawned_by:
        embed.description = f"Spawned by {spawned_by.mention}"
    embed.set_image(url=f"attachment://{ORE_FILE_MAP[correct]}")
    msg = await channel.send(embed=embed, file=file, view=view)
    view.message = msg

@tasks.loop(seconds=SPAWN_INTERVAL)
async def spawn_loop():
    for guild_id in servers_db.keys():
        guild = bot.get_guild(int(guild_id))
        if guild:
            await spawn_ore(guild)

# =====================
# PRESENCE ROTATION
# =====================
@tasks.loop(seconds=15)
async def presence_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await bot.change_presence(status=discord.Status.dnd, activity=discord.Game(name="@Gargantuan Guesser to start"))
        await asyncio.sleep(15)
        await bot.change_presence(status=discord.Status.dnd, activity=discord.Game(name="discord.gg/bananite"))
        await asyncio.sleep(15)

# =====================
# LEADERBOARD VIEW
# =====================
class LeaderboardView(View):
    def __init__(self, requester: discord.User, guild: discord.Guild):
        super().__init__(timeout=120)
        self.page = 1
        self.requester = requester
        self.guild = guild
        self.next_btn = Button(label="Next →", style=discord.ButtonStyle.primary)
        self.back_btn = Button(label="← Back", style=discord.ButtonStyle.secondary)
        self.next_btn.callback = self.next_page
        self.back_btn.callback = self.prev_page
        self.add_item(self.next_btn)

    async def build_embed(self):
        embed = discord.Embed(color=discord.Color.gold())
        guild_users = self.guild.members
        guild_user_ids = {str(u.id) for u in guild_users}

        if self.page == 1:
            embed.title = "🏆 Leaderboard — 🍌 Most Bananas"
            sorted_users = sorted(
                ((uid, data) for uid,data in bananas_db.items() if uid in guild_user_ids),
                key=lambda x: (x[1]["bananas"], x[1]["best_streak"]),
                reverse=True
            )
            value_key = "bananas"
        elif self.page == 2:
            embed.title = "🏆 Leaderboard — 🔥 Current Streak"
            sorted_users = sorted(
                ((uid, data) for uid,data in bananas_db.items() if uid in guild_user_ids),
                key=lambda x: x[1]["streak"],
                reverse=True
            )
            value_key = "streak"
        else:
            embed.title = "🏆 Leaderboard — 🏆 Best Streak Ever"
            sorted_users = sorted(
                ((uid, data) for uid,data in bananas_db.items() if uid in guild_user_ids),
                key=lambda x: x[1]["best_streak"],
                reverse=True
            )
            value_key = "best_streak"

        players = ""
        values = ""
        top10_uids = []

        for i, (uid, data) in enumerate(sorted_users[:10], start=1):
            top10_uids.append(uid)
            try:
                user = await bot.fetch_user(int(uid))
                name = user.mention
            except:
                name = "Unknown"
            medal = {1:"🥇",2:"🥈",3:"🥉"}.get(i,f"{i}.")
            players += f"{medal} {name}\n"
            values += f"{data[value_key]}\n"

        embed.add_field(name="Player", value=players or "—", inline=True)
        embed.add_field(name="Value", value=values or "—", inline=True)

        try:
            requester_data = bananas_db.get(str(self.requester.id))
            if requester_data and str(self.requester.id) not in top10_uids:
                sorted_for_rank = sorted(
                    ((uid,data) for uid,data in bananas_db.items() if uid in guild_user_ids),
                    key=lambda x: x[1][value_key],
                    reverse=True
                )
                rank = next((i+1 for i,(uid,_) in enumerate(sorted_for_rank) if uid==str(self.requester.id)),"N/A")
                embed.add_field(name="-------------", value=f"Your rank: #{rank}\nValue: {requester_data[value_key]}", inline=False)
        except:
            pass

        embed.set_footer(text=f"Requested by {self.requester} | Page {self.page}/3", icon_url=self.requester.display_avatar.url)

        self.clear_items()
        if self.page > 1:
            self.add_item(self.back_btn)
        if self.page < 3:
            self.add_item(self.next_btn)

        return embed

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

# =====================
# INDEX GALLERY VIEW (PokéDex style)
# =====================
class GalleryView(View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = str(user_id)
        self.page = 0
        self.ores_per_page = 21

        self.back_btn = Button(label="← Back", style=discord.ButtonStyle.secondary)
        self.next_btn = Button(label="Next →", style=discord.ButtonStyle.primary)
        self.refresh_btn = Button(label="🔄 Refresh", style=discord.ButtonStyle.success)

        self.back_btn.callback = self.prev_page
        self.next_btn.callback = self.next_page
        self.refresh_btn.callback = self.refresh_page

        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.page > 0:
            self.add_item(self.back_btn)
        if (self.page + 1) * self.ores_per_page < len(ALL_ORES):
            self.add_item(self.next_btn)
        self.add_item(self.refresh_btn)

    def filtered_ores(self):
        return ALL_ORES.copy()

    async def build_embed(self):
        user_data = get_user(self.user_id)
        ores = self.filtered_ores()
        start = self.page * self.ores_per_page
        end = start + self.ores_per_page
        ores_page = ores[start:end]

        discovered_count = sum(1 for o in ores if o in user_data["found"])
        embed = discord.Embed(title="🪨 Your Ore Collection", color=discord.Color.blurple())
        description = f"**You've discovered {discovered_count}/{len(ores)} ores!**\n\n"

        guild = None
        for g in bot.guilds:
            if any(int(self.user_id) == m.id for m in g.members):
                guild = g
                break

        rows = [ores_page[i:i+3] for i in range(0, len(ores_page), 3)]
        for row in rows:
            line_emoji = ""
            line_status = ""

            col_widths = []
            for ore in row:
                emoji_obj = None
                if guild:
                    emoji_name = ore.replace(" ","_")
                    emoji_obj = discord.utils.get(guild.emojis, name=emoji_name)
                emoji_str = str(emoji_obj) if emoji_obj else f":{ore.replace(' ','_')}:"
                col_widths.append(len(emoji_str + " " + ore))

            for idx, ore in enumerate(row):
                discovered = ore in user_data["found"]
                emoji_obj = None
                if guild:
                    emoji_name = ore.replace(" ","_")
                    emoji_obj = discord.utils.get(guild.emojis, name=emoji_name)
                emoji_str = str(emoji_obj) if emoji_obj else f":{ore.replace(' ','_')}:"
                cell = f"{emoji_str} {ore}"
                pad = col_widths[idx] - len(cell)
                line_emoji += cell + " " * (pad + 4)
                tick = "✅" if discovered else "❌"
                left_pad = pad // 2 + 2
                right_pad = pad - pad//2 + 2
                line_status += " " * left_pad + tick + " " * right_pad

            description += line_emoji.rstrip() + "\n" + line_status.rstrip() + "\n\n"

        embed.description = description.strip()
        add_requester_footer(embed, await bot.fetch_user(int(self.user_id)))
        return embed

    async def next_page(self, interaction: discord.Interaction):
        if (self.page + 1) * self.ores_per_page < len(ALL_ORES):
            self.page += 1
            self.update_buttons()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    async def refresh_page(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

# =====================
# SLASH COMMANDS
# =====================
gg = app_commands.Group(name="gargantuan", description="Gargantuan Guesser commands")

@gg.command(name="setup", description="Admins only — select the channel where ores will spawn")
@app_commands.describe(channel="Admins only: choose which channel ores will appear in")
async def setup(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admins only.", ephemeral=True)
        return
    servers_db.setdefault(str(interaction.guild.id), {})["spawn_channel"] = channel.id
    save_servers()
    push_to_github()
    await interaction.response.send_message(f"✅ Spawn channel set to {channel.mention}", ephemeral=True)

@gg.command(name="spawn", description="Admins only — manually spawn an ore")
async def spawn(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admins only", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await spawn_ore(interaction.guild, spawned_by=interaction.user)
    await interaction.followup.send("✅ Ore spawned!", ephemeral=True)

@gg.command(name="leaderboard", description="View top players in your server")
async def leaderboard(interaction: discord.Interaction):
    view = LeaderboardView(interaction.user, interaction.guild)
    embed = await view.build_embed()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@gg.command(name="profile", description="View your own or another player's profile")
@app_commands.describe(user="Optional: select another player")
async def profile(interaction: discord.Interaction, user: discord.User | None=None):
    target = user or interaction.user
    data = get_user(str(target.id))
    sorted_users = sorted(
        ((uid,d) for uid,d in bananas_db.items() if uid in {str(m.id) for m in interaction.guild.members}),
        key=lambda x:(x[1]["bananas"],x[1]["best_streak"]),
        reverse=True
    )
    rank = next((i+1 for i,(uid,_) in enumerate(sorted_users) if uid==str(target.id)),"N/A")
    embed = discord.Embed(title=f"🐒 {target.name}'s Profile", color=discord.Color.green())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🍌 Bananas", value=data["bananas"], inline=True)
    embed.add_field(name="🔥 Current Streak", value=data["streak"], inline=True)
    embed.add_field(name="🏆 Best Streak", value=data["best_streak"], inline=True)
    embed.add_field(name="🥇 Global Rank", value=f"#{rank}", inline=False)
    add_requester_footer(embed, interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@gg.command(name="save", description="Admins only — save all players' stats to disk and GitHub")
async def save(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admins only", ephemeral=True)
        return
    save_db()
    save_servers()
    push_to_github()
    await interaction.response.send_message("✅ All data saved to disk and GitHub!", ephemeral=True)

@gg.command(name="index", description="View your ore collection")
async def index(interaction: discord.Interaction):
    view = GalleryView(interaction.user.id)
    embed = await view.build_embed()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

tree.add_command(gg)

# =====================
# EVENTS
# =====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync()
    spawn_loop.start()
    presence_loop.start()

@bot.event
async def on_message(message):
    if bot.user in message.mentions and not message.author.bot:
        try:
            await message.author.send(TUTORIAL_MESSAGE)
            await message.channel.send(f"{message.author.mention}, check your DMs!")
        except:
            pass
    await bot.process_commands(message)

bot.run(TOKEN)
