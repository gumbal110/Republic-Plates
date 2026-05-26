"""
Comandos de actividad:
  /actividad registrar — Registra una actividad con descripción y 4 imágenes obligatorias
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db

logger = logging.getLogger(__name__)


class Actividad(commands.Cog, name="Actividad"):
    actividad = app_commands.Group(
        name="actividad", description="Registro de actividades de la Policía Nacional."
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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

        # Must have a badge
        badge = db.get_badge_by_user(str(interaction.user.id))
        if not badge:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Sin Placa Asignada",
                    description=(
                        "Debes tener una placa institucional asignada "
                        "para registrar actividades."
                    ),
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

        # Save to DB
        activity_id = db.create_activity(
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            guild_id=str(interaction.guild.id),
            badge_number=badge["badge_number"],
            description=descripcion,
            image_urls=image_urls,
        )

        now_unix = int(datetime.utcnow().timestamp())

        # Main info embed
        main_embed = discord.Embed(
            title="📋 Registro de Actividad",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        main_embed.add_field(name="Oficial", value=interaction.user.mention, inline=True)
        main_embed.add_field(name="Placa", value=f"`{badge['badge_number']}`", inline=True)
        main_embed.add_field(name="ID Registro", value=f"`#{activity_id}`", inline=True)
        main_embed.add_field(name="Hora", value=f"<t:{now_unix}:F>", inline=True)
        main_embed.add_field(name="Actividad", value=descripcion, inline=False)
        main_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        main_embed.set_footer(text="Policía Nacional · Registro de Actividades")
        main_embed.set_image(url=image_urls[0])

        # Image embeds 2-4 (grouped with main embed in one message)
        img_embeds = []
        for url in image_urls[1:]:
            e = discord.Embed(color=config.COLOR_NAVY)
            e.set_image(url=url)
            img_embeds.append(e)

        all_embeds = [main_embed] + img_embeds

        # Resolve target channel
        target_channel: discord.abc.Messageable = interaction.channel
        if config.ACTIVITIES_CHANNEL_ID:
            ch = interaction.guild.get_channel(config.ACTIVITIES_CHANNEL_ID)
            if ch:
                target_channel = ch

        try:
            await target_channel.send(embeds=all_embeds)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Sin Permisos en el Canal de Actividades",
                    description="No tengo permisos para enviar mensajes en el canal configurado.",
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Actividad Registrada",
                description=(
                    f"Tu actividad ha sido registrada correctamente (ID `#{activity_id}`).\n"
                    f"Publicada en {target_channel.mention}."
                ),
                color=config.COLOR_GREEN,
            ),
            ephemeral=True,
        )
        logger.info(
            "Actividad #%d registrada por %s (%s)",
            activity_id,
            interaction.user,
            badge["badge_number"],
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Actividad(bot))
