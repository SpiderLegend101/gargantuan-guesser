# Gargantuan Guesser Discord Bot

## Overview
A Discord bot game where users guess ore types from images. Players earn "bananas" as currency for correct guesses and build streaks.

## Project Structure
- `main.py` - Main bot code with slash commands and game logic
- `ores/` - Directory containing ore images (.webp files)
- `db.json` - User database (bananas, streaks)
- `servers.json` - Server configuration (spawn channels)
- `requirements.txt` - Python dependencies

## Tech Stack
- Python 3.11
- discord.py library

## Setup Requirements
- `DISCORD_TOKEN` secret is required to run the bot

## Commands
- `/gargantuan setup` - Select spawn channel (admin only)
- `/gargantuan spawn` - Manually spawn an ore (admin only)
- `/gargantuan balance` - View your balance
- `/gargantuan leaderboard` - View top players
- `/gargantuan profile` - View your or another player's profile

## Running
The bot runs via the "Discord Bot" workflow with `python main.py`
