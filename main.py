import discord
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button, Select
import os
import json
import random
import time

# =====================
# CONFIG
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")
SPAWN_INTERVAL = 60  # seconds
DB_FILE = "db.json"
SERVERS_FILE = "servers.json"
ORES_DIR = "ores"

TUTORIAL_MESSAGE = (
    "🍌 **Welcome to Gargantuan Guesser!** 🍌\n\n"
    "🪨 Guess the ore by clicking the correct button.\n"
    "🏆 First correct guess wins **1 Banana**.\n"
    "🔥 Correct guesses build a **streak**.\n"
    "💥 Wrong guesses reset your streak.\n\n"
    "📊 `/gargantuan balance`\n"
    "🥇 `/gargantuan leaderboard`\n"
    "👤 `/gargantuan profile`\n"
)

# =====================
# DATABASES
# =====================
# User DB
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        bananas_db = json.load(f)
else:
    bananas_db = {}

def get_user(uid):
    if uid not in bananas_db:
        bananas_db[uid] = {"bananas":0,"streak":0,"best_streak":0,"cooldown":0}
    else:
        bananas_db[uid].setdefault("best_streak",0)
        bananas_db[uid].setdefault("cooldown",0)
    return bananas_db[uid]

def save_db():
    with open(DB_FILE,"w") as f:
        json.dump(bananas_db,f,indent=4)

# Server DB (spawn channel per server)
if os.path.exists(SERVERS_FILE):
    with open(SERVERS_FILE,"r") as f:
        servers_db = json.load(f)
else:
    servers_db = {}

def save_servers():
    with open(SERVERS_FILE,"w") as f:
        json.dump(servers_db,f,indent=4)

# =====================
# HELPER FUNCTIONS
# =====================
def add_requester_footer(embed: discord.Embed, user: discord.User):
    embed.set_footer(
        text=f"Requested by {user}",
        icon_url=user.display_avatar.url
    )

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
if not ALL_ORES:
    raise RuntimeError("❌ No ore images found")

# =====================
# BOT INIT
# =====================
intents = discord.Intents.default()
intents.message_content = True

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

    async def callback(self,interaction: discord.Interaction):
        uid = str(interaction.user.id)
        user = get_user(uid)

        if self.view_ref.answered:
            await interaction.response.send_message("❌ This ore was already guessed!",ephemeral=True)
            return

        now = time.time()
        if now < user["cooldown"]:
            await interaction.response.send_message("⏳ Wait **3 seconds** before guessing again.",ephemeral=True)
            return

        if self.label == self.view_ref.correct_ore:
            self.view_ref.answered = True
            user["bananas"] += 1
            user["streak"] += 1
            user["best_streak"] = max(user["best_streak"],user["streak"])
            save_db()

            for b in self.view_ref.children:
                b.disabled = True

            await interaction.response.edit_message(
                content=(
                    f"🍌 {interaction.user.mention} guessed it first!\n"
                    f"🔥 **Streak:** {user['streak']}\n"
                    f"The ore was **{self.view_ref.correct_ore}**."
                ),
                view=self.view_ref
            )
        else:
            user["streak"] = 0
            user["cooldown"] = now + 3
            save_db()
            await interaction.response.send_message("❌ Incorrect guess! Streak reset.\n⏳ 3s cooldown.",ephemeral=True)

# =====================
# SPAWN SYSTEM
# =====================
CURRENT_VIEWS = {}  # server_id -> OreView
CURRENT_CORRECT = {}  # server_id -> ore name

async def spawn_ore(guild: discord.Guild, spawned_by: discord.User | None = None):
    if str(guild.id) not in servers_db:
        return
    channel_id = servers_db[str(guild.id)]["spawn_channel"]
    channel = guild.get_channel(channel_id)
    if not channel:
        return

    # handle previous view
    if guild.id in CURRENT_VIEWS and not CURRENT_VIEWS[guild.id].answered:
        for b in CURRENT_VIEWS[guild.id].children:
            b.disabled = True
        if CURRENT_VIEWS[guild.id].message:
            await CURRENT_VIEWS[guild.id].message.edit(view=CURRENT_VIEWS[guild.id])
        await channel.send(f"❌ Nobody got it right! The ore was **{CURRENT_CORRECT[guild.id]}**.")

    correct = random.choice(ALL_ORES)
    CURRENT_CORRECT[guild.id] = correct

    decoys = random.sample([o for o in ALL_ORES if o != correct],2)
    options = [correct]+decoys
    random.shuffle(options)

    view = OreView(correct)
    CURRENT_VIEWS[guild.id] = view
    for opt in options:
        view.add_item(OreButton(opt,view))

    file = discord.File(os.path.join(ORES_DIR,ORE_FILE_MAP[correct]))

    content = "🪨 **Guess the ore!**"
    if spawned_by:
        content += f"\n\nSpawned by {spawned_by}"
    msg = await channel.send(content,file=file,view=view)
    view.message = msg

