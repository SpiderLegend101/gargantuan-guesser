import discord
from discord.ext import tasks
from discord import app_commands
from discord.ui import View, Button
import os
import json
import random
import requests

# =====================
# CONFIG (YOU EDIT THESE)
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")  # DO NOT PUT TOKEN HERE
GUILD_ID = 1449955287682514976       # <-- PUT YOUR SERVER ID
SPAWN_CHANNEL_ID = 1463900161032978677  # <-- PUT ORE SPAWN CHANNEL ID
SPAWN_INTERVAL = 120  # seconds (2 minutes)

DB_FILE = "db.json"

# =====================
# WIKI API
# =====================
WIKI_API = "https://forge-roblox.fandom.com/api.php"

# =====================
# LOAD / SAVE DB
# =====================
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        bananas_db = json.load(f)
else:
    bananas_db = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(bananas_db, f, indent=4)

# =====================
# GET ALL ORES (ALL WORLDS)
# =====================
def get_all_ores():
    ores = []
    cmcontinue = None

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:Ores",
            "cmlimit": "500",
            "format": "json"
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        r = requests.get(WIKI_API, params=params).json()
        ores.extend([p["title"] for p in r["query"]["categorymembers"]])

        if "continue" not in r:
            break
        cmcontinue = r["continue"]["cmcontinue"]

    return ores

# =====================
# GET ORE IMAGE
# =====================
def get_ore_image(ore_name):
    params = {
        "action": "query",
        "titles": ore_name,
        "prop": "pageimages",
        "pithumbsize": 512,
        "format": "json"
    }

    r = requests.get(WIKI_API, params=params).json()
    pages = r["query"]["pages"]

    for page in pages.values():
        if "thumbnail" in page:
            return page["thumbnail"]["source"]

    return None

ALL_ORES = get_all_ores()

# =====================
# BOT SETUP
# =====================
intents = discord.Intents.default()
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

class OreButton(Button):
    def __init__(self, label, view):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if self.view_ref.answered:
            await interaction.response.send_message(
                "Sorry, but this was answered by another person before you.",
                ephemeral=True
            )
            return

        if self.label == self.view_ref.correct_ore:
            self.view_ref.answered = True

            user_id = str(interaction.user.id)
            bananas_db[user_id] = bananas_db.get(user_id, 0) + 1
            save_db()

            for item in self.view_ref.children:
                item.disabled = True

            await interaction.response.edit_message(
                content=f"🍌 {interaction.user.mention} guessed it first! +1 Banana.\n"
                        f"The ore was **{self.view_ref.correct_ore}**.",
                view=self.view_ref
            )
        else:
            await interaction.response.send_message(
                "Wrong guess!",
                ephemeral=True
            )

# =====================
# SPAWN ORE
# =====================
async def spawn_ore():
    channel = bot.get_channel(SPAWN_CHANNEL_ID)
    if not channel:
        return

    correct = random.choice(ALL_ORES)
    image_url = get_ore_image(correct)

    decoys = random.sample([o for o in ALL_ORES if o != correct], 2)
    options = [correct] + decoys
    random.shuffle(options)

    view = OreView(correct)
    for option in options:
        view.add_item(OreButton(option, view))

    embed = discord.Embed(title="Guess the ore!")
    if image_url:
        embed.set_image(url=image_url)

    await channel.send(embed=embed, view=view)

# =====================
# SPAWN LOOP
# =====================
@tasks.loop(seconds=SPAWN_INTERVAL)
async def spawn_loop():
    await spawn_ore()

# =====================
# SLASH COMMANDS
# =====================
@tree.command(name="bananas", description="Check your bananas")
async def bananas(interaction: discord.Interaction):
    count = bananas_db.get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"🍌 You have {count} bananas.")

@tree.command(name="leaderboard", description="Top banana holders")
async def leaderboard(interaction: discord.Interaction):
    top = sorted(bananas_db.items(), key=lambda x: x[1], reverse=True)[:10]
    if not top:
        await interaction.response.send_message("No bananas yet!")
        return

    msg = "**🍌 Banana Leaderboard 🍌**\n"
    for i, (uid, count) in enumerate(top, 1):
        user = await bot.fetch_user(int(uid))
        msg += f"{i}. {user.name} — {count}\n"

    await interaction.response.send_message(msg)

# =====================
# READY
# =====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    spawn_loop.start()

# =====================
# RUN
# =====================
bot.run(TOKEN)
