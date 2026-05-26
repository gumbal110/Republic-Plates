import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime

import database as db
import config

logger = logging.getLogger(__name__)


class Placas(commands.Cog, name="Placas"):
    """Comandos de placas vehiculares para ciudadanos."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    #  /solicitar_placa                                                    #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="solicitar_placa",
        description="Solicita el registro de una placa vehicular.",
    )
    @app_commands.describe(motivo="Motivo o descripción del vehículo a registrar")
    async def solicitar_placa(
        self, interaction: discord.Interaction, motivo: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if len(motivo) < 10:
            await interaction.followup.send(
                embed=discord.Embed(
                    title=f"{config.ERROR_COLOR and ''}❌ Motivo demasiado corto",
                    description="El motivo debe tener al menos 10 caracteres.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if len(motivo) > 300:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Motivo demasiado largo",
                    description="El motivo no puede superar los 300 caracteres.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        pending = db.get_pending_requests()
        user_pending = [r for r in pending if r["user_id"] == str(interaction.user.id)]
        if user_pending:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⏳ Solicitud ya en proceso",
                    description=(
                        f"Ya tienes una solicitud pendiente (ID: `{user_pending[0]['id']}`).\n"
                        "Espera a que sea revisada antes de enviar otra."
                    ),
                    color=config.WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return

        request_id = db.create_request(
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            reason=motivo,
        )

        embed = discord.Embed(
            title="🚗 Solicitud Enviada",
            description="Tu solicitud de placa ha sido registrada y está en revisión.",
            color=config.SUCCESS_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="ID de Solicitud", value=f"`{request_id}`", inline=True)
        embed.add_field(name="Estado", value="⏳ Pendiente", inline=True)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        embed.set_footer(text="República Dominicana · Registro Vehicular")
        await interaction.followup.send(embed=embed, ephemeral=True)

        await self._notify_approval_channel(interaction, request_id, motivo)
        logger.info(
            "Solicitud #%d creada por %s (%s)",
            request_id,
            interaction.user,
            interaction.user.id,
        )

    async def _notify_approval_channel(
        self,
        interaction: discord.Interaction,
        request_id: int,
        motivo: str,
    ) -> None:
        channel_id = config.APPROVAL_CHANNEL_ID
        if not channel_id:
            return
        channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
        if not channel:
            return

        embed = discord.Embed(
            title="📥 Nueva Solicitud de Placa",
            color=config.INFO_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Solicitante", value=interaction.user.mention, inline=True)
        embed.add_field(name="ID Solicitud", value=f"`{request_id}`", inline=True)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        embed.add_field(
            name="Acciones",
            value=(
                f"`/aprobar_solicitud {request_id}` — Aprobar\n"
                f"`/rechazar_solicitud {request_id} [motivo]` — Rechazar"
            ),
            inline=False,
        )
        embed.set_footer(text="Dirección General de Tránsito · RD")
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Sin permisos para enviar al canal de aprobaciones.")

    # ------------------------------------------------------------------ #
    #  /mis_placas                                                         #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="mis_placas",
        description="Consulta tus placas vehiculares registradas.",
    )
    async def mis_placas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        plates = db.get_user_plates(str(interaction.user.id))

        embed = discord.Embed(
            title="🚗 Mis Placas Registradas",
            color=config.BOT_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.set_author(
            name=str(interaction.user),
            icon_url=interaction.user.display_avatar.url,
        )

        if not plates:
            embed.description = "No tienes placas registradas actualmente."
        else:
            lines = []
            for p in plates:
                issued = p["issued_at"][:10]
                lines.append(f"**`{p['plate']}`** — Emitida el {issued}")
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Total: {len(plates)} placa(s)")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    #  /consultar_placa                                                    #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="consultar_placa",
        description="Consulta la información de una placa vehicular.",
    )
    @app_commands.describe(placa="Número de placa (ej: RD-1234)")
    async def consultar_placa(
        self, interaction: discord.Interaction, placa: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        row = db.lookup_plate(placa.upper())

        if not row:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Placa No Encontrada",
                    description=f"La placa `{placa.upper()}` no existe en el registro.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        status = "🔒 Revocada" if row["revoked"] else "✅ Activa"
        embed = discord.Embed(
            title=f"🔍 Información de Placa `{row['plate']}`",
            color=config.ERROR_COLOR if row["revoked"] else config.SUCCESS_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Propietario", value=row["username"], inline=True)
        embed.add_field(name="Estado", value=status, inline=True)
        embed.add_field(name="Fecha de Emisión", value=row["issued_at"][:10], inline=True)
        if row["revoked"]:
            embed.add_field(name="Fecha de Revocación", value=(row["revoked_at"] or "N/A")[:10], inline=True)
        embed.set_footer(text="Dirección General de Tránsito · RD")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    #  /mis_solicitudes                                                    #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="mis_solicitudes",
        description="Consulta el historial de tus solicitudes de placa.",
    )
    async def mis_solicitudes(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        requests = db.get_user_requests(str(interaction.user.id))

        embed = discord.Embed(
            title="📋 Mis Solicitudes",
            color=config.BOT_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.set_author(
            name=str(interaction.user),
            icon_url=interaction.user.display_avatar.url,
        )

        status_map = {
            "pendiente": "⏳ Pendiente",
            "aprobada": "✅ Aprobada",
            "rechazada": "❌ Rechazada",
        }

        if not requests:
            embed.description = "No tienes solicitudes registradas."
        else:
            lines = []
            for r in requests:
                status_label = status_map.get(r["status"], r["status"])
                plate_info = f" → `{r['plate']}`" if r["plate"] else ""
                lines.append(
                    f"**ID `{r['id']}`** — {status_label}{plate_info}\n"
                    f"*{r['reason'][:60]}{'...' if len(r['reason']) > 60 else ''}*"
                )
            embed.description = "\n\n".join(lines)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Placas(bot))
