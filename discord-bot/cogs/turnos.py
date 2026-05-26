"""
Comandos de turnos:
  /turno iniciar  — Inicia turno con panel de temporizador (botones Pausar / Finalizar)
  /turno ver      — Panel de todos los turnos activos en el servidor
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database as db

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _elapsed_str(shift: db.sqlite3.Row) -> str:
    seconds = db.elapsed_seconds(shift)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _start_unix(shift: db.sqlite3.Row) -> int:
    return int(datetime.fromisoformat(shift["start_time"]).replace(
        tzinfo=timezone.utc).timestamp())


def build_shift_embed(shift: db.sqlite3.Row, *, final: bool = False) -> discord.Embed:
    if shift["status"] == "pausado":
        title = "⏸️ Turno en Pausa — Policía Nacional RD"
        color = config.COLOR_GOLD
        status_label = "⏸️ Pausado"
    elif final or shift["status"] == "finalizado":
        title = "✅ Turno Finalizado — Policía Nacional RD"
        color = config.COLOR_GREY
        status_label = "🔴 Fuera de Servicio"
    else:
        title = "🚓 Turno en Servicio — Policía Nacional RD"
        color = config.COLOR_GREEN
        status_label = "🟢 En Servicio"

    embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
    embed.add_field(name="Oficial", value=f"<@{shift['user_id']}>", inline=True)
    embed.add_field(name="Placa", value=f"`{shift['badge_number']}`", inline=True)
    embed.add_field(name="Estado", value=status_label, inline=True)
    embed.add_field(
        name="Hora de Inicio",
        value=f"<t:{_start_unix(shift)}:F>",
        inline=True,
    )
    embed.add_field(name="Tiempo en Servicio", value=_elapsed_str(shift), inline=True)

    if (final or shift["status"] == "finalizado") and shift["end_time"]:
        end_unix = int(
            datetime.fromisoformat(shift["end_time"])
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        embed.add_field(name="Hora de Cierre", value=f"<t:{end_unix}:F>", inline=True)

    embed.set_footer(text="Policía Nacional · Control de Turnos  ·  Actualizado")
    return embed


# ------------------------------------------------------------------ #
#  Persistent View                                                     #
# ------------------------------------------------------------------ #

class TurnoView(discord.ui.View):
    def __init__(self, shift_id: int, user_id: str) -> None:
        super().__init__(timeout=None)
        self.shift_id = shift_id
        self.user_id = user_id
        self.pausar_btn.custom_id = f"turno_pausar:{shift_id}"
        self.finalizar_btn.custom_id = f"turno_finalizar:{shift_id}"

    # ---------------------------------------------------------------- #

    @discord.ui.button(
        label="⏸️  Pausar",
        style=discord.ButtonStyle.secondary,
        custom_id="turno_pausar:0",
    )
    async def pausar_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔒 Sin Permiso",
                    description="Solo el oficial que inició el turno puede controlarlo.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        shift = db.get_shift(self.shift_id)
        if not shift or shift["status"] == "finalizado":
            await interaction.response.send_message(
                "Este turno ya fue finalizado.", ephemeral=True
            )
            return

        if shift["status"] == "pausado":
            db.resume_shift(self.shift_id)
            shift = db.get_shift(self.shift_id)
            button.label = "⏸️  Pausar"
            button.style = discord.ButtonStyle.secondary
        else:
            db.pause_shift(self.shift_id)
            shift = db.get_shift(self.shift_id)
            button.label = "▶️  Reanudar"
            button.style = discord.ButtonStyle.success

        await interaction.response.edit_message(
            embed=build_shift_embed(shift), view=self
        )

    # ---------------------------------------------------------------- #

    @discord.ui.button(
        label="🛑  Finalizar",
        style=discord.ButtonStyle.danger,
        custom_id="turno_finalizar:0",
    )
    async def finalizar_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔒 Sin Permiso",
                    description="Solo el oficial que inició el turno puede controlarlo.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        shift = db.get_shift(self.shift_id)
        if not shift or shift["status"] == "finalizado":
            await interaction.response.send_message(
                "Este turno ya fue finalizado.", ephemeral=True
            )
            return

        ended = db.end_shift(self.shift_id)
        if not ended:
            await interaction.response.send_message(
                "Error al finalizar el turno.", ephemeral=True
            )
            return

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        final_embed = build_shift_embed(ended, final=True)
        await interaction.response.edit_message(embed=final_embed, view=self)
        logger.info(
            "Turno #%d finalizado por %s — duración %s",
            self.shift_id,
            interaction.user,
            _elapsed_str(ended),
        )


# ------------------------------------------------------------------ #
#  Cog                                                                 #
# ------------------------------------------------------------------ #

class Turnos(commands.Cog, name="Turnos"):
    turno = app_commands.Group(name="turno", description="Sistema de turnos de la Policía Nacional.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._register_persistent_views()

    def _register_persistent_views(self) -> None:
        active = db.get_all_active_shifts_globally()
        for shift in active:
            view = TurnoView(shift["id"], shift["user_id"])
            self.bot.add_view(view)
        if active:
            logger.info("Re-registradas %d vistas persistentes de turno.", len(active))

    def cog_load(self) -> None:
        self.update_shift_embeds.start()

    def cog_unload(self) -> None:
        self.update_shift_embeds.cancel()

    # ---------------------------------------------------------------- #
    #  Background task — update all active shift embeds every 30s       #
    # ---------------------------------------------------------------- #

    @tasks.loop(seconds=30)
    async def update_shift_embeds(self) -> None:
        active = db.get_all_active_shifts_globally()
        for shift in active:
            if not shift["message_id"] or not shift["channel_id"]:
                continue
            try:
                guild = self.bot.get_guild(int(shift["guild_id"]))
                if not guild:
                    continue
                channel = guild.get_channel(int(shift["channel_id"]))
                if not channel:
                    continue
                msg = await channel.fetch_message(int(shift["message_id"]))
                await msg.edit(embed=build_shift_embed(shift))
            except discord.NotFound:
                pass
            except Exception as e:
                logger.debug("Error actualizando embed turno #%d: %s", shift["id"], e)

    @update_shift_embeds.before_loop
    async def before_update(self) -> None:
        await self.bot.wait_until_ready()

    # ---------------------------------------------------------------- #
    #  /turno iniciar                                                   #
    # ---------------------------------------------------------------- #

    @turno.command(name="iniciar", description="Inicia tu turno de servicio con temporizador.")
    async def turno_iniciar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        # Must have a badge
        if not db.user_has_badge(str(interaction.user.id)):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Sin Placa Asignada",
                    description="Debes tener una placa institucional asignada para iniciar turno.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        # No duplicate active shifts
        existing = db.get_active_shift(str(interaction.user.id), str(interaction.guild.id))
        if existing:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Turno Ya Activo",
                    description=(
                        "Ya tienes un turno en curso.\n"
                        f"Iniciado: <t:{_start_unix(existing)}:R>"
                    ),
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        badge = db.get_badge_by_user(str(interaction.user.id))
        shift_id = db.create_shift(
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            guild_id=str(interaction.guild.id),
            badge_number=badge["badge_number"],
        )

        shift = db.get_shift(shift_id)
        view = TurnoView(shift_id=shift_id, user_id=str(interaction.user.id))
        self.bot.add_view(view)

        msg = await interaction.channel.send(embed=build_shift_embed(shift), view=view)
        db.update_shift_message(shift_id, str(msg.id), str(msg.channel.id))

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Turno Iniciado",
                description="Tu turno ha comenzado. El panel aparece en este canal.",
                color=config.COLOR_GREEN,
            ),
            ephemeral=True,
        )
        logger.info("Turno #%d iniciado por %s (%s)", shift_id, interaction.user, badge["badge_number"])

    # ---------------------------------------------------------------- #
    #  /turno ver                                                       #
    # ---------------------------------------------------------------- #

    @turno.command(name="ver", description="Muestra todos los oficiales actualmente en turno.")
    async def turno_ver(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        active = db.get_all_active_shifts(str(interaction.guild.id))

        embed = discord.Embed(
            title="🚓 Turnos Activos — Policía Nacional RD",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )

        if not active:
            embed.description = "_No hay oficiales en turno en este momento._"
        else:
            lines = []
            for shift in active:
                status_icon = "⏸️" if shift["status"] == "pausado" else "🟢"
                elapsed = _elapsed_str(shift)
                lines.append(
                    f"{status_icon} **`{shift['badge_number']}`** — <@{shift['user_id']}>\n"
                    f"  ⏱️ `{elapsed}` | Inicio: <t:{_start_unix(shift)}:R>"
                )
            embed.description = "\n\n".join(lines)
            embed.set_footer(text=f"Total en servicio: {len(active)} oficial(es)")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Turnos(bot))
