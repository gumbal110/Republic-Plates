"""
Comandos de actividad:
  /actividad registrar — Registra actividad con descripción + 4 imágenes, pendiente de revisión
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from cogs.views import member_has_action

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Activity Review View (persistent)                                   #
# ------------------------------------------------------------------ #

class ActivityReviewView(discord.ui.View):
    def __init__(self, activity_id: int, requester_id: str) -> None:
        super().__init__(timeout=None)
        self.activity_id = activity_id
        self.requester_id = requester_id
        self.aceptar_btn.custom_id = f"actividad_aceptar:{activity_id}"
        self.negar_btn.custom_id = f"actividad_negar:{activity_id}"

    @discord.ui.button(
        label="🟢  Aceptar",
        style=discord.ButtonStyle.success,
        custom_id="actividad_aceptar:0",
    )
    async def aceptar_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._review(interaction, approved=True)

    @discord.ui.button(
        label="🔴  Negar",
        style=discord.ButtonStyle.danger,
        custom_id="actividad_negar:0",
    )
    async def negar_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._review(interaction, approved=False)

    async def _review(self, interaction: discord.Interaction, approved: bool) -> None:
        if not member_has_action(interaction.user, "revisar_actividad"):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔒 Sin Permiso",
                    description=(
                        "No tienes el rol necesario para revisar actividades.\n"
                        "Configura los roles con `/config`."
                    ),
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        if str(interaction.user.id) == self.requester_id:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⛔ Acción No Permitida",
                    description="No puedes revisar tu propia actividad.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        activity = db.get_activity(self.activity_id)
        if not activity or activity["status"] != "pendiente":
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⚠️ Ya Revisada",
                    description="Esta actividad ya fue revisada anteriormente.",
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        status = "aprobada" if approved else "rechazada"
        db.update_activity_status(
            self.activity_id, status,
            str(interaction.user), str(interaction.user.id)
        )

        for item in self.children:
            item.disabled = True

        if approved:
            new_title = "✅ Actividad Aprobada"
            new_color = config.COLOR_GREEN
        else:
            new_title = "❌ Actividad Rechazada"
            new_color = config.COLOR_RED

        embeds = list(interaction.message.embeds)
        if embeds:
            updated = embeds[0].copy()
            updated.title = new_title
            updated.colour = discord.Colour(new_color)
            updated.set_footer(
                text=f"Revisado por {interaction.user}  ·  Policía Nacional · Registro de Actividades"
            )
            embeds[0] = updated

        await interaction.response.edit_message(embeds=embeds, view=self)
        logger.info(
            "Actividad #%d %s por %s",
            self.activity_id, status, interaction.user
        )


# ------------------------------------------------------------------ #
#  Cog                                                                 #
# ------------------------------------------------------------------ #

class Actividad(commands.Cog, name="Actividad"):
    actividad = app_commands.Group(
        name="actividad", description="Registro de actividades de la Policía Nacional."
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._register_persistent_views()

    def _register_persistent_views(self) -> None:
        pending = db.get_pending_activities()
        for act in pending:
            view = ActivityReviewView(act["id"], act["user_id"])
            self.bot.add_view(view)
        if pending:
            logger.info("Re-registradas %d vistas de revisión de actividad.", len(pending))

    # ---------------------------------------------------------------- #
    #  /actividad registrar                                             #
    # ---------------------------------------------------------------- #

    @actividad.command(
        name="registrar",
        description="Registra una actividad oficial con descripción y 4 imágenes obligatorias.",
    )
    @app_commands.describe(
        descripcion="Descripción de la actividad realizada",
        imagen1="Primera imagen (obligatoria)",
        imagen2="Segunda imagen (obligatoria)",
        imagen3="Tercera imagen (obligatoria)",
        imagen4="Cuarta imagen (obligatoria)",
    )
    async def actividad_registrar(
        self,
        interaction: discord.Interaction,
        descripcion: str,
        imagen1: discord.Attachment,
        imagen2: discord.Attachment,
        imagen3: discord.Attachment,
        imagen4: discord.Attachment,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Role permission check
        if not member_has_action(interaction.user, "actividad"):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="🔒 Sin Permiso",
                    description="No tienes el rol necesario para registrar actividades.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        # Must have a badge
        badge = db.get_badge_by_user(str(interaction.user.id))
        if not badge:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Sin Placa Asignada",
                    description="Debes tener una placa institucional asignada para registrar actividades.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        # Validate image types
        images = [imagen1, imagen2, imagen3, imagen4]
        for i, img in enumerate(images, start=1):
            if not img.content_type or not img.content_type.startswith("image/"):
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ Archivo Inválido",
                        description=f"El archivo en **imagen{i}** no es una imagen válida.",
                        color=config.COLOR_RED,
                    ),
                    ephemeral=True,
                )
                return

        image_urls = [img.url for img in images]

        # Save to DB as pending
        activity_id = db.create_activity(
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            guild_id=str(interaction.guild.id),
            badge_number=badge["badge_number"],
            description=descripcion,
            image_urls=image_urls,
        )

        now_unix = int(datetime.utcnow().timestamp())

        # Main embed — pending review
        main_embed = discord.Embed(
            title="📋 Registro de Actividad — Pendiente de Revisión",
            color=config.COLOR_GOLD,
            timestamp=datetime.utcnow(),
        )
        main_embed.add_field(name="Oficial", value=interaction.user.mention, inline=True)
        main_embed.add_field(name="Placa", value=f"`{badge['badge_number']}`", inline=True)
        main_embed.add_field(name="ID Registro", value=f"`#{activity_id}`", inline=True)
        main_embed.add_field(name="Hora", value=f"<t:{now_unix}:F>", inline=True)
        main_embed.add_field(name="Actividad", value=descripcion, inline=False)
        main_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        main_embed.set_image(url=image_urls[0])
        main_embed.set_footer(text="Policía Nacional · Registro de Actividades")

        img_embeds = []
        for url in image_urls[1:]:
            e = discord.Embed(color=config.COLOR_GOLD)
            e.set_image(url=url)
            img_embeds.append(e)

        all_embeds = [main_embed] + img_embeds

        # Review buttons — only the reviewer can interact
        view = ActivityReviewView(activity_id=activity_id, requester_id=str(interaction.user.id))
        self.bot.add_view(view)

        # Resolve target channel
        target_channel: discord.abc.Messageable = interaction.channel
        if config.ACTIVITIES_CHANNEL_ID:
            ch = interaction.guild.get_channel(config.ACTIVITIES_CHANNEL_ID)
            if ch:
                target_channel = ch

        try:
            msg = await target_channel.send(embeds=all_embeds, view=view)
            db.update_activity_message(activity_id, str(msg.id), str(msg.channel.id))
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Sin Permisos en el Canal",
                    description="No tengo permisos para enviar mensajes en el canal de actividades.",
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Actividad Enviada a Revisión",
                description=(
                    f"Tu actividad (ID `#{activity_id}`) fue enviada a revisión en {target_channel.mention}.\n"
                    "Serás notificado cuando sea aprobada o negada."
                ),
                color=config.COLOR_GREEN,
            ),
            ephemeral=True,
        )
        logger.info(
            "Actividad #%d enviada a revisión por %s (%s)",
            activity_id, interaction.user, badge["badge_number"],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Actividad(bot))
