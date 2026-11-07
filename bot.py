import os
import sqlite3
from datetime import datetime, timezone

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
    joined_at TEXT NOT NULL
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS cooldowns (
    discord_id INTEGER PRIMARY KEY,
    joined_at TEXT NOT NULL
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS panel (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL
)
""")

db.commit()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

view_registered = False


def queue_rows():
    return db.execute(
        "SELECT discord_id, trainer_name, joined_at "
        "FROM queue ORDER BY joined_at, discord_id"
    ).fetchall()


def build_queue_embed():
    rows = queue_rows()

    if rows:
        lines = []

        for number, (discord_id, trainer_name, joined_at) in enumerate(
            rows[:50], start=1
        ):
            joined_time = datetime.strptime(
                joined_at, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            timestamp = int(joined_time.timestamp())

            lines.append(
                f"**{number}.** <@{discord_id}> — "
                f"`{discord.utils.escape_markdown(trainer_name)}`\n"
                f"🕒 Joined: <t:{timestamp}:f> "
                f"(<t:{timestamp}:R>)"
            )

        if len(rows) > 50:
            lines.append(f"...and {len(rows) - 50} more players.")

        description = "\n\n".join(lines)
    else:
        description = "The queue is currently empty. Be the first to join!"

    embed = discord.Embed(
        title="Pokemon GO Raid Queue",
        description=description,
        color=discord.Color.green(),
    )

    embed.add_field(
        name="Players in Queue",
        value=str(len(rows)),
        inline=True,
    )

    embed.set_footer(text="JOIN QUEUE | LEAVE QUEUE")
    return embed


async def refresh_queue_panel():
    saved = db.execute(
        "SELECT channel_id, message_id FROM panel WHERE id = 1"
    ).fetchone()

    if not saved:
        return

    channel_id, message_id = saved

    try:
        channel = bot.get_channel(channel_id)

        if channel is None:
            channel = await bot.fetch_channel(channel_id)

        message = await channel.fetch_message(message_id)

        await message.edit(
            embed=build_queue_embed(),
            view=QueuePanel(),
        )

    except discord.NotFound:
        print("Queue panel was deleted. Run /setup_panel again.")

    except discord.HTTPException as error:
        print("Could not update queue panel:", error)


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
                "Please enter a valid Trainer Name.",
                ephemeral=True,
            )
            return

        user_id = interaction.user.id

        existing = db.execute(
            "SELECT trainer_name FROM queue WHERE discord_id = ?",
            (user_id,),
        ).fetchone()

        if existing:
            await interaction.response.send_message(
                f"You are already in the queue as **{existing[0]}**.",
                ephemeral=True,
            )
            return

        cooldown = db.execute(
            "SELECT joined_at FROM cooldowns WHERE discord_id = ?",
            (user_id,),
        ).fetchone()

        now = datetime.now(timezone.utc)

        if cooldown:
            previous_time = datetime.strptime(
                cooldown[0], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            elapsed = (now - previous_time).total_seconds()
            remaining = 300 - elapsed

            if remaining > 0:
                available_time = int(previous_time.timestamp()) + 300

                await interaction.response.send_message(
                    "You must wait before joining again.\n"
                    f"You can join <t:{available_time}:R>.",
                    ephemeral=True,
                )
                return

        joined_at = now.strftime("%Y-%m-%d %H:%M:%S")

        db.execute(
            "INSERT INTO queue(discord_id, trainer_name, joined_at) "
            "VALUES(?, ?, ?)",
            (user_id, name, joined_at),
        )

        db.execute(
            "INSERT OR REPLACE INTO cooldowns(discord_id, joined_at) "
            "VALUES(?, ?)",
            (user_id, joined_at),
        )

        db.commit()

        position = len(queue_rows())

        await interaction.response.send_message(
            f"You joined as **{name}**. "
            f"Your position is **#{position}**.",
            ephemeral=True,
        )

        await refresh_queue_panel()


class QueuePanel(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="JOIN QUEUE",
        style=discord.ButtonStyle.success,
        custom_id="raidqueue:join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(TrainerNameModal())

    @discord.ui.button(
        label="LEAVE QUEUE",
        style=discord.ButtonStyle.secondary,
        custom_id="raidqueue:leave",
    )
    async def leave(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        cursor = db.execute(
            "DELETE FROM queue WHERE discord_id = ?",
            (interaction.user.id,),
        )
        db.commit()

        if cursor.rowcount:
            message = "You have left the queue."
        else:
            message = "You are not currently in the queue."

        await interaction.response.send_message(
            message,
            ephemeral=True,
        )

        if cursor.rowcount:
            await refresh_queue_panel()


@bot.event
async def on_ready():
    global view_registered

    if not view_registered:
        bot.add_view(QueuePanel())
        view_registered = True

    try:
        await bot.tree.sync()
    except discord.HTTPException as error:
        print("Command sync failed:", error)

    print("Logged in as", bot.user)


@bot.tree.command(
    name="setup_panel",
    description="Create or update the raid queue panel.",
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_panel(interaction: discord.Interaction):

    saved = db.execute(
        "SELECT channel_id, message_id FROM panel WHERE id = 1"
    ).fetchone()

    if saved:
        channel_id, message_id = saved

        try:
            channel = bot.get_channel(channel_id)

            if channel is None:
                channel = await bot.fetch_channel(channel_id)

            message = await channel.fetch_message(message_id)

            await message.edit(
                embed=build_queue_embed(),
                view=QueuePanel(),
            )

            await interaction.response.send_message(
                "The original raid queue panel has been updated.",
                ephemeral=True,
            )
            return

        except discord.NotFound:
            print("Old panel not found. Creating a new one.")

    await interaction.response.send_message(
        embed=build_queue_embed(),
        view=QueuePanel(),
    )

    message = await interaction.original_response()

    db.execute(
        "INSERT OR REPLACE INTO panel(id, channel_id, message_id) "
        "VALUES(1, ?, ?)",
        (message.channel.id, message.id),
    )
    db.commit()


@bot.tree.command(
    name="queue",
    description="Show the global waiting list.",
)
@app_commands.checks.has_permissions(administrator=True)
async def show_queue(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=build_queue_embed(),
        ephemeral=True,
    )


@bot.tree.command(
    name="remove",
    description="Remove a member from the queue.",
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="The Discord member to remove.")
async def remove_player(
    interaction: discord.Interaction,
    member: discord.Member,
):
    cursor = db.execute(
        "DELETE FROM queue WHERE discord_id = ?",
        (member.id,),
    )
    db.commit()

    if cursor.rowcount:
        response = f"Removed {member.mention} from the queue."
        await refresh_queue_panel()
    else:
        response = f"{member.mention} is not in the queue."

    await interaction.response.send_message(
        response,
        ephemeral=True,
    )


@bot.tree.command(
    name="reset_queue",
    description="Clear the entire global queue.",
)
@app_commands.checks.has_permissions(administrator=True)
async def reset_queue(interaction: discord.Interaction):
    db.execute("DELETE FROM queue")
    db.commit()

    await refresh_queue_panel()

    await interaction.response.send_message(
        "The global raid queue has been cleared.",
        ephemeral=True,
    )


@bot.tree.error
async def command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You do not have permission to use this command."
    else:
        print("Application command error:", error)
        message = "Something went wrong while running that command."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True,
        )


bot.run(TOKEN)
