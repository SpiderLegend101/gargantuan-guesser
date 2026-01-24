import discord
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button
import os
import json
import random
import time
import asyncio
import subprocess
from collections import deque

# =====================
# CONFIG
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")
DB_FILE = "db.json"
SERVERS_FILE = "servers.json"
ORES_DIR = "ores"
SPAWN_INTERVAL = 60  # seconds

# GitHub config
GITHUB_REPO = os.getenv("GITHUB_REPO")  # e.g. https://github.com/username/repo_name.git
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # personal access token

TUTORIAL_MESSAGE = (
    "🍌 **Welcome to Gargantuan Guesser!** 🍌\n\n"
    "🪨 Guess the ore by clicking the correct button.\n"
    "🏆 First correct guess wins **1 Banana**.\n"
    "🔥 Correct guesses build a **streak**.\n"
    "💥 Wrong guesses reset your streak.\n\n"
    "**🎉 Join our official Discord server:** [Click Here!](https://discord.gg/bananite)\n\n"
    "🥇 `/gargantuan leaderboard`\n"
    "👤 `/gargantuan profile`"
)

# =====================
# DATABASES
# =====================
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        bananas_db = json.load(f)
else:
    bananas_db = {}

if os.path.exists(SERVERS_FILE):
    with open(SERVERS_FILE, "r") as f:
        servers_db = json.load(f)
else:
    servers_db = {}

def get_user(uid):
    if uid not in bananas_db:
        bananas_db[uid] = {"bananas":0,"streak":0,"best_streak":0,"cooldown":0}
    else:
        bananas_db[uid].setdefault("best_streak",0)
        bananas_db[uid].setdefault("cooldown",0)
    return bananas_db[uid]

# =====================
# SAVE FUNCTIONS
# =====================
def save_db(auto_push=True):
    with open(DB_FILE, "w") as f:
        json.dump(bananas_db, f, indent=4)
    if auto_push:
        push_to_github()

def save_servers(auto_push=True):
    with open(SERVERS_FILE, "w") as f:
        json.dump(servers_db, f, indent=4)
    if auto_push:
        push_to_github()

# =====================
# GITHUB PUSH
# =====================
def push_to_github():
    if not GITHUB_REPO or not GITHUB_TOKEN:
        print("❌ GitHub repo/token not set")
        return
    auth_repo = GITHUB_REPO.replace("https://", f"https://{GITHUB_TOKEN}@")
    try:
        subprocess.run(["git", "add", DB_FILE, SERVERS_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update bot stats"], check=True)
        subprocess.run(["git", "push", auth_repo, "HEAD:main"], check=True)
        print("✅ Data pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print("❌ Git push failed:", e)

# =====================
# FOOTER
# =====================
def add_requester_footer(embed: discord.Embed, user: discord.User):
    embed.set_footer(text=f"Requested by {user}", icon_url=user.display_avatar.url)

# =====================
# LOAD ORES
# =====================
ALL_ORES = []
ORE_FILE_MAP = {}
for file in os.listdir(ORES_DIR):
    if file.lower().endswith((".png", ".webp")):
        name = file.rsplit(".",1)[0].replace("_"," ")
        ALL_ORES.append(name)
        ORE_FILE_MAP[name] = file
if not ALL_ORES:
    raise RuntimeError("❌ No ore images found")

# =====================
# BOT INIT
# =====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# =====================
# BUTTON VIEW
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

    async def callback(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        user = get_user(uid)

        if self.view_ref.answered:
            await interaction.response.send_message("❌ Already guessed!", ephemeral=True)
            return

        now = time.time()
        if now < user["cooldown"]:
            await interaction.response.send_message("⏳ Wait 3 seconds before guessing.", ephemeral=True)
            return

        if self.label == self.view_ref.correct_ore:
            self.view_ref.answered = True
            user["bananas"] += 1
            user["streak"] += 1
            user["best_streak"] = max(user["best_streak"], user["streak"])
            save_db(auto_push=True)
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
            save_db(auto_push=True)
            await interaction.response.send_message("❌ Incorrect guess! 3s cooldown.", ephemeral=True)

# =====================
# SPAWN SYSTEM
# =====================
CURRENT_VIEWS = {}
CURRENT_CORRECT = {}
LAST_SPAWNS = {}  # {guild_id: deque(maxlen=10)}

async def spawn_ore(guild: discord.Guild, spawned_by: discord.User | None = None):
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

    # Initialize deque for last spawns
    if guild_id not in LAST_SPAWNS:
        LAST_SPAWNS[guild_id] = deque(maxlen=10)

    # Avoid repeating last 10 ores
    available_ores = [o for o in ALL_ORES if o not in LAST_SPAWNS[guild_id]]
    if not available_ores:
        available_ores = ALL_ORES.copy()  # fallback if all ores in queue
    correct = random.choice(available_ores)
    LAST_SPAWNS[guild_id].append(correct)

    CURRENT_CORRECT[guild.id] = correct
    decoys = random.sample([o for o in ALL_ORES if o != correct], 2)
    options = [correct] + decoys
    random.shuffle(options)

    view = OreView(correct)
    CURRENT_VIEWS[guild.id] = view
    for opt in options:
        view.add_item(OreButton(opt, view))

    file_path = os.path.join(ORES_DIR, ORE_FILE_MAP[correct])
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
# PRESENCE
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
# ... Keep the LeaderboardView class as in your previous main.py (unchanged) ...

# =====================
# SLASH COMMANDS
# =====================
gg = app_commands.Group(name="gargantuan", description="Gargantuan Guesser commands")

# Include all previous commands: setup, spawn, leaderboard, profile

@gg.command(
    name="save",
    description="Admins only — save all stats to disk and GitHub"
)
async def save(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admins only", ephemeral=True)
        return
    save_db(auto_push=True)
    save_servers(auto_push=True)
    await interaction.response.send_message("✅ All data saved and pushed to GitHub!", ephemeral=True)

tree.add_command(gg)

# =====================
# EVENTS
# =====================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync()
    spawn_loop.start()
    presence_loop.start()

bot.run(TOKEN)
