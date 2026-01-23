import discord
from discord.ext import tasks
from discord.ui import View, Button
import os
import json
import random

# =====================
# CONFIG
# =====================
TOKEN = os.getenv("DISCORD_TOKEN")  # set in host env vars
GUILD_ID = 1449955287682514976
SPAWN_CHANNEL_ID = 1463900161032978677
SPAWN_INTERVAL = 120  # seconds

DB_FILE = "db.json"
ORES_DIR = "ores"

# =====================
# LOAD DB
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
# LOAD ORES FROM FOLDER
# =====================
# Converts: Rainbow_Crystal_Ore.webp -> Rainbow Crystal Ore
ALL_ORES = []
ORE_FILE_MAP = {}  # "Rainbow Crystal Ore" -> "Rainbow_Crystal_Ore.webp"

for file in os.listdir(ORES_DIR):
    if file.lower().endswith(".webp"):
        name = file[:-5].replace("_", " ")
        ALL_ORES.append(name)
        ORE_FILE_MAP[name] = file

if not ALL_ORES:
    raise RuntimeError("❌ No .webp ore images found in /ores folder")

print(f"Loaded {len(ALL_ORES)} ores")

# =====================
# BOT
# =====================
intents = discord.Intents.default()
bot = discord.Client(intents=intents)

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
        # Someone already answered
        if self.view_ref.answered:
            await interaction.response.send_message(
                "Sorry, but this was answered by another person before you.",
                ephemeral=True
            )
            return

        # Correct answer
        if self.label == self.view_ref.correct_ore:
            self.view_ref.answered = True

            uid = str(interaction.user.id)
            bananas_db[uid] = bananas_db.get(uid, 0) + 1
            save_db()

            # Disable all buttons
            for b in self.view_ref.children:
                b.disabled = True

            await interaction.response.edit_message(
                content=(
                    f"🍌 {interaction.user.mention} guessed it first! +1 Banana.\n"
                    f"The ore was **{self.view_ref.correct_ore}**."
                ),
                view=self.view_ref
            )

        # Wrong answer
        else:
            await interaction.response.send_message(
                "❌ Sorry, but your answer is incorrect.",
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

    decoys = random.sample(
        [o for o in ALL_ORES if o != correct],
        k=2
    )

    options = [correct] + decoys
    random.shuffle(options)

    view = OreView(correct)
    for opt in options:
        view.add_item(OreButton(opt, view))

    file_path = os.path.join(ORES_DIR, ORE_FILE_MAP[correct])
    file = discord.File(file_path)

    await channel.send(
        content="🪨 **Guess the ore!**",
        file=file,
        view=view
    )

# =====================
# LOOP
# =====================
@tasks.loop(seconds=SPAWN_INTERVAL)
async def spawn_loop():
    await spawn_ore()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    spawn_loop.start()

# =====================
# RUN
# =====================
bot.run(TOKEN)
