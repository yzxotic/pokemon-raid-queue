# Pokemon GO Raid Queue Bot

A Discord bot with one global raid waiting list. Players join through a permanent button panel and enter their Pokemon GO Trainer Name in a modal.

## Features
- One shared queue for the server.
- JOIN QUEUE opens a form for the player's in-game Trainer Name.
- Prevents duplicate entries using Discord user IDs.
- LEAVE QUEUE lets a player remove themselves.
- Admin commands to view, remove a player, or clear the queue.
- SQLite stores queue entries between bot restarts.
- Bot messages and commands are in English.

## Run locally
1. Install dependencies: `python -m pip install -r requirements.txt`
2. Set the `DISCORD_BOT_TOKEN` environment variable. Never put the token in this repository.
3. Start the bot: `python bot.py`
4. In Discord, run `/setup_panel` in the channel where the queue panel should appear.

## Commands
- `/setup_panel` — Manage Server permission; posts the queue panel.
- `/queue` — Manage Server permission; shows the global waiting list.
- `/remove @member` — Manage Server permission; removes one player.
- `/reset_queue` — Administrator permission; clears the queue.

Invite the bot with the `bot` and `applications.commands` scopes. Grant it permission to view the target channel, send messages, embed links, and use application commands. The SQLite database must be on persistent storage on the host; ephemeral filesystems can erase the queue after a restart. This repository contains code; it does not host the bot by itself.
