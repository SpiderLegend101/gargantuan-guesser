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


def push_to_github():
    if not GITHUB_REPO or not GITHUB_TOKEN:
        return
    try:

        repo = GITHUB_REPO.replace("https://", f"https://{GITHUB_TOKEN}@")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run([
            "git", "commit", "-m",
            f"Auto save {time.strftime('%Y-%m-%d %H:%M:%S')}"
        ], check=True)
        subprocess.run(["git", "push", repo, "HEAD:main"], check=True)
    except Exception:
        pass

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
# SLASH COMMAND GROUP
# =====================
gargantuan = app_commands.Group(
    name="gargantuan",
    description="Gargantuan Guesser commands"
)
tree.add_command(gargantuan)

# =====================
# RARITY DATA
# =====================
RARITY_DATA = {
    "common": {"color": 0x95a5a6, "chance": 22, "cost": 5,
               "ores": ["Stone", "Sand Stone", "Copper", "Iron", "Grass",
                        "Cardboardite", "Tungsten", "Fichillium", "Mosasaursit"]},
    "uncommon": {"color": 0x2ecc71, "chance": 19, "cost": 10,
                 "ores": ["Tin", "Silver", "Gold", "Bananite", "Cobalt",
                          "Titanium", "Lapis Lazuli", "Sulfur"]},
    "rare": {"color": 0x3498db, "chance": 16, "cost": 20,
             "ores": ["Mushroomite", "Platinum", "Volcanic Rock", "Quartz",
                      "Amethyst", "Topaz", "Diamond", "Sapphire", "Boneite",
                      "Scheelite", "Pumice", "Graphite", "Aetherit", "Dark Boneite",
                      "Mistvein", "Lgarite"]},
    "epic": {"color": 0xbf75e9, "chance": 14, "cost": 30,
             "ores": ["Aite", "Poopite", "Slimite", "Cuprite", "Obsidian",
                      "Emerald", "Ruby", "Rivalite", "Blue Crystal", "Orange Crystal",
                      "Green Crystal", "Magenta Crystal", "Crimson Crystal", "Larimar",
                      "Neurotite", "Frost Fossil", "Tide Carve", "Moltenfrost",
                      "Crimsonite", "Malachite", "Aquajade", "Cryptex", "Frogite"]},
    "legendary": {"color": 0xfdb745, "chance": 12, "cost": 40,
                  "ores": ["Uranium", "Mythril", "Eye Ore", "Velchire", "Sanctis",
                           "Fireite", "Magmaite", "Lightite", "Snowite",
                           "Rainbow Crystal", "Moon Stone", "Voidstar", "Gulabite",
                           "Coinite", "Prismatic Heart"]},
    "mythical": {"color": 0xff4d4d, "chance": 10, "cost": 50,
                 "ores": ["Demonite", "Darkryte", "Iceite", "Etherealite",
                          "Duranite", "Voidfractal", "Galestor", "Evil Eye",
                          "Yeti Heart", "Arcane Crystal"]},
    "divine": {"color": 0x5b2b9a, "cost": 60, "chance": 7,
               "ores": ["Suryafal", "Stolen Heart", "Golem Heart", "Heart of The Island",
                        "Heavenite", "Gargantuan", "Galaxite"]},
}

ALL_RARITIES = list(RARITY_DATA.keys())
ALL_ORES = [ore for data in RARITY_DATA.values() for ore in data["ores"]]

            # =====================
            # ORE IMAGE MAP
            # =====================
ORE_IMAGE = {}
if os.path.exists(ORES_DIR):
                for f in os.listdir(ORES_DIR):
                    if f.lower().endswith((".png", ".webp")):
                        # Keep original filename safe
                        name = f.rsplit(".", 1)[0].replace("_", " ")
                        ORE_IMAGE[name] = f"{ORES_DIR}/{f}"


# =====================
# RANDOM HELPERS
# =====================
def pick_rarity():
    keys = list(RARITY_DATA.keys())
    weights = [RARITY_DATA[k]["chance"] for k in keys]
    return random.choices(keys, weights=weights)[0]

def pick_ore_within_rarity(rarity):
    ores = RARITY_DATA[rarity]["ores"]
    n = len(ores)
    weights = [n - i for i in range(n)]
    return random.choices(ores, weights=weights)[0]