@tasks.loop(seconds=SPAWN_INTERVAL)
async def spawn_loop():
    for guild_id in servers_db.keys():
        guild = bot.get_guild(int(guild_id))
        if guild:
            await spawn_ore(guild)

# =====================
# SLASH COMMANDS
# =====================
gg = app_commands.Group(name="gargantuan", description="Gargantuan Guesser commands")

@gg.command(name="setup")
async def setup(interaction: discord.Interaction):
    """Select spawn channel for this server"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need admin permissions to setup.",ephemeral=True)
        return

    text_channels = [c for c in interaction.guild.text_channels]
    if not text_channels:
        await interaction.response.send_message("❌ No text channels found in this server.",ephemeral=True)
        return

    # Create a select menu
    options = [discord.SelectOption(label=c.name,value=str(c.id)) for c in text_channels]

    class ChannelSelectView(View):
        def __init__(self):
            super().__init__(timeout=60)
            self.selected_channel = None
            select = discord.ui.Select(placeholder="Select spawn channel",options=options)
            select.callback = self.select_callback
            self.add_item(select)

        async def select_callback(self,select_interaction: discord.Interaction):
            self.selected_channel = int(select.values[0])
            servers_db[str(interaction.guild.id)] = {"spawn_channel": self.selected_channel}
            save_servers()
            await select_interaction.response.edit_message(content=f"✅ Spawn channel set to <#{self.selected_channel}>",view=None)

    await interaction.response.send_message("Select a channel for Gargantuan spawns:",view=ChannelSelectView(),ephemeral=True)

@gg.command(name="spawn")
async def spawn(interaction: discord.Interaction):
    """Manually spawn an ore in this server"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need admin permissions to spawn.",ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    await spawn_ore(interaction.guild, spawned_by=interaction.user)
    await interaction.followup.send("✅ Ore spawned!",ephemeral=True)

@gg.command(name="balance")
async def balance(interaction: discord.Interaction):
    user = get_user(str(interaction.user.id))
    embed = discord.Embed(title="🍌 Your Balance",color=discord.Color.yellow())
    embed.add_field(name="🍌 Bananas",value=user["bananas"],inline=True)
    embed.add_field(name="🔥 Current Streak",value=user["streak"],inline=True)
    embed.add_field(name="🏆 Best Streak",value=user["best_streak"],inline=True)
    add_requester_footer(embed,interaction.user)
    await interaction.response.send_message(embed=embed)

@gg.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    if not bananas_db:
        await interaction.response.send_message("No data yet!")
        return
    sorted_users = sorted(bananas_db.items(),key=lambda x:(x[1]["bananas"],x[1]["best_streak"]),reverse=True)[:10]

    embed = discord.Embed(title="🏆 LEADERBOARD 🏆",color=discord.Color.gold())
    players = ""
    bananas = ""
    streaks = ""
    for i,(uid,data) in enumerate(sorted_users,1):
        try:
            user_obj = await bot.fetch_user(int(uid))
            name = user_obj.name
        except:
            name = "Unknown"
        players += f"**{i}.** {name}\n"
        bananas += f"{data['bananas']}\n"
        streaks += f"{data['best_streak']}\n"

    embed.add_field(name="Player",value=players,inline=True)
    embed.add_field(name="🍌 Bananas",value=bananas,inline=True)
    embed.add_field(name="🔥 Best Streak",value=streaks,inline=True)
    add_requester_footer(embed,interaction.user)
    await interaction.response.send_message(embed=embed)

@gg.command(name="profile")
@app_commands.describe(user="View another player's profile")
async def profile(interaction: discord.Interaction,user: discord.User | None=None):
    target = user or interaction.user
    data = get_user(str(target.id))
    sorted_users = sorted(bananas_db.items(),key=lambda x:(x[1]["bananas"],x[1]["best_streak"]),reverse=True)
    rank = next((i+1 for i,(uid,_) in enumerate(sorted_users) if uid==str(target.id)),"N/A")

    embed = discord.Embed(title=f"🐒 {target.name}'s Profile",color=discord.Color.green())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🍌 Bananas",value=data["bananas"],inline=True)
    embed.add_field(name="🔥 Current Streak",value=data["streak"],inline=True)
    embed.add_field(name="🏆 Best Streak",value=data["best_streak"],inline=True)
    embed.add_field(name="🥇 Global Rank",value=f"#{rank}",inline=False)
    add_requester_footer(embed,interaction.user)
    await interaction.response.send_message(embed=embed)

tree.add_command(gg)

# =====================
# EVENTS
# =====================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if any(role.id==servers_db.get(str(message.guild.id),{}).get("gargantuan_role",-1) for role in message.role_mentions) \
       or bot.user in message.mentions:
        await message.channel.send(TUTORIAL_MESSAGE)

@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.dnd,activity=discord.Game(name="discord.gg/bananite"))
    print(f"Logged in as {bot.user}")
    await tree.sync()
    spawn_loop.start()

# =====================
# RUN
# =====================
bot.run(TOKEN)
