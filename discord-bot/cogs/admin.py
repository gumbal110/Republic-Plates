import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
from functools import wraps

import database as db
import config

logger = logging.getLogger(__name__)


def is_admin():
    """Check decorator: el usuario debe tener el rol de administrador configurado."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message(
                "Este comando solo puede usarse en un servidor.", ephemeral=True
            )
            return False
        role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
        if role and role in interaction.user.roles:
            return True
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔒 Acceso Denegado",
                description=(
                    f"Necesitas el rol **{config.ADMIN_ROLE_NAME}** o permisos de administrador."
                ),
                color=config.ERROR_COLOR,
            ),
            ephemeral=True,
        )
        return False

    return app_commands.check(predicate)


class Admin(commands.Cog, name="Administración"):
    """Comandos administrativos del sistema de placas."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    #  /aprobar_solicitud                                                  #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="aprobar_solicitud",
        description="[ADMIN] Aprueba una solicitud de placa y la asigna automáticamente.",
    )
    @app_commands.describe(solicitud_id="ID numérico de la solicitud a aprobar")
    @is_admin()
    async def aprobar_solicitud(
        self, interaction: discord.Interaction, solicitud_id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        request = db.get_request(solicitud_id)
        if not request:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Solicitud No Encontrada",
                    description=f"No existe la solicitud con ID `{solicitud_id}`.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if request["status"] != "pendiente":
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Solicitud Ya Procesada",
                    description=f"Esta solicitud ya tiene el estado: **{request['status']}**.",
                    color=config.WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return

        try:
            plate = db.approve_request(
                request_id=solicitud_id,
                reviewer_id=str(interaction.user.id),
                reviewer_name=str(interaction.user),
            )
        except Exception as e:
            logger.error("Error al aprobar solicitud %d: %s", solicitud_id, e)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Error Interno",
                    description="Ocurrió un error al procesar la aprobación.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="✅ Solicitud Aprobada",
            color=config.SUCCESS_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="ID Solicitud", value=f"`{solicitud_id}`", inline=True)
        embed.add_field(name="Placa Asignada", value=f"**`{plate}`**", inline=True)
        embed.add_field(name="Solicitante", value=request["username"], inline=True)
        embed.add_field(name="Aprobado por", value=str(interaction.user), inline=True)
        embed.set_footer(text="Dirección General de Tránsito · RD")
        await interaction.followup.send(embed=embed, ephemeral=True)

        await self._notify_user(
            guild=interaction.guild,
            user_id=int(request["user_id"]),
            title="✅ Solicitud de Placa Aprobada",
            description=(
                f"Tu solicitud de placa ha sido **aprobada**.\n\n"
                f"🚗 **Placa asignada:** `{plate}`\n"
                f"Guarda este número. Es tu identificación vehicular oficial."
            ),
            color=config.SUCCESS_COLOR,
        )
        await self._send_log(
            guild=interaction.guild,
            title="✅ Placa Aprobada",
            fields={
                "Placa": f"`{plate}`",
                "Solicitante": request["username"],
                "Aprobado por": str(interaction.user),
                "ID Solicitud": f"`{solicitud_id}`",
            },
            color=config.SUCCESS_COLOR,
        )
        logger.info("Solicitud #%d aprobada por %s → placa %s", solicitud_id, interaction.user, plate)

    # ------------------------------------------------------------------ #
    #  /rechazar_solicitud                                                 #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="rechazar_solicitud",
        description="[ADMIN] Rechaza una solicitud de placa con un motivo.",
    )
    @app_commands.describe(
        solicitud_id="ID numérico de la solicitud a rechazar",
        motivo="Motivo del rechazo",
    )
    @is_admin()
    async def rechazar_solicitud(
        self, interaction: discord.Interaction, solicitud_id: int, motivo: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if len(motivo) < 5:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Motivo demasiado corto",
                    description="El motivo de rechazo debe tener al menos 5 caracteres.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        request = db.get_request(solicitud_id)
        if not request:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Solicitud No Encontrada",
                    description=f"No existe la solicitud con ID `{solicitud_id}`.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        if request["status"] != "pendiente":
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Solicitud Ya Procesada",
                    description=f"Esta solicitud ya tiene el estado: **{request['status']}**.",
                    color=config.WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return

        try:
            db.reject_request(
                request_id=solicitud_id,
                reviewer_id=str(interaction.user.id),
                reviewer_name=str(interaction.user),
                reason=motivo,
            )
        except Exception as e:
            logger.error("Error al rechazar solicitud %d: %s", solicitud_id, e)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Error Interno",
                    description="Ocurrió un error al procesar el rechazo.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="❌ Solicitud Rechazada",
            color=config.ERROR_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="ID Solicitud", value=f"`{solicitud_id}`", inline=True)
        embed.add_field(name="Solicitante", value=request["username"], inline=True)
        embed.add_field(name="Rechazado por", value=str(interaction.user), inline=True)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        embed.set_footer(text="Dirección General de Tránsito · RD")
        await interaction.followup.send(embed=embed, ephemeral=True)

        await self._notify_user(
            guild=interaction.guild,
            user_id=int(request["user_id"]),
            title="❌ Solicitud de Placa Rechazada",
            description=(
                f"Tu solicitud de placa ha sido **rechazada**.\n\n"
                f"📋 **Motivo:** {motivo}\n\n"
                "Puedes enviar una nueva solicitud corregida cuando estés listo."
            ),
            color=config.ERROR_COLOR,
        )
        await self._send_log(
            guild=interaction.guild,
            title="❌ Placa Rechazada",
            fields={
                "Solicitante": request["username"],
                "Rechazado por": str(interaction.user),
                "Motivo": motivo,
                "ID Solicitud": f"`{solicitud_id}`",
            },
            color=config.ERROR_COLOR,
        )
        logger.info("Solicitud #%d rechazada por %s", solicitud_id, interaction.user)

    # ------------------------------------------------------------------ #
    #  /ver_solicitudes                                                    #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="ver_solicitudes",
        description="[ADMIN] Lista todas las solicitudes de placa pendientes.",
    )
    @is_admin()
    async def ver_solicitudes(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        pending = db.get_pending_requests()

        embed = discord.Embed(
            title="📋 Solicitudes Pendientes",
            color=config.WARNING_COLOR,
            timestamp=datetime.utcnow(),
        )

        if not pending:
            embed.description = "No hay solicitudes pendientes en este momento. ✅"
        else:
            lines = []
            for r in pending:
                created = r["created_at"][:10]
                motivo_short = r["reason"][:60] + ("..." if len(r["reason"]) > 60 else "")
                lines.append(
                    f"**ID `{r['id']}`** — {r['username']} ({created})\n"
                    f"*{motivo_short}*"
                )
            embed.description = "\n\n".join(lines[:15])
            if len(pending) > 15:
                embed.set_footer(text=f"Mostrando 15 de {len(pending)} solicitudes.")
            else:
                embed.set_footer(text=f"Total: {len(pending)} solicitud(es) pendiente(s).")

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    #  /revocar_placa                                                      #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="revocar_placa",
        description="[ADMIN] Revoca una placa vehicular activa.",
    )
    @app_commands.describe(placa="Número de placa a revocar (ej: RD-1234)")
    @is_admin()
    async def revocar_placa(
        self, interaction: discord.Interaction, placa: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            row = db.revoke_plate(
                plate=placa.upper(),
                revoker_id=str(interaction.user.id),
                revoker_name=str(interaction.user),
            )
        except ValueError as e:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Error",
                    description=str(e),
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return
        except Exception as e:
            logger.error("Error al revocar placa %s: %s", placa, e)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Error Interno",
                    description="Ocurrió un error al revocar la placa.",
                    color=config.ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔒 Placa Revocada",
            color=config.ERROR_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Placa", value=f"`{placa.upper()}`", inline=True)
        embed.add_field(name="Propietario", value=row["username"], inline=True)
        embed.add_field(name="Revocado por", value=str(interaction.user), inline=True)
        embed.set_footer(text="Dirección General de Tránsito · RD")
        await interaction.followup.send(embed=embed, ephemeral=True)

        await self._notify_user(
            guild=interaction.guild,
            user_id=int(row["user_id"]),
            title="🔒 Tu Placa Ha Sido Revocada",
            description=(
                f"La placa **`{placa.upper()}`** registrada a tu nombre ha sido **revocada** "
                f"por un administrador.\n\nContacta a las autoridades para más información."
            ),
            color=config.ERROR_COLOR,
        )
        await self._send_log(
            guild=interaction.guild,
            title="🔒 Placa Revocada",
            fields={
                "Placa": f"`{placa.upper()}`",
                "Propietario": row["username"],
                "Revocado por": str(interaction.user),
            },
            color=config.ERROR_COLOR,
        )
        logger.info("Placa %s revocada por %s", placa.upper(), interaction.user)

    # ------------------------------------------------------------------ #
    #  /buscar_placa                                                       #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="buscar_placa",
        description="[ADMIN] Busca información completa de una placa.",
    )
    @app_commands.describe(placa="Número de placa a buscar (ej: RD-1234)")
    @is_admin()
    async def buscar_placa(
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
            title=f"🔍 Detalles de Placa `{row['plate']}`",
            color=config.ERROR_COLOR if row["revoked"] else config.SUCCESS_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Propietario", value=row["username"], inline=True)
        embed.add_field(name="User ID", value=f"`{row['user_id']}`", inline=True)
        embed.add_field(name="Estado", value=status, inline=True)
        embed.add_field(name="Fecha de Emisión", value=row["issued_at"][:19], inline=True)
        embed.add_field(name="ID Solicitud", value=f"`{row['request_id']}`", inline=True)
        if row["revoked"]:
            embed.add_field(name="Fecha Revocación", value=(row["revoked_at"] or "N/A")[:19], inline=True)
            embed.add_field(name="Revocado por ID", value=f"`{row['revoked_by'] or 'N/A'}`", inline=True)
        embed.set_footer(text="Dirección General de Tránsito · RD")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    #  /estadisticas                                                       #
    # ------------------------------------------------------------------ #
    @app_commands.command(
        name="estadisticas",
        description="[ADMIN] Muestra estadísticas del sistema de placas.",
    )
    @is_admin()
    async def estadisticas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        stats = db.get_stats()

        embed = discord.Embed(
            title="📊 Estadísticas del Sistema",
            color=config.BOT_COLOR,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="🚗 Placas Activas", value=str(stats["total_plates"]), inline=True)
        embed.add_field(name="📋 Total Solicitudes", value=str(stats["total_requests"]), inline=True)
        embed.add_field(name="⏳ Pendientes", value=str(stats["pending"]), inline=True)
        embed.add_field(name="✅ Aprobadas", value=str(stats["approved"]), inline=True)
        embed.add_field(name="❌ Rechazadas", value=str(stats["rejected"]), inline=True)
        embed.set_footer(text="Dirección General de Tránsito · RD")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    async def _notify_user(
        self,
        guild: discord.Guild,
        user_id: int,
        title: str,
        description: str,
        color: int,
    ) -> None:
        try:
            member = guild.get_member(user_id) if guild else None
            if not member:
                return
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=datetime.utcnow(),
            )
            embed.set_footer(text="Dirección General de Tránsito · República Dominicana")
            await member.send(embed=embed)
        except discord.Forbidden:
            logger.debug("No se pudo enviar DM al usuario %d (DMs cerrados).", user_id)
        except Exception as e:
            logger.warning("Error enviando DM al usuario %d: %s", user_id, e)

    async def _send_log(
        self,
        guild: discord.Guild,
        title: str,
        fields: dict[str, str],
        color: int,
    ) -> None:
        channel_id = config.LOG_CHANNEL_ID
        if not channel_id or not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        embed = discord.Embed(title=f"📋 {title}", color=color, timestamp=datetime.utcnow())
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
        embed.set_footer(text="Log del Sistema · DGT RD")
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Sin permisos para enviar al canal de logs.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