def rarity_error_text():
    return "❌ Invalid rarity.\nAvailable rarities: " + ", ".join(r.capitalize() for r in ALL_RARITIES)

def add_footer(embed: discord.Embed, user: discord.User):
    embed.set_footer(text=f"Requested by {user}", icon_url=user.display_avatar.url)

def calculate_banana_reward(streak):
    if streak >= 20:
        return 5
    elif streak >= 10:
        return 3
    elif streak >= 5:
        return 2
    else:
        return 1

# =====================
# ORE BUTTON & VIEW
# =====================
class OreButton(Button):
    def __init__(self, label, view: "OreView"):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.ore_view = view

    async def callback(self, interaction: discord.Interaction):
        if self.ore_view.answered:
            await interaction.response.send_message("⏱️ This ore has already been guessed!", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        if user_id in INCORRECT_USERS.get(self.ore_view.message_id, []):
            await interaction.response.send_message("❌ You already guessed incorrectly for this ore!", ephemeral=True)
            return

        if self.label == self.ore_view.correct:
            self.ore_view.answered = True
            await self.ore_view.disable_all()
            CURRENT_VIEWS.pop(self.ore_view.message_id, None)

            user_data = get_user(user_id)
            reward = calculate_banana_reward(user_data["streak"])
            user_data["bananas"] += reward
            user_data["streak"] += 1
            if user_data["streak"] > user_data["best_streak"]:
                user_data["best_streak"] = user_data["streak"]
            if self.ore_view.correct not in user_data["found"]:
                user_data["found"].append(self.ore_view.correct)
            save_db()

            await interaction.response.edit_message(
                content=(
                    f"✅ Correct! {interaction.user.mention} found **{self.label}** 🍌\n"
                    f"🔥 Streak: {user_data['streak']}\n"
                    f"🍌 Reward: {reward} bananas"
                ),
                view=self.ore_view
            )
            ACTIVE_SPAWN.discard(self.ore_view.channel_id)
        else:
            INCORRECT_USERS.setdefault(self.ore_view.message_id, []).append(user_id)
            get_user(user_id)["streak"] = 0
            save_db()
            await interaction.response.send_message(f"❌ Wrong! {self.label} is not correct.", ephemeral=True)


class OreView(View):
    def __init__(self, correct, options, message_id, rarity, channel_id=None, timeout=60):
        super().__init__(timeout=timeout)
        self.correct = correct
        self.message_id = message_id
        self.rarity = rarity
        self.answered = False
        self.channel_id = channel_id

        for opt in options:
            self.add_item(OreButton(opt, self))

    async def disable_all(self):
        for child in self.children:
            child.disabled = True

    async def on_timeout(self):
        if self.answered:
            return
        self.answered = True
        await self.disable_all()
        CURRENT_VIEWS.pop(self.message_id, None)

        channel = bot.get_channel(self.channel_id) if self.channel_id else None
        if channel:
            await channel.send(f"⏱️ **Nobody guessed the ore. It was {self.correct}!**")
        ACTIVE_SPAWN.discard(self.channel_id)


# =====================
# SPAWN LOGIC
# =====================

async def spawn_ore(
    guild_id,
    forced_rarity=None,
    channel_override=None,
    dm_user=None,
    spawned_by: discord.User | None = None
):
    servers = load_json(SERVERS_FILE)
    guild_data = servers.get(str(guild_id))
    if not guild_data and not dm_user:
        return

    channel_id = guild_data.get("spawn_channel") if guild_data else None
    channel = channel_override or (bot.get_channel(channel_id) if channel_id else None)
    if channel and channel.id in ACTIVE_SPAWN:
        return

    rarity = forced_rarity or pick_rarity()
    ore = pick_ore_within_rarity(rarity)

    options = random.sample(ALL_ORES, 3)
    if ore not in options:
        options[random.randint(0, 2)] = ore
    random.shuffle(options)

    desc = f"**Rarity:** {rarity.capitalize()}"
    if spawned_by:
        desc += f"\n**Spawned by:** {spawned_by.mention}"

    embed = discord.Embed(
        title="🪨 Guess the Ore!",
        description=desc,
        color=RARITY_DATA[rarity]["color"]
    )

    files = []
    if ore in ORE_IMAGE and os.path.exists(ORE_IMAGE[ore]):
            embed.set_image(url=f"attachment://{os.path.basename(ORE_IMAGE[ore])}")
            files.append(discord.File(ORE_IMAGE[ore], filename=os.path.basename(ORE_IMAGE[ore])))


    if dm_user:
        msg = await dm_user.send(embed=embed, files=files)
        view = OreView(ore, options, ("dm", msg.id), rarity)
        await msg.edit(view=view)
        CURRENT_VIEWS[("dm", msg.id)] = view
        return

    msg = await channel.send(embed=embed, files=files)
    view = OreView(ore, options, (channel.id, msg.id), rarity, channel_id=channel.id)
    await msg.edit(view=view)
    CURRENT_VIEWS[(channel.id, msg.id)] = view
    ACTIVE_SPAWN.add(channel.id)

# =====================
# AUTO SPAWNER (respects interval)
# =====================
@tasks.loop(seconds=5)
async def auto_spawn():
    now = time.time()
    servers = load_json(SERVERS_FILE)
    for gid, data in servers.items():
        channel_id = data.get("spawn_channel")
        if not channel_id or channel_id in ACTIVE_SPAWN:
            continue
        last_spawn = data.get("last_spawn", 0)
        interval = data.get("interval", 60)
        if now - last_spawn >= interval:
            await spawn_ore(int(gid))
            data["last_spawn"] = now
    save_servers()

@auto_spawn.before_loop
async def before_spawn():
    await bot.wait_until_ready()

# =====================
# ROTATE STATUS
# =====================
statuses = [
    discord.Game(name="discord.gg/bananite"),
    discord.Game(name="@Gargantuan Guesser to play")
]

@tasks.loop(seconds=15)
async def rotate_status():
    i = 0
    while True:
        await bot.change_presence(status=discord.Status.dnd, activity=statuses[i])
        i = (i + 1) % len(statuses)
        await asyncio.sleep(15)

# =====================
# ON READY
# =====================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} commands")
    except Exception as e:
        print("Sync failed:", e)

    if not auto_spawn.is_running():
        auto_spawn.start()
    if not rotate_status.is_running():
        rotate_status.start()
# =====================
# SETUP COMMAND
# =====================
@gargantuan.command(name="setup", description="Set the channel for ore spawns to occur")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Select the channel for ore spawns")
async def setup(interaction: discord.Interaction, channel: discord.TextChannel):
    servers_db[str(interaction.guild.id)] = {
        "spawn_channel": channel.id,
        "last_spawn": 0
    }
    save_servers()
    await interaction.response.send_message(
        f"✅ Ore spawns will appear in {channel.mention}.", ephemeral=True
    )

# =====================
# SPAWN COMMAND (ADMIN)
# =====================
@gargantuan.command(name="spawn", description="Admins only - spawn a random or specific rarity ore")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(rarity="Optional: select rarity to spawn")
@app_commands.choices(rarity=[app_commands.Choice(name=r.capitalize(), value=r) for r in ALL_RARITIES])
async def spawn(interaction: discord.Interaction, rarity: str = None):
    rarity_value = rarity.lower() if rarity else None
    if rarity_value and rarity_value not in ALL_RARITIES:
        await interaction.response.send_message(rarity_error_text(), ephemeral=True)
        return

    await spawn_ore(
        interaction.guild.id,
        forced_rarity=rarity_value,
        channel_override=interaction.channel,
        spawned_by=interaction.user
    )
    await interaction.response.send_message(
        f"✅ Spawned a {'random' if not rarity_value else rarity_value.capitalize()} ore!",
        ephemeral=True
    )

# =====================
# REDEEM SPAWN COMMAND
# =====================
@gargantuan.command(name="redeem_spawn", description="Redeem bananas for a guaranteed ore of selected rarity")
@app_commands.describe(rarity="Select rarity to redeem")
@app_commands.choices(rarity=[app_commands.Choice(name=r.capitalize(), value=r) for r in ALL_RARITIES])
async def redeem_spawn(interaction: discord.Interaction, rarity: str):
    rarity_value = rarity.lower()
    if rarity_value not in ALL_RARITIES:
        await interaction.response.send_message(rarity_error_text(), ephemeral=True)
        return

    user_data = get_user(str(interaction.user.id))
    cost = RARITY_DATA[rarity_value]["cost"]

    if user_data["bananas"] < cost:
        await interaction.response.send_message(
            f"❌ You need {cost} 🍌 bananas to redeem a {rarity_value.capitalize()} ore.",
            ephemeral=True
        )
        return

    user_data["bananas"] -= cost
    save_db()

    await spawn_ore(interaction.guild.id, forced_rarity=rarity_value, dm_user=interaction.user)
    await interaction.response.send_message(
        f"✅ Redeemed {cost} 🍌 bananas for a {rarity_value.capitalize()} ore! Check your DMs.",
        ephemeral=True
    )

# =====================
# ADD BANANAS COMMAND (ADMIN)
# =====================
@gargantuan.command(name="add_bananas", description="Admins only - add bananas to a user.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="User to add bananas to", amount="Amount to add (1-1000)")
async def add_bananas(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount < 1 or amount > 1000:
        await interaction.response.send_message("❌ Amount must be between 1 and 1000.", ephemeral=True)
        return

    user_data = get_user(str(user.id))
    user_data["bananas"] += amount
    save_db()
    await interaction.response.send_message(f"🍌 Added {amount} bananas to {user.mention}.", ephemeral=True)

# =====================
# INDEX COMMAND
# =====================
@gargantuan.command(name="index", description="View your ore gallery")
@app_commands.describe(rarity="Filter ores by rarity")
@app_commands.choices(rarity=[
    app_commands.Choice(name=r.capitalize(), value=r)
    for r in ALL_RARITIES
])
async def index(interaction: discord.Interaction, rarity: str = None):
    rarity_value = rarity.lower() if rarity else None
    view = GalleryView(interaction.user.id, rarity_value)
    embed = await view.build_embed()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# =====================
# GALLERY VIEW
# =====================
class GalleryView(View):
                def __init__(self, user_id, rarity=None):
                    super().__init__(timeout=180)
                    self.user_id = str(user_id)
                    self.page = 0
                    self.ores_per_page = 21
                    self.rarity = rarity

                    # Buttons
                    self.back_btn = Button(label="← Back", style=discord.ButtonStyle.secondary)
                    self.next_btn = Button(label="Next →", style=discord.ButtonStyle.primary)
                    self.refresh_btn = Button(label="🔄 Refresh", style=discord.ButtonStyle.success)

                    self.back_btn.callback = self.prev_page
                    self.next_btn.callback = self.next_page
                    self.refresh_btn.callback = self.refresh_page

                    self.update_buttons()

                def filtered_ores(self):
                    if not self.rarity:
                        return ALL_ORES.copy()
                    return RARITY_DATA[self.rarity]["ores"]

                def update_buttons(self):
                    self.clear_items()
                    if self.page > 0:
                        self.add_item(self.back_btn)
                    if (self.page + 1) * self.ores_per_page < len(self.filtered_ores()):
                        self.add_item(self.next_btn)
                    self.add_item(self.refresh_btn)

                async def build_embed(self):
                    user_data = get_user(self.user_id)
                    ores = self.filtered_ores()
                    start = self.page * self.ores_per_page
                    end = start + self.ores_per_page
                    ores_page = ores[start:end]

                    # ✅ Count found exactly like index
                    discovered = [ore for ore in ores if ore in user_data["found"]]

                    embed = discord.Embed(
                        title="🪨 Your Ore Collection",
                        color=RARITY_DATA[self.rarity]["color"] if self.rarity else discord.Color.blurple()
                    )
                    desc = f"**Discovered {len(discovered)}/{len(ores)} ores**\n\n"

                    guild = None
                    for g in bot.guilds:
                        if any(int(self.user_id) == m.id for m in g.members):
                            guild = g
                            break

                    rows = [ores_page[i:i + 3] for i in range(0, len(ores_page), 3)]
                    for row in rows:
                        line1 = ""
                        line2 = ""
                        for ore in row:
                            emoji = None
                            if guild:
                                emoji = discord.utils.get(guild.emojis, name=ore.replace(" ", "_"))
                            emoji_str = str(emoji) if emoji else f":{ore.replace(' ', '_')}:"
                            line1 += f"{emoji_str} {ore}    "
                            line2 += ("✅" if ore in user_data["found"] else "❌") + "        "
                        desc += line1.rstrip() + "\n" + line2.rstrip() + "\n\n"

                    embed.description = desc.strip()
                    return embed

                # ---------- Navigation callbacks ----------
                async def next_page(self, interaction: discord.Interaction):
                    self.page += 1
                    self.update_buttons()
                    embed = await self.build_embed()
                    await interaction.response.edit_message(embed=embed, view=self)

                async def prev_page(self, interaction: discord.Interaction):
                    self.page -= 1
                    self.update_buttons()
                    embed = await self.build_embed()
                    await interaction.response.edit_message(embed=embed, view=self)

                async def refresh_page(self, interaction: discord.Interaction):
                    self.update_buttons()
                    embed = await self.build_embed()
                    await interaction.response.edit_message(embed=embed, view=self)

# =====================
# PROFILE COMMAND
# =====================
# =====================
# INDEX GALLERY VIEW
# =====================
class GalleryView(View):
    def __init__(self, user_id, rarity=None):
        super().__init__(timeout=180)
        self.user_id = str(user_id)
        self.page = 0
        self.ores_per_page = 21
        self.rarity = rarity

        # Buttons
        self.back_btn = Button(label="← Back", style=discord.ButtonStyle.secondary)
        self.next_btn = Button(label="Next →", style=discord.ButtonStyle.primary)
        self.refresh_btn = Button(label="🔄 Refresh", style=discord.ButtonStyle.success)

        self.back_btn.callback = self.prev_page
        self.next_btn.callback = self.next_page
        self.refresh_btn.callback = self.refresh_page

        self.update_buttons()

    def filtered_ores(self):
        if not self.rarity:
            return ALL_ORES.copy()
        return RARITY_DATA[self.rarity]["ores"]

    def update_buttons(self):
        self.clear_items()
        if self.page > 0:
            self.add_item(self.back_btn)
        if (self.page + 1) * self.ores_per_page < len(self.filtered_ores()):
            self.add_item(self.next_btn)
        self.add_item(self.refresh_btn)

    async def build_embed(self):
        user_data = get_user(self.user_id)
        ores = self.filtered_ores()
        start = self.page * self.ores_per_page
        end = start + self.ores_per_page
        ores_page = ores[start:end]

        # Count discovered
        discovered = [ore for ore in ores if ore in user_data["found"]]

        embed = discord.Embed(
            title="🪨 Your Ore Collection",
            color=RARITY_DATA[self.rarity]["color"] if self.rarity else discord.Color.blurple()
        )
        desc = f"**Discovered {len(discovered)}/{len(ores)} ores**\n\n"

        guild = None
        for g in bot.guilds:
            if any(int(self.user_id) == m.id for m in g.members):
                guild = g
                break

        rows = [ores_page[i:i + 3] for i in range(0, len(ores_page), 3)]
        for row in rows:
            line1 = ""
            line2 = ""
            for ore in row:
                emoji = None
                if guild:
                    emoji = discord.utils.get(guild.emojis, name=ore.replace(" ", "_"))
                emoji_str = str(emoji) if emoji else f":{ore.replace(' ', '_')}:"
                line1 += f"{emoji_str} {ore}    "
                line2 += ("✅" if ore in user_data["found"] else "❌") + "        "
            desc += line1.rstrip() + "\n" + line2.rstrip() + "\n\n"

        embed.description = desc.strip()
        add_requester_footer(embed, await bot.fetch_user(int(self.user_id)))
        return embed

    # Navigation
    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.update_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def refresh_page(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)


# =====================
# PROFILE COMMAND
# =====================
@gargantuan.command(name="profile", description="View your profile")
async def profile(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    data = get_user(user_id)

    # Determine title by highest fully completed rarity
    title = "No Title"
    for rarity in reversed(ALL_RARITIES):  # Start from highest rarity
        ores = RARITY_DATA[rarity]["ores"]
        if all(o in data["found"] for o in ores):
            title = f"{rarity.capitalize()} Collector"
            break
    if all(ore in data["found"] for ore in ALL_ORES):
        title = "Master Collector"

    # Global rank
    sorted_users = sorted(
        bananas_db.items(),
        key=lambda x: x[1]["bananas"],
        reverse=True
    )
    rank = next((i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == user_id), "N/A")

    embed = discord.Embed(
        title=f"{interaction.user.name}'s Profile — {title}",
        color=discord.Color.gold()
    )
    embed.add_field(name="🍌 Bananas", value=data["bananas"], inline=True)
    embed.add_field(name="🔥 Current Streak", value=data["streak"], inline=True)
    embed.add_field(name="🏆 Best Streak", value=data["best_streak"], inline=True)
    total_discovered = sum(1 for ore in ALL_ORES if ore in data["found"])
    embed.add_field(name="🔍 Ores Found", value=f"{total_discovered}/{len(ALL_ORES)}", inline=True)
    embed.add_field(name="🌐 Global Rank", value=f"#{rank}", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)
# =====================
# SAVE COMMAND (ADMIN)
# =====================
@gargantuan.command(name="save", description="Admins only — save all players' stats to disk and GitHub")
async def save(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admins only", ephemeral=True)
            return

        # Save locally
        save_db()
        save_servers()

        pushed = False
        if GITHUB_REPO and GITHUB_TOKEN:
            try:
                # Add token to repo URL for authentication
                auth_repo = GITHUB_REPO.replace("https://", f"https://{GITHUB_TOKEN}@")

                # Git config & push
                subprocess.run(["git", "config", "user.name", "GargantuanBot"], check=True)
                subprocess.run(["git", "config", "user.email", "bot@example.com"], check=True)
                subprocess.run(["git", "add", "--all"], check=True)
                subprocess.run(
                    ["git", "commit", "-m", f"Update db & servers by {interaction.user.name}"], 
                    check=False
                )
                subprocess.run(["git", "push", auth_repo, "HEAD:main"], check=True)
                pushed = True
            except subprocess.CalledProcessError as e:
                print("❌ Git push failed:", e)
                pushed = False

        if pushed:
            await interaction.response.send_message(
                "✅ db.json and servers.json saved locally **and** pushed to GitHub! 🎉", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "✅ Saved locally. ⚠️ Push to GitHub failed (nothing to commit or check GITHUB_TOKEN/GITHUB_REPO).", 
                ephemeral=True
            )
# =====================
@gargantuan.command(name="leaderboard", description="View the top players in your server")
async def leaderboard(interaction: discord.Interaction):
    view = LeaderboardView(interaction.user, interaction.guild)
    embed = await view.build_embed()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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

        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.page > 1:
            self.add_item(self.back_btn)
        if self.page < 3:
            self.add_item(self.next_btn)

    async def build_embed(self):
        embed = discord.Embed(color=discord.Color.gold())
        guild_user_ids = {str(m.id) for m in self.guild.members}

        if self.page == 1:
            embed.title = "🏆 Leaderboard — 🍌 Most Bananas"
            key = "bananas"
            sorted_users = sorted(
                ((uid, d) for uid, d in bananas_db.items() if uid in guild_user_ids),
                key=lambda x: (x[1]["bananas"], x[1]["best_streak"]),
                reverse=True
            )
        elif self.page == 2:
            embed.title = "🏆 Leaderboard — 🔥 Current Streak"
            key = "streak"
            sorted_users = sorted(
                ((uid, d) for uid, d in bananas_db.items() if uid in guild_user_ids),
                key=lambda x: x[1]["streak"],
                reverse=True
            )
        else:
            embed.title = "🏆 Leaderboard — 🏆 Best Streak Ever"
            key = "best_streak"
            sorted_users = sorted(
                ((uid, d) for uid, d in bananas_db.items() if uid in guild_user_ids),
                key=lambda x: x[1]["best_streak"],
                reverse=True
            )

        players = ""
        values = ""
        top10 = []

        for i, (uid, data) in enumerate(sorted_users[:10], start=1):
            top10.append(uid)
            try:
                user = self.guild.get_member(int(uid)) or await bot.fetch_user(int(uid))
                name = user.mention
            except:
                name = "Unknown"

            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            players += f"{medal} {name}\n"
            values += f"{data[key]}\n"

        embed.add_field(name="Player", value=players or "—", inline=True)
        embed.add_field(name="Value", value=values or "—", inline=True)

        # Show requester rank if not top 10
        requester_id = str(self.requester.id)
        if requester_id in guild_user_ids and requester_id not in top10:
            ranked = sorted(
                ((uid, d) for uid, d in bananas_db.items() if uid in guild_user_ids),
                key=lambda x: x[1][key],
                reverse=True
            )
            rank = next((i + 1 for i, (uid, _) in enumerate(ranked) if uid == requester_id), "N/A")
            embed.add_field(
                name="──────────",
                value=f"Your rank: **#{rank}**\nValue: **{bananas_db[requester_id][key]}**",
                inline=False
            )

        embed.set_footer(
            text=f"Requested by {self.requester} | Page {self.page}/3",
            icon_url=self.requester.display_avatar.url
        )

        return embed

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.update_buttons()
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
    def __init__(self, user_id, rarity=None):
        super().__init__(timeout=180)
        self.user_id = str(user_id)
        self.page = 0
        self.ores_per_page = 21
        self.rarity = rarity

        # Buttons
        self.back_btn = Button(label="← Back", style=discord.ButtonStyle.secondary)
        self.next_btn = Button(label="Next →", style=discord.ButtonStyle.primary)
        self.refresh_btn = Button(label="🔄 Refresh", style=discord.ButtonStyle.success)

        self.back_btn.callback = self.prev_page
        self.next_btn.callback = self.next_page
        self.refresh_btn.callback = self.refresh_page

        self.update_buttons()

    def filtered_ores(self):
        if not self.rarity:
            return ALL_ORES.copy()
        return RARITY_DATA[self.rarity]["ores"]

    def update_buttons(self):
        self.clear_items()
        if self.page > 0:
            self.add_item(self.back_btn)
        if (self.page + 1) * self.ores_per_page < len(self.filtered_ores()):
            self.add_item(self.next_btn)
        self.add_item(self.refresh_btn)

    async def build_embed(self):
        user_data = get_user(self.user_id)
        ores = self.filtered_ores()
        start = self.page * self.ores_per_page
        end = start + self.ores_per_page
        ores_page = ores[start:end]

        # Count discovered
        discovered = [ore for ore in ores if ore in user_data["found"]]

        embed = discord.Embed(
            title="🪨 Your Ore Collection",
            color=RARITY_DATA[self.rarity]["color"] if self.rarity else discord.Color.blurple()
        )
        desc = f"**Discovered {len(discovered)}/{len(ores)} ores**\n\n"

        guild = None
        for g in bot.guilds:
            if any(int(self.user_id) == m.id for m in g.members):
                guild = g
                break

        rows = [ores_page[i:i + 3] for i in range(0, len(ores_page), 3)]
        for row in rows:
            line1 = ""
            line2 = ""
            for ore in row:
                emoji = None
                if guild:
                    emoji = discord.utils.get(guild.emojis, name=ore.replace(" ", "_"))
                emoji_str = str(emoji) if emoji else f":{ore.replace(' ', '_')}:"
                line1 += f"{emoji_str} {ore}    "
                line2 += ("✅" if ore in user_data["found"] else "❌") + "        "
            desc += line1.rstrip() + "\n" + line2.rstrip() + "\n\n"

        embed.description = desc.strip()
        add_requester_footer(embed, await bot.fetch_user(int(self.user_id)))
        return embed

    # Navigation
    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.update_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def refresh_page(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

# =====================
# AUTO SPAWN TASK
# =====================
@tasks.loop(seconds=10)
async def auto_spawn():
    for guild_id, data in servers_db.items():
        channel_id = data.get("spawn_channel")
        last_spawn = data.get("last_spawn", 0)
        now = time.time()

        if channel_id and (now - last_spawn) >= 60 and channel_id not in ACTIVE_SPAWN:
            await spawn_ore(int(guild_id), channel_override=bot.get_channel(channel_id))
            servers_db[guild_id]["last_spawn"] = now
            save_servers()

@auto_spawn.before_loop
async def before_auto_spawn():
    await bot.wait_until_ready()

# =====================
# ROTATE STATUS (DND)
# =====================
statuses = [
    discord.Game(name="discord.gg/bananite"),
    discord.Game(name="@Gargantuan Guesser to play")
]

@tasks.loop(seconds=15)
async def rotate_status():
    i = 0
    while True:
        await bot.change_presence(status=discord.Status.dnd, activity=statuses[i])
        i = (i + 1) % len(statuses)
        await asyncio.sleep(15)

# =====================
# ON READY
# =====================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} commands")
    except Exception as e:
        print("Sync failed:", e)

    if not auto_spawn.is_running():
        auto_spawn.start()
    if not rotate_status.is_running():
        rotate_status.start()

# =====================
# ON MESSAGE
# =====================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        try:
            await message.author.send(TUTORIAL_MESSAGE)
        except:
            pass
    await bot.process_commands(message)

# =====================
# RUN BOT
# =====================
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set")
    bot.run(TOKEN)
