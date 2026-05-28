"""
Comandos para ciudadanos/oficiales:
  /solicitar_placa — envía una solicitud de placa al canal de revisión
"""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from cogs.views import SolicitudView

logger = logging.getLogger(__name__)


class Placas(commands.Cog, name="Placas"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="solicitar_placa",
        description="Envía una solicitud oficial de asignación de placa a la Policía Nacional.",
    )
    async def solicitar_placa(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        # Prevent duplicate pending requests
        if db.has_pending_request(str(interaction.user.id), str(interaction.guild.id)):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Solicitud Pendiente",
                    description=(
                        "Ya tienes una solicitud en proceso de revisión.\n"
                        "Por favor espera a que sea atendida antes de enviar otra."
                    ),
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        # Prevent request if officer already has a badge
        if db.user_has_badge(str(interaction.user.id)):
            badge = db.get_badge_by_user(str(interaction.user.id))
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Ya Posees una Placa",
                    description=(
                        f"Ya tienes la placa institucional **{badge['badge_number']}** asignada.\n"
                        "Contacta a un superior si necesitas realizar cambios."
                    ),
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        request_id = db.create_request(
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            guild_id=str(interaction.guild.id),
        )

        # Build review embed
        review_embed = discord.Embed(
            title="📋 Nueva Solicitud de Placa Institucional",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        review_embed.add_field(name="Oficial", value=interaction.user.mention, inline=True)
        review_embed.add_field(name="ID de Usuario", value=f"`{interaction.user.id}`", inline=True)
        review_embed.add_field(name="ID de Solicitud", value=f"`{request_id}`", inline=True)
        review_embed.add_field(
            name="Fecha de Solicitud",
            value=f"<t:{int(datetime.utcnow().timestamp())}:F>",
            inline=False,
        )
        review_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        review_embed.set_footer(text="Policía Nacional · Dirección de Recursos Humanos")

        view = SolicitudView(request_id=request_id, requester_id=str(interaction.user.id))

        # Post to configured review channel
        review_channel = None
        configured_channel_id = db.get_channel_solicitudes(str(interaction.guild.id))
        if configured_channel_id:
            review_channel = interaction.guild.get_channel(int(configured_channel_id))
        elif config.REVIEW_CHANNEL_ID:
            review_channel = interaction.guild.get_channel(config.REVIEW_CHANNEL_ID)

        if review_channel:
            try:
                msg = await review_channel.send(embed=review_embed, view=view)
                db.update_request_message(request_id, str(msg.id), str(msg.channel.id))
            except discord.Forbidden:
                logger.warning("Sin permisos en el canal de revisión.")
        else:
            # Fallback: post in current channel if review channel not configured
            msg = await interaction.channel.send(embed=review_embed, view=view)
            db.update_request_message(request_id, str(msg.id), str(msg.channel.id))

        # Confirm to requester
        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Solicitud Enviada",
                description=(
                    "Tu solicitud de placa ha sido enviada al área de revisión.\n"
                    "Serás notificado por mensaje directo cuando sea procesada."
                ),
                color=config.COLOR_GREEN,
            ),
            ephemeral=True,
        )
        logger.info("Solicitud #%d creada por %s", request_id, interaction.user)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Placas(bot))
