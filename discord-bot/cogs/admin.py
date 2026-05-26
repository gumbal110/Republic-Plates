"""
Comandos administrativos:
  /config_roles    — configurar roles con permisos de acción
  /limpiar_placa   — eliminar la placa de un oficial
  /ver_placas      — panel paginado de todas las placas
  /buscar_placa    — buscar placa por número
"""

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from cogs.views import PlacasView, member_has_action

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Config Roles Modal                                                  #
# ------------------------------------------------------------------ #

class ConfigRolesModal(discord.ui.Modal, title="Configuración de Roles — Policía Nacional"):
    aprobar: discord.ui.TextInput = discord.ui.TextInput(
        label="ID Rol: Aprobar placas",
        placeholder="ID numérico del rol (dejar vacío para no cambiar)",
        required=False,
        max_length=25,
    )
    rechazar: discord.ui.TextInput = discord.ui.TextInput(
        label="ID Rol: Rechazar placas",
        placeholder="ID numérico del rol (dejar vacío para no cambiar)",
        required=False,
        max_length=25,
    )
    asignar: discord.ui.TextInput = discord.ui.TextInput(
        label="ID Rol: Asignar placas",
        placeholder="ID numérico del rol (dejar vacío para no cambiar)",
        required=False,
        max_length=25,
    )
    eliminar: discord.ui.TextInput = discord.ui.TextInput(
        label="ID Rol: Eliminar placas",
        placeholder="ID numérico del rol (dejar vacío para no cambiar)",
        required=False,
        max_length=25,
    )
    ver: discord.ui.TextInput = discord.ui.TextInput(
        label="ID Rol: Ver todas las placas",
        placeholder="ID numérico del rol (dejar vacío para no cambiar)",
        required=False,
        max_length=25,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)

        fields = {
            "aprobar": self.aprobar.value.strip(),
            "rechazar": self.rechazar.value.strip(),
            "asignar": self.asignar.value.strip(),
            "eliminar": self.eliminar.value.strip(),
            "ver": self.ver.value.strip(),
        }

        updated = []
        errors = []
        for action, role_id in fields.items():
            if not role_id:
                continue
            if not role_id.isdigit():
                errors.append(f"`{action}`: ID inválido (`{role_id}`)")
                continue
            role = interaction.guild.get_role(int(role_id))
            if not role:
                errors.append(f"`{action}`: Rol con ID `{role_id}` no encontrado en el servidor")
                continue
            db.set_role(guild_id, action, role_id)
            updated.append(f"**{action.capitalize()}** → {role.mention}")

        embed = discord.Embed(
            title="⚙️ Configuración de Roles Actualizada",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        if updated:
            embed.add_field(name="✅ Roles Configurados", value="\n".join(updated), inline=False)
        if errors:
            embed.add_field(name="❌ Errores", value="\n".join(errors), inline=False)
        if not updated and not errors:
            embed.description = "No se realizaron cambios (todos los campos estaban vacíos)."
            embed.color = config.COLOR_GOLD
        else:
            embed.set_footer(text="Policía Nacional · Administración del Sistema")

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info("Roles configurados por %s en guild %s", interaction.user, guild_id)


# ------------------------------------------------------------------ #
#  Cog                                                                 #
# ------------------------------------------------------------------ #

class Admin(commands.Cog, name="Administración"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---------------------------------------------------------------- #
    #  /config_roles                                                    #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="config_roles",
        description="[ADMIN] Configura los roles que pueden gestionar placas.",
    )
    @app_commands.default_permissions(administrator=True)
    async def config_roles(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔒 Acceso Denegado",
                    description="Solo los administradores del servidor pueden usar este comando.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ConfigRolesModal())

    # ---------------------------------------------------------------- #
    #  /limpiar_placa                                                   #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="limpiar_placa",
        description="[ADMIN] Elimina la placa institucional asignada a un oficial.",
    )
    @app_commands.describe(oficial="El oficial al que se le removerá la placa")
    async def limpiar_placa(
        self, interaction: discord.Interaction, oficial: discord.Member
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not member_has_action(interaction.user, "eliminar"):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="🔒 Acceso Denegado",
                    description="No tienes el rol necesario para eliminar placas.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        removed = db.remove_badge(
            user_id=str(oficial.id),
            removed_by=str(interaction.user.id),
            removed_by_name=str(interaction.user),
        )

        if not removed:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Sin Placa Asignada",
                    description=f"{oficial.mention} no tiene ninguna placa registrada.",
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🗑️ Placa Eliminada del Registro",
            color=config.COLOR_RED,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Placa", value=f"`{removed['badge_number']}`", inline=True)
        embed.add_field(name="Oficial", value=oficial.mention, inline=True)
        embed.add_field(name="Eliminado por", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Policía Nacional · Registro Institucional")
        await interaction.followup.send(embed=embed, ephemeral=True)

        # DM the officer
        try:
            dm_embed = discord.Embed(
                title="🔒 Placa Revocada",
                description=(
                    f"Tu placa institucional **{removed['badge_number']}** ha sido "
                    "eliminada del registro por un superior.\n"
                    "Contacta a la Dirección de Recursos Humanos para más información."
                ),
                color=config.COLOR_RED,
                timestamp=datetime.utcnow(),
            )
            dm_embed.set_footer(text="Policía Nacional · República Dominicana")
            await oficial.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        logger.info("Placa %s eliminada de %s por %s", removed["badge_number"], oficial, interaction.user)

    # ---------------------------------------------------------------- #
    #  /ver_placas                                                      #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="ver_placas",
        description="[ADMIN] Muestra el registro paginado de todas las placas activas.",
    )
    async def ver_placas(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not member_has_action(interaction.user, "ver"):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="🔒 Acceso Denegado",
                    description="No tienes el rol necesario para ver el registro completo.",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        badges = db.get_all_badges()
        view = PlacasView(badges)
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    # ---------------------------------------------------------------- #
    #  /buscar_placa                                                    #
    # ---------------------------------------------------------------- #
    @app_commands.command(
        name="buscar_placa",
        description="[ADMIN] Busca información de una placa por su número.",
    )
    @app_commands.describe(numero="Número de placa a buscar (ej: PN-025)")
    async def buscar_placa(
        self, interaction: discord.Interaction, numero: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        badge = db.get_badge_by_number(numero.strip().upper())

        if not badge:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Placa No Encontrada",
                    description=(
                        f"La placa **`{numero.upper()}`** no existe en el registro institucional.\n"
                        "Verifica el número e inténtalo nuevamente."
                    ),
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🔍 Información de Placa `{badge['badge_number']}`",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Número de Placa", value=f"`{badge['badge_number']}`", inline=True)
        embed.add_field(name="Oficial Asignado", value=f"<@{badge['user_id']}>", inline=True)
        embed.add_field(name="Usuario", value=badge["username"], inline=True)
        embed.add_field(name="Estado", value="✅ Activa", inline=True)
        embed.add_field(name="Asignada por", value=badge["assigned_by"], inline=True)
        embed.add_field(
            name="Fecha de Emisión",
            value=badge["assigned_at"][:10],
            inline=True,
        )
        embed.set_footer(text="Policía Nacional · Dirección de Recursos Humanos")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
