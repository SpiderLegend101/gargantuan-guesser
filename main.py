import discord
from discord.ext import commands
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

GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("REPLIT_GITHUB_TOKEN")

# =====================
# GLOBAL STATE
# =====================
CURRENT_VIEWS = {}
CURRENT_CORRECT = {}
INCORRECT_USERS = {}
ACTIVE_SPAWN = set()

# =====================
# TUTORIAL MESSAGE
# =====================
TUTORIAL_MESSAGE = (
    "🍌 **Welcome to Gargantuan Guesser!** 🍌\n\n"
    "🪨 Guess the ore by clicking the correct button.\n"
    "🏆 First correct guess wins **1 Banana**.\n"
    "🔥 Correct guesses build a **streak**.\n"
    "💥 Wrong guesses reset your streak.\n\n"
    "**Commands:**\n"
    "📚 /gargantuan index\n"
    "👤 /gargantuan profile\n"
    "🏆 /gargantuan leaderboard\n"
    "🍌 /gargantuan redeem_spawn\n"
)

# =====================
# DATABASE UTILITIES
# =====================
def load_json(path):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({}, f)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(path, "w") as f:
            json.dump({}, f)
        return {}

bananas_db = load_json(DB_FILE)
servers_db = load_json(SERVERS_FILE)

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(bananas_db, f, indent=4)

def save_servers():
    with open(SERVERS_FILE, "w") as f:
        json.dump(servers_db, f, indent=4)

def get_user(uid: str):
    if uid not in bananas_db:
        bananas_db[uid] = {
            "bananas": 0,
            "streak": 0,
            "best_streak": 0,
            "found": []
        }
    return bananas_db[uid]

# =====================
# OPTIONAL GITHUB PUSH
# =====================
def push_to_github():
    if not GITHUB_REPO or not GITHUB_TOKEN:
        return
    try:
        repo = GITHUB_REPO.replace("https://", f"https://{GITHUB_TOKEN}@")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Auto save {time.strftime('%Y-%m-%d %H:%M:%S')}"],
            check=True
        )
        subprocess.run(["git", "push", repo, "HEAD:main"], check=True)
    except Exception:
        pass

# =====================
# BOT INIT
# =====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# =====================
# RARITY DATA (FULL, ORDERED, BALANCED)
# =====================
RARITY_DATA = {
    "common": {
        "color": 0x95a5a6,
        "chance": 22,
        "cost": 5,
        "ores": [
            "Stone", "Sand Stone", "Copper", "Iron", "Grass",
            "Cardboardite", "Tungsten", "Fichillium", "Mosasaursit"
        ]
    },
    "uncommon": {
        "color": 0x2ecc71,
        "chance": 19,
        "cost": 10,
        "ores": [
            "Tin", "Silver", "Gold", "Bananite",
            "Cobalt", "Titanium", "Lapis Lazuli", "Sulfur"
        ]
    },
    "rare": {
        "color": 0x3498db,
        "chance": 16,
        "cost": 20,
        "ores": [
            "Mushroomite", "Platinum", "Volcanic Rock", "Quartz",
            "Amethyst", "Topaz", "Diamond", "Sapphire",
            "Boneite", "Scheelite", "Pumice", "Graphite",
            "Aetherit", "Dark Boneite", "Mistvein", "Lgarite"
        ]
    },
    "epic": {
        "color": 0xbf75e9,
        "chance": 14,
        "cost": 30,
        "ores": [
            "Aite", "Poopite", "Slimite", "Cuprite", "Obsidian",
            "Emerald", "Ruby", "Rivalite",
            "Blue Crystal", "Orange Crystal", "Green Crystal",
            "Magenta Crystal", "Crimson Crystal",
            "Larimar", "Neurotite", "Frost Fossil",
            "Tide Carve", "Moltenfrost", "Crimsonite",
            "Malachite", "Aquajade", "Cryptex", "Frogite"
        ]
    },
    "legendary": {
        "color": 0xfdb745,
        "chance": 12,
        "cost": 40,
        "ores": [
            "Uranium", "Mythril", "Eye Ore", "Velchire",
            "Sanctis", "Fireite", "Magmaite", "Lightite",
            "Snowite", "Rainbow Crystal", "Moon Stone",
            "Voidstar", "Gulabite", "Coinite",
            "Prismatic Heart"
        ]
    },
    "mythical": {
        "color": 0xff4d4d,
        "chance": 10,
        "cost": 50,
        "ores": [
            "Demonite", "Darkryte", "Iceite", "Etherealite",
            "Duranite", "Voidfractal", "Galestor",
            "Evil Eye", "Yeti Heart", "Arcane Crystal"
        ]
    },
    "divine": {
        "color": 0x5b2b9a,
        "chance": 7,
        "cost": 50,
        "ores": [
            "Suryafal", "Stolen Heart", "Golem Heart",
            "Heart of The Island", "Heavenite",
            "Gargantuan", "Galaxite"
        ]
    }
}

