"""
/config - Configuracion directa de permisos y canales.

Este comando evita componentes interactivos para que la configuracion funcione
de forma estable en cualquier version soportada de discord.py.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config as cfg
import database as db

logger = logging.getLogger(__name__)

PERMISSIONS: dict[str, str] = {
    "aprobar": "Aceptar solicitudes de placa",
    "rechazar": "Rechazar solicitudes de placa",
    "asignar": "Asignar placas",
    "eliminar": "Limpiar placas",
    "ver": "Ver registro de placas",
}

CHANNELS: dict[str, tuple[str, str]] = {
    "solicitudes": ("channel_solicitudes", "Solicitudes de placa"),
    "aceptadas": ("channel_aceptadas", "Solicitudes aceptadas"),
    "rechazadas": ("channel_rechazadas", "Solicitudes rechazadas"),
    "logs": ("channel_logs", "Logs administrativos"),
}


def _roles_text(guild: discord.Guild, role_ids: list[str]) -> str:
    if not role_ids:
        return "*Sin restriccion: admins o Manage Server*"
    mentions: list[str] = []
    for role_id in role_ids:
        role = guild.get_role(int(role_id)) if role_id.isdigit() else None
        mentions.append(role.mention if role else f"`{role_id}`")
    return " ".join(mentions)


def build_summary_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="Configuracion - Policia Nacional RD",
        description="Estado actual de permisos y canales.",
        color=cfg.COLOR_NAVY,
        timestamp=datetime.utcnow(),
    )

    all_roles = db.get_all_roles_multi(str(guild.id))
    for action, label in PERMISSIONS.items():
        embed.add_field(
            name=label,
            value=_roles_text(guild, all_roles.get(action, [])),
            inline=False,
        )

    guild_config = db.get_guild_config(str(guild.id))
    channel_lines: list[str] = []
    for _, (db_key, label) in CHANNELS.items():
        channel_id = guild_config[db_key] if guild_config and db_key in guild_config.keys() else None
        channel_lines.append(f"**{label}:** {f'<#{channel_id}>' if channel_id else '*No configurado*'}")
    embed.add_field(name="Canales", value="\n".join(channel_lines), inline=False)
    embed.set_footer(text="Usa /config categoria:permiso o categoria:canal para editar.")
    return embed


class Config(commands.Cog, name="Configuracion"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="config",
        description="[ADMIN] Configura permisos por rol y canales del sistema de placas.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        categoria="Que deseas configurar o consultar.",
        permiso="Permiso que quieres editar.",
        rol="Rol que recibira o perdera el permiso.",
        accion="Como editar el permiso seleccionado.",
        canal_tipo="Tipo de canal que quieres configurar.",
        canal="Canal de texto para el tipo seleccionado. Omitelo para limpiar.",
    )
    @app_commands.choices(
        categoria=[
            app_commands.Choice(name="Ver configuracion actual", value="resumen"),
            app_commands.Choice(name="Permisos de roles", value="permiso"),
            app_commands.Choice(name="Canales", value="canal"),
        ],
        permiso=[
            app_commands.Choice(name="Aceptar solicitudes", value="aprobar"),
            app_commands.Choice(name="Rechazar solicitudes", value="rechazar"),
            app_commands.Choice(name="Asignar placas", value="asignar"),
            app_commands.Choice(name="Limpiar placas", value="eliminar"),
            app_commands.Choice(name="Ver placas", value="ver"),
        ],
        accion=[
            app_commands.Choice(name="Establecer solo este rol", value="establecer"),
            app_commands.Choice(name="Agregar rol", value="agregar"),
            app_commands.Choice(name="Quitar rol", value="quitar"),
            app_commands.Choice(name="Limpiar permiso", value="limpiar"),
        ],
        canal_tipo=[
            app_commands.Choice(name="Solicitudes de placa", value="solicitudes"),
            app_commands.Choice(name="Solicitudes aceptadas", value="aceptadas"),
            app_commands.Choice(name="Solicitudes rechazadas", value="rechazadas"),
            app_commands.Choice(name="Logs administrativos", value="logs"),
        ],
    )
    async def config_cmd(
        self,
        interaction: discord.Interaction,
        categoria: app_commands.Choice[str],
        permiso: Optional[app_commands.Choice[str]] = None,
        rol: Optional[discord.Role] = None,
        accion: Optional[app_commands.Choice[str]] = None,
        canal_tipo: Optional[app_commands.Choice[str]] = None,
        canal: Optional[discord.TextChannel] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Acceso denegado",
                    description="Solo administradores pueden usar `/config`.",
                    color=cfg.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        if categoria.value == "resumen":
            await interaction.followup.send(embed=build_summary_embed(interaction.guild), ephemeral=True)
            return

        if categoria.value == "permiso":
            await self._configure_permission(interaction, permiso, rol, accion)
            return

        if categoria.value == "canal":
            await self._configure_channel(interaction, canal_tipo, canal)
            return

        await interaction.followup.send("Categoria no valida.", ephemeral=True)

    async def _configure_permission(
        self,
        interaction: discord.Interaction,
        permiso: Optional[app_commands.Choice[str]],
        rol: Optional[discord.Role],
        accion: Optional[app_commands.Choice[str]],
    ) -> None:
        if permiso is None:
            await interaction.followup.send("Selecciona el campo `permiso`.", ephemeral=True)
            return

        action = permiso.value
        edit_action = accion.value if accion else "establecer"
        current = db.get_roles(str(interaction.guild.id), action)

        if edit_action == "limpiar":
            new_roles: list[str] = []
        else:
            if rol is None:
                await interaction.followup.send(
                    "Selecciona el campo `rol`, o usa `accion: Limpiar permiso`.",
                    ephemeral=True,
                )
                return

            role_id = str(rol.id)
            if edit_action == "establecer":
                new_roles = [role_id]
            elif edit_action == "agregar":
                new_roles = current.copy()
                if role_id not in new_roles:
                    new_roles.append(role_id)
            elif edit_action == "quitar":
                new_roles = [rid for rid in current if rid != role_id]
            else:
                await interaction.followup.send("Accion de permiso no valida.", ephemeral=True)
                return

        db.set_roles(str(interaction.guild.id), action, new_roles)
        logger.info("Permiso %s actualizado por %s: %s", action, interaction.user, new_roles)

        embed = discord.Embed(
            title="Permiso actualizado",
            color=cfg.COLOR_GREEN,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Permiso", value=PERMISSIONS[action], inline=False)
        embed.add_field(name="Roles permitidos", value=_roles_text(interaction.guild, new_roles), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _configure_channel(
        self,
        interaction: discord.Interaction,
        canal_tipo: Optional[app_commands.Choice[str]],
        canal: Optional[discord.TextChannel],
    ) -> None:
        if canal_tipo is None:
            await interaction.followup.send("Selecciona el campo `canal_tipo`.", ephemeral=True)
            return

        db_key, label = CHANNELS[canal_tipo.value]
        channel_id = str(canal.id) if canal else None
        db.set_guild_channel(str(interaction.guild.id), db_key, channel_id)
        logger.info("Canal %s actualizado por %s: %s", db_key, interaction.user, channel_id)

        embed = discord.Embed(
            title="Canal actualizado",
            color=cfg.COLOR_GREEN,
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Tipo", value=label, inline=False)
        embed.add_field(name="Canal", value=canal.mention if canal else "*No configurado*", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Config(bot))
