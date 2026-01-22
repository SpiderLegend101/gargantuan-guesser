import discord
from discord.ext import tasks
from discord import app_commands
import json
import os
import random
from discord.ui import View, Button
from dotenv import load_dotenv
load_dotenv()


# -----------------------------
# CONFIG
# -----------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1449955287682514976  # Replace with your server ID
SPAWN_CHANNEL_ID = 1463900161032978677  # Replace with the channel ID for ore spawns
SPAWN_INTERVAL = 120  # seconds

DB_FILE = "db.json"
ORES_DIR = "ores"

# -----------------------------
# LOAD ORES
# -----------------------------
ores = [f.split(".")[0] for f in os.listdir(ORES_DIR) if f.endswith((".png", ".jpg", ".jpeg"))]

# -----------------------------
# LOAD BANANA DB
# -----------------------------
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        bananas_db = json.load(f)
else:
    bananas_db = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(bananas_db, f, indent=4)

# -----------------------------
# BOT INIT
# -----------------------------
intents = discord.Intents.default()
intents.members = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# -----------------------------
# BUTTON CLASS
# -----------------------------
class OreButton(Button):
    def __init__(self, label, correct, spawned_message):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.correct = correct
        self.spawned_message = spawned_message
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        if self.clicked:
            await interaction.response.send_message("Sorry, but this was answered by another person before you.", ephemeral=True)
            return

        if self.label == self.correct:
            self.clicked = True
            user_id = str(interaction.user.id)
            bananas_db[user_id] = bananas_db.get(user_id, 0) + 1
            save_db()
            await self.spawned_message.edit(content=f"🍌 {interaction.user.mention} guessed it first! +1 Banana. The ore was **{self.correct}**.")
            # Disable all buttons
            for child in self.spawned_message.components[0].children:
                child.disabled = True
            await self.spawned_message.edit(view=self.spawned_message.components[0])
        else:
            await interaction.response.send_message("Wrong guess!", ephemeral=True)

# -----------------------------
# ORE SPAWN FUNCTION
# -----------------------------
async def spawn_ore():
    channel = bot.get_channel(SPAWN_CHANNEL_ID)
    correct_ore = random.choice(ores)
    # pick 2 decoys
    decoys = random.sample([o for o in ores if o != correct_ore], k=2)
    all_options = [correct_ore] + decoys
    random.shuffle(all_options)

    # Create buttons
    view = View()
    dummy_message = None  # placeholder for message object
    for option in all_options:
        view.add_item(OreButton(option, correct_ore, dummy_message))

    # Send ore image with buttons
    file = discord.File(f"{ORES_DIR}/{correct_ore}.png")
    message = await channel.send(file=file, content="Guess the ore!", view=view)
    # Assign spawned message reference to buttons
    for item in view.children:
        item.spawned_message = message

# -----------------------------
# SPAWN LOOP
# -----------------------------
@tasks.loop(seconds=SPAWN_INTERVAL)
async def spawn_loop():
    await spawn_ore()

# -----------------------------
# SLASH COMMANDS
# -----------------------------
@tree.command(name="bananas", description="Check your banana balance")
async def bananas(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    count = bananas_db.get(user_id, 0)
    await interaction.response.send_message(f"🍌 You have {count} bananas.")

@tree.command(name="leaderboard", description="Show the top players")
async def leaderboard(interaction: discord.Interaction):
    top = sorted(bananas_db.items(), key=lambda x: x[1], reverse=True)[:10]
    description = ""
    for i, (user_id, count) in enumerate(top, 1):
        user = await bot.fetch_user(int(user_id))
        description += f"{i}. {user.name} - {count} 🍌\n"
    if description == "":
        description = "No bananas yet!"
    await interaction.response.send_message(f"**Leaderboard**\n{description}")

# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    spawn_loop.start()

# -----------------------------
# RUN BOT
# -----------------------------
bot.run(TOKEN)