ALL_RARITIES = list(RARITY_DATA.keys())

# =====================
# ORE IMAGE MAP
# =====================
ORE_IMAGE = {}
ALL_ORES = []

if os.path.exists(ORES_DIR):
    for f in os.listdir(ORES_DIR):
        if f.lower().endswith((".png", ".webp")):
            name = f.rsplit(".", 1)[0].replace("_", " ")
            ORE_IMAGE[name] = f

for data in RARITY_DATA.values():
    for ore in data["ores"]:
        ALL_ORES.append(ore)

# =====================
# RANDOM HELPERS
# =====================
def pick_rarity():
    keys = list(RARITY_DATA.keys())
    weights = [RARITY_DATA[k]["chance"] for k in keys]
    return random.choices(keys, weights=weights)[0]

def rarity_error_text():
    return (
        "❌ Invalid rarity.\n"
        f"Available rarities: **{', '.join(r.capitalize() for r in ALL_RARITIES)}**"
    )

def add_footer(embed: discord.Embed, user: discord.User):
    embed.set_footer(
        text=f"Requested by {user}",
        icon_url=user.display_avatar.url
    )

# =====================
# ORE VIEW & BUTTON LOGIC
# =====================
class OreView(View):
    def __init__(self, correct_ore: str):
        super().__init__(timeout=None)
        self.correct = correct_ore
        self.answered = False
        self.message = None

class OreButton(Button):
    def __init__(self, label: str, view: OreView):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        uid = str(interaction.user.id)
        user = get_user(uid)

        INCORRECT_USERS.setdefault(guild_id, set())

        if uid in INCORRECT_USERS[guild_id]:
            await interaction.response.send_message(
                "⏳ You already guessed incorrectly. Wait for the next ore.",
                ephemeral=True
            )
            return

        if self.view_ref.answered:
            await interaction.response.send_message(
                "❌ This ore was already guessed.",
                ephemeral=True
            )
            return

        if self.label == self.view_ref.correct:
            self.view_ref.answered = True
            user["bananas"] += 1
            user["streak"] += 1
            user["best_streak"] = max(user["best_streak"], user["streak"])

            if self.label not in user["found"]:
                user["found"].append(self.label)

            save_db()
            push_to_github()

            for b in self.view_ref.children:
                b.disabled = True

            await interaction.response.edit_message(
                content=(
                    f"🍌 {interaction.user.mention} guessed it first!\n"
                    f"🔥 Streak: **{user['streak']}**\n"
                    f"The ore was **{self.view_ref.correct}**"
                ),
                view=self.view_ref
            )

            ACTIVE_SPAWN.discard(guild_id)

        else:
            user["streak"] = 0
            INCORRECT_USERS[guild_id].add(uid)

            save_db()
            push_to_github()

            await interaction.response.send_message(
                "❌ Incorrect guess.\n**Your streak has been reset.**",
                ephemeral=True
            )
# =====================
# SPAWN CORE
# =====================
async def spawn_ore(
    guild: discord.Guild,
    spawned_by: discord.User | None = None,
    forced_rarity: str | None = None,
    ephemeral: bool = False
):
    if guild.id in ACTIVE_SPAWN:
        return
    ACTIVE_SPAWN.add(guild.id)

    server = servers_db.get(str(guild.id))
    if not server:
        ACTIVE_SPAWN.discard(guild.id)
        return

    channel = guild.get_channel(server.get("spawn_channel"))
    if not channel:
        ACTIVE_SPAWN.discard(guild.id)
        return

    # Close previous unanswered spawn
    if guild.id in CURRENT_VIEWS:
        old_view = CURRENT_VIEWS[guild.id]
        for b in old_view.children:
            b.disabled = True
        if old_view.message:
            await old_view.message.edit(view=old_view)

        await channel.send(
            f"❌ Nobody guessed it.\nThe ore was **{CURRENT_CORRECT[guild.id]}**."
        )

    INCORRECT_USERS[guild.id] = set()

    rarity = forced_rarity or pick_rarity()
    ore = random.choice(RARITY_DATA[rarity]["ores"])
    CURRENT_CORRECT[guild.id] = ore

    # 2 decoys
    decoys = random.sample(
        [o for o in ALL_ORES if o != ore],
        2
    )
    options = [ore] + decoys
    random.shuffle(options)

    view = OreView(ore)
    CURRENT_VIEWS[guild.id] = view

    for opt in options:
        view.add_item(OreButton(opt, view))

    embed = discord.Embed(
        title="🪨 Guess the Ore!",
        description=f"**Rarity:** {rarity.capitalize()}",
        color=RARITY_DATA[rarity]["color"]
    )

    if spawned_by and not ephemeral:
        embed.description += f"\nSpawned by {spawned_by.mention}"

    img = ORE_IMAGE.get(ore)
    file = None
    if img:
        file = discord.File(
            os.path.join(ORES_DIR, img),
            filename=img
        )
        embed.set_image(url=f"attachment://{img}")

    if ephemeral and spawned_by:
        await spawned_by.send(embed=embed, file=file, view=view)
        ACTIVE_SPAWN.discard(guild.id)
        return

    msg = await channel.send(embed=embed, file=file, view=view)
    view.message = msg


