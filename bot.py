import os
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Set the DISCORD_BOT_TOKEN environment variable.")

db = sqlite3.connect(os.getenv("DATABASE_PATH", "raid_queue.db"))
db.execute("""
CREATE TABLE IF NOT EXISTS queue (
    discord_id INTEGER PRIMARY KEY,
    trainer_name TEXT NOT NULL,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
""")
db.commit()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def queue_rows():
    return db.execute(
        "SELECT discord_id, trainer_name FROM queue ORDER BY joined_at, discord_id"
    ).fetchall()


class TrainerNameModal(discord.ui.Modal, title="Join the Raid Queue"):
    trainer_name = discord.ui.TextInput(
        label="Pokemon GO Trainer Name",
        placeholder="Enter your in-game trainer name",
        min_length=1,
        max_length=24,
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = str(self.trainer_name).strip()
        if not name:
            await interaction.response.send_message(
                "Please enter a valid Trainer Name.", ephemeral=True
            )
            return

        existing = db.execute(
            "SELECT trainer_name FROM queue WHERE discord_id = ?",
            (interaction.user.id,),
        ).fetchone()
        if existing:
            await interaction.response.send_message(
                "You are already in the queue as **" + existing[0] + "**. "
                "Use **LEAVE QUEUE** before joining again.",
                ephemeral=True,
            )
            return

        db.execute(
            "INSERT INTO queue(discord_id, trainer_name) VALUES(?, ?)",
            (interaction.user.id, name),
        )
        db.commit()
        position = len(queue_rows())
        await interaction.response.send_message(
            "You joined as **" + name + "**. Your current position is **#" +
            str(position) + "**.",
            ephemeral=True,
        )


class QueuePanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="JOIN QUEUE",
        style=discord.ButtonStyle.success,
        custom_id="raidqueue:join",
    )
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TrainerNameModal())

    @discord.ui.button(
        label="LEAVE QUEUE",
        style=discord.ButtonStyle.secondary,
        custom_id="raidqueue:leave",
    )
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor = db.execute(
            "DELETE FROM queue WHERE discord_id = ?", (interaction.user.id,)
        )
        db.commit()
        message = (
            "You have left the queue."
            if cursor.rowcount
            else "You are not currently in the queue."
        )
        await interaction.response.send_message(message, ephemeral=True)


@bot.event
async def on_ready():
    bot.add_view(QueuePanel())
    try:
        await bot.tree.sync()
    except discord.HTTPException as error:
        print("Command sync failed:", error)
    print("Logged in as", bot.user)


@bot.tree.command(
    name="setup_panel",
    description="Post the permanent raid queue panel in this channel.",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Pokemon GO Raid Queue",
        description=(
            "Press **JOIN QUEUE** and enter your Pokemon GO Trainer Name "
            "to join the global waiting list.\n\n"
            "Press **LEAVE QUEUE** if you no longer want to wait."
        ),
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed=embed, view=QueuePanel())


@bot.tree.command(name="queue", description="Show the global waiting list.")
@app_commands.checks.has_permissions(manage_guild=True)
async def show_queue(interaction: discord.Interaction):
    rows = queue_rows()
    if not rows:
        await interaction.response.send_message(
            "The queue is currently empty.", ephemeral=True
        )
        return
    lines = []
    for number, (discord_id, trainer_name) in enumerate(rows, start=1):
        lines.append(
            "**" + str(number) + ".** <@" + str(discord_id) + "> — `" +
            trainer_name + "`"
        )
    embed = discord.Embed(
        title="Global Raid Queue (" + str(len(rows)) + " players)",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="remove", description="Remove a member from the queue.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(member="The Discord member to remove.")
async def remove_player(interaction: discord.Interaction, member: discord.Member):
    cursor = db.execute(
        "DELETE FROM queue WHERE discord_id = ?", (member.id,)
    )
    db.commit()
    response = (
        "Removed " + member.mention + " from the queue."
        if cursor.rowcount
        else member.mention + " is not in the queue."
    )
    await interaction.response.send_message(response, ephemeral=True)


@bot.tree.command(name="reset_queue", description="Clear the entire global queue.")
@app_commands.checks.has_permissions(administrator=True)
async def reset_queue(interaction: discord.Interaction):
    db.execute("DELETE FROM queue")
    db.commit()
    await interaction.response.send_message(
        "The global raid queue has been cleared.", ephemeral=True
    )


@bot.tree.error
async def command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You do not have permission to use this command."
    else:
        print("Application command error:", error)
        message = "Something went wrong while running that command."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


bot.run(TOKEN)