# =====================
# HELPER: LIST RARITIES FOR ERROR
# =====================
def rarity_error_text():
    return "❌ Invalid rarity. Available rarities: " + ", ".join([r.capitalize() for r in RARITY_DATA.keys()])


# =====================
# SLASH COMMAND GROUP
# =====================
gargantuan = app_commands.Group(
    name="gargantuan",
    description="Gargantuan Guesser commands"
)


# =====================
# SETUP COMMAND
# =====================
@gargantuan.command(
    name="setup",
    description="Admins only — set the spawn channel"
)
@app_commands.describe(channel="Channel where ores will spawn")
async def setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Admins only.",
            ephemeral=True
        )
        return

    servers_db.setdefault(str(interaction.guild.id), {})
    servers_db[str(interaction.guild.id)]["spawn_channel"] = channel.id
    save_servers()

    await interaction.response.send_message(
        f"✅ Spawn channel set to {channel.mention}",
        ephemeral=True
    )


# =====================
# MANUAL SPAWN COMMAND
# =====================
@gargantuan.command(
    name="spawn",
    description="Admins only — manually spawn an ore"
)
@app_commands.describe(rarity="Optional rarity to force spawn")
async def spawn(
    interaction: discord.Interaction,
    rarity: str | None = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Admins only.",
            ephemeral=True
        )
        return

    chosen = rarity.lower() if rarity else None
    if chosen and chosen not in RARITY_DATA:
        await interaction.response.send_message(
            rarity_error_text(),
            ephemeral=True
        )
        return

    await spawn_ore(
        interaction.guild,
        spawned_by=interaction.user,
        forced_rarity=chosen
    )

    await interaction.response.send_message(
        "✅ Ore spawned.",
        ephemeral=True
    )


# =====================
# REDEEM SPAWN COMMAND
# =====================
@gargantuan.command(
    name="redeem_spawn",
    description="Spend bananas to spawn a specific rarity ore"
)
@app_commands.describe(rarity="Rarity to redeem")
async def redeem_spawn(
    interaction: discord.Interaction,
    rarity: str
):
    uid = str(interaction.user.id)
    user = get_user(uid)
    rarity = rarity.lower()

    if rarity not in RARITY_DATA:
        await interaction.response.send_message(
            rarity_error_text(),
            ephemeral=True
        )
        return

    cost = RARITY_DATA[rarity]["cost"]
    if user["bananas"] < cost:
        await interaction.response.send_message(
            f"❌ You need {cost} bananas.",
            ephemeral=True
        )
        return

    user["bananas"] -= cost
    save_db()
    push_to_github()

    await spawn_ore(
        interaction.guild,
        spawned_by=interaction.user,
        forced_rarity=rarity,
        ephemeral=True
    )

    await interaction.response.send_message(
        f"✅ Spent {cost} bananas. Check your DMs!",
        ephemeral=True
    )


# =====================
# INDEX COMMAND WITH OPTIONAL RARITY
# =====================
@gargantuan.command(
    name="index",
    description="View your ore collection, optionally filtered by rarity"
)
@app_commands.describe(rarity="Optional rarity to filter")
async def index(interaction: discord.Interaction, rarity: str | None = None):
    user = get_user(str(interaction.user.id))
    ores = ALL_ORES

    if rarity:
        rarity = rarity.lower()
        if rarity not in RARITY_DATA:
            await interaction.response.send_message(
                rarity_error_text(),
                ephemeral=True
            )
            return
        ores = RARITY_DATA[rarity]["ores"]

    ores = sorted(ores)

    embed = discord.Embed(
        title="🪨 Ore Index",
        description=f"Discovered **{len([o for o in ores if o in user['found'])}/{len(ores)}** ores",
        color=discord.Color.blurple()
    )

    for ore in ores:
        status = "✅" if ore in user["found"] else "❌"
        embed.add_field(name=ore, value=status, inline=True)

    add_footer(embed, interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)
# =====================
# LEADERBOARD VIEW
# =====================
class LeaderboardView(View):
    def __init__(self, requester: discord.User, guild: discord.Guild):
        super().__init__(timeout=120)
        self.requester = requester
        self.guild = guild
        self.page = 1

        self.back_btn = Button(label="← Back", style=discord.ButtonStyle.secondary)
        self.next_btn = Button(label="Next →", style=discord.ButtonStyle.primary)

        self.back_btn.callback = self.prev_page
        self.next_btn.callback = self.next_page

        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.page > 1:
            self.add_item(self.back_btn)
        if self.page < 3:
            self.add_item(self.next_btn)

    async def build_embed(self):
        embed = discord.Embed(color=discord.Color.gold())

        members = {str(m.id) for m in self.guild.members}
        data = [(uid, d) for uid, d in bananas_db.items() if uid in members]

        if self.page == 1:
            embed.title = "🏆 Leaderboard — 🍌 Bananas"
            data.sort(key=lambda x: x[1]["bananas"], reverse=True)
            key = "bananas"
        elif self.page == 2:
            embed.title = "🏆 Leaderboard — 🔥 Current Streak"
            data.sort(key=lambda x: x[1]["streak"], reverse=True)
            key = "streak"
        else:
            embed.title = "🏆 Leaderboard — 🏆 Best Streak"
            data.sort(key=lambda x: x[1]["best_streak"], reverse=True)
            key = "best_streak"

        players = ""
        values = ""

        for i, (uid, d) in enumerate(data[:10], start=1):
            try:
                user = await bot.fetch_user(int(uid))
                name = user.mention
            except:
                name = "Unknown"

            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            players += f"{medal} {name}\n"
            values += f"{d[key]}\n"

        embed.add_field(name="Player", value=players or "—", inline=True)
        embed.add_field(name="Value", value=values or "—", inline=True)

        embed.set_footer(
            text=f"Requested by {self.requester} | Page {self.page}/3",
            icon_url=self.requester.display_avatar.url
        )

        self.update_buttons()
        return embed

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        await interaction.response.edit_message(
            embed=await self.build_embed(),
            view=self
        )

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        await interaction.response.edit_message(
            embed=await self.build_embed(),
            view=self
        )


# =====================
# LEADERBOARD COMMAND
# =====================
@gargantuan.command(name="leaderboard", description="View the server leaderboard")
async def leaderboard(interaction: discord.Interaction):
    view = LeaderboardView(interaction.user, interaction.guild)
    embed = await view.build_embed()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# =====================
# PROFILE COMMAND
# =====================
@gargantuan.command(name="profile", description="View a player profile")
@app_commands.describe(user="Optional user")
async def profile(interaction: discord.Interaction, user: discord.User | None = None):
    target = user or interaction.user
    data = get_user(str(target.id))

    embed = discord.Embed(
        title=f"🐒 {target.name}'s Profile",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🍌 Bananas", value=data["bananas"], inline=True)
    embed.add_field(name="🔥 Current Streak", value=data["streak"], inline=True)
    embed.add_field(name="🏆 Best Streak", value=data["best_streak"], inline=True)

    add_footer(embed, interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# =====================
# ADD BANANAS (ADMIN)
# =====================
@gargantuan.command(
    name="add_bananas",
    description="Admins only — add bananas to a user"
)
@app_commands.describe(user="User", amount="Bananas (1–1000)")
async def add_bananas(
    interaction: discord.Interaction,
    user: discord.User,
    amount: int
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Admins only.",
            ephemeral=True
        )
        return

    if amount < 1 or amount > 1000:
        await interaction.response.send_message(
            "❌ Amount must be between 1 and 1000.",
            ephemeral=True
        )
        return

    target = get_user(str(user.id))
    target["bananas"] += amount
    save_db()
    push_to_github()

    await interaction.response.send_message(
        f"✅ Added {amount} bananas to {user.mention}",
        ephemeral=True
    )


# =====================
# ON READY — COMMAND SYNC
# =====================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    try:
        tree.add_command(gargantuan)
        await tree.sync()
        print("✅ Slash commands synced")
    except Exception as e:
        print("❌ Command sync failed:", e)


# =====================
# RUN BOT
# =====================
bot.run(TOKEN)
