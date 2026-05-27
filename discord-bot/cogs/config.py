"""
/config — Panel visual de configuración de roles y canales con Select Menus.
Solo administradores del servidor pueden usarlo.
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

CATEGORIES: dict[str, str] = {
    "aprobar":           "✅  Aprobar placas",
    "rechazar":          "❌  Rechazar placas",
    "asignar":           "📋  Asignar placas",
    "eliminar":          "🗑️  Limpiar placas",
    "turno":             "🚔  Iniciar turno",
    "actividad":         "📸  Registrar actividad",
    "revisar_actividad": "🔍  Revisar actividades",
}

CHANNEL_CATEGORIES: dict[str, str] = {
    "channel_solicitudes":  "📨  Canal de Solicitudes",
    "channel_aceptadas":    "✅  Canal de Solicitudes Aceptadas",
    "channel_rechazadas":   "❌  Canal de Solicitudes Rechazadas",
}


# ------------------------------------------------------------------ #
#  Embed builders                                                      #
# ------------------------------------------------------------------ #

def build_config_embed(guild: discord.Guild, highlight: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Configuración de Permisos — Policía Nacional RD",
        color=cfg.COLOR_NAVY,
        timestamp=datetime.utcnow(),
    )
    all_roles = db.get_all_roles_multi(str(guild.id))
    for action, label in CATEGORIES.items():
        role_ids = all_roles.get(action, [])
        if role_ids:
            roles_text = "  ".join(f"<@&{rid}>" for rid in role_ids)
        else:
            roles_text = "*Sin restricción*"
        name = f"▶ {label}" if action == highlight else label
        embed.add_field(name=name, value=roles_text, inline=False)
    embed.set_footer(
        text="Selecciona una categoría del menú para editar sus roles.  ·  Policía Nacional"
    )
    return embed


def build_channels_embed(guild: discord.Guild, highlight: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title="📡 Configuración de Canales — Policía Nacional RD",
        color=cfg.COLOR_NAVY,
        timestamp=datetime.utcnow(),
    )
    config = db.get_guild_config(str(guild.id))
    
    for channel_key, label in CHANNEL_CATEGORIES.items():
        channel_id = getattr(config, channel_key, None) if config else None
        if channel_id:
            channel = guild.get_channel(int(channel_id))
            channel_text = f"<#{channel_id}>" if channel else f"Canal: {channel_id}"
        else:
            channel_text = "*No configurado*"
        name = f"▶ {label}" if channel_key == highlight else label
        embed.add_field(name=name, value=channel_text, inline=False)
    embed.set_footer(
        text="Selecciona una categoría del menú para editar los canales.  ·  Policía Nacional"
    )
    return embed


# ------------------------------------------------------------------ #
#  UI Components                                                       #
# ------------------------------------------------------------------ #

class ModeSelect(discord.ui.Select):
    """Selector para elegir entre configurar roles o canales."""
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="Permisos de Roles", value="roles", emoji="🔐"),
            discord.SelectOption(label="Configuración de Canales", value="channels", emoji="📡"),
        ]
        super().__init__(
            placeholder="Selecciona qué deseas configurar...",
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        mode = self.values[0]
        if mode == "roles":
            self.view.clear_items()
            self.view.add_item(ModeSelect())
            self.view.add_item(CategorySelect())
            embed = build_config_embed(interaction.guild)
        else:
            self.view.clear_items()
            self.view.add_item(ModeSelect())
            self.view.add_item(ChannelCategorySelect())
            embed = build_channels_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)


class CategorySelect(discord.ui.Select):
    """Selector de categorías de roles."""
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=label.strip(), value=action)
            for action, label in CATEGORIES.items()
        ]
        super().__init__(
            placeholder="Selecciona qué permisos deseas configurar...",
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.show_role_editor(interaction, self.values[0])


class ChannelCategorySelect(discord.ui.Select):
    """Selector de categorías de canales."""
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=label.strip(), value=channel_key)
            for channel_key, label in CHANNEL_CATEGORIES.items()
        ]
        super().__init__(
            placeholder="Selecciona qué canal deseas configurar...",
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.show_channel_editor(interaction, self.values[0])


class RoleConfigSelect(discord.ui.RoleSelect):
    def __init__(self, action: str) -> None:
        self.action = action
        label = CATEGORIES.get(action, action).strip()
        super().__init__(
            placeholder=f"Roles para: {label}  (vacío = sin restricción)",
            min_values=0,
            max_values=10,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.pending_role_ids = [str(r.id) for r in self.values]
        await interaction.response.defer()


class ChannelConfigSelect(discord.ui.ChannelSelect):
    def __init__(self, channel_key: str) -> None:
        self.channel_key = channel_key
        label = CHANNEL_CATEGORIES.get(channel_key, channel_key).strip()
        super().__init__(
            placeholder=f"Selecciona canal para: {label}  (vacío = no configurado)",
            min_values=0,
            max_values=1,
            channel_types=[discord.ChannelType.text],
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values:
            self.view.pending_channel_id = str(self.values[0].id)
        else:
            self.view.pending_channel_id = None
        await interaction.response.defer()


class SaveButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="💾  Guardar configuración",
            style=discord.ButtonStyle.success,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if hasattr(self.view, "editing_action") and self.view.editing_action:
            # Guardando roles
            role_ids = self.view.pending_role_ids
            action = self.view.editing_action

            if role_ids is None:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ Sin cambios",
                        description=(
                            "Selecciona roles en el menú de abajo antes de guardar.\n"
                            "Para eliminar todos los roles, selecciona ninguno y guarda."
                        ),
                        color=cfg.COLOR_GOLD,
                    ),
                    ephemeral=True,
                )
                return

            db.set_roles(str(interaction.guild.id), action, role_ids)
            label = CATEGORIES.get(action, action).strip()
            saved_text = (
                "  ".join(f"<@&{rid}>" for rid in role_ids) if role_ids else "*Sin restricción*"
            )
            logger.info("Config %s actualizada por %s: %s", action, interaction.user, role_ids)

            self.view.clear_items()
            self.view.add_item(ModeSelect())
            self.view.add_item(CategorySelect())
            self.view.editing_action = None
            self.view.pending_role_ids = None

            embed = build_config_embed(interaction.guild)
            embed.description = f"✅ **{label}** actualizado → {saved_text}"
            await interaction.response.edit_message(embed=embed, view=self.view)
        
        elif hasattr(self.view, "editing_channel") and self.view.editing_channel:
            # Guardando canal
            channel_id = getattr(self.view, "pending_channel_id", None)
            channel_key = self.view.editing_channel

            # Construir el diccionario con el parámetro dinámico
            update_dict = {channel_key: channel_id}
            db.set_guild_config(str(interaction.guild.id), **update_dict)
            
            label = CHANNEL_CATEGORIES.get(channel_key, channel_key).strip()
            saved_text = f"<#{channel_id}>" if channel_id else "*No configurado*"
            logger.info("Config canal %s actualizada por %s: %s", channel_key, interaction.user, channel_id)

            self.view.clear_items()
            self.view.add_item(ModeSelect())
            self.view.add_item(ChannelCategorySelect())
            self.view.editing_channel = None
            self.view.pending_channel_id = None

            embed = build_channels_embed(interaction.guild)
            embed.description = f"✅ **{label}** actualizado → {saved_text}"
            await interaction.response.edit_message(embed=embed, view=self.view)


class BackButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="← Volver",
            style=discord.ButtonStyle.secondary,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.clear_items()
        self.view.add_item(ModeSelect())
        if hasattr(self.view, "editing_action"):
            self.view.add_item(CategorySelect())
            self.view.editing_action = None
            self.view.pending_role_ids = None
            embed = build_config_embed(interaction.guild)
        else:
            self.view.add_item(ChannelCategorySelect())
            self.view.editing_channel = None
            self.view.pending_channel_id = None
            embed = build_channels_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)


# ------------------------------------------------------------------ #
#  View                                                                #
# ------------------------------------------------------------------ #

class ConfigView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.editing_action: Optional[str] = None
        self.pending_role_ids: Optional[list[str]] = None
        self.editing_channel: Optional[str] = None
        self.pending_channel_id: Optional[str] = None
        self.add_item(ModeSelect())
        self.add_item(CategorySelect())

    async def show_role_editor(self, interaction: discord.Interaction, action: str) -> None:
        self.editing_action = action
        self.pending_role_ids = None

        label = CATEGORIES.get(action, action).strip()
        current = db.get_roles(str(interaction.guild.id), action)
        current_text = (
            "  ".join(f"<@&{rid}>" for rid in current) if current else "*Sin restricción (todos)*"
        )

        self.clear_items()
        self.add_item(ModeSelect())
        self.add_item(CategorySelect())
        self.add_item(RoleConfigSelect(action))
        self.add_item(SaveButton())
        self.add_item(BackButton())

        embed = build_config_embed(interaction.guild, highlight=action)
        embed.description = (
            f"**Editando:** {label}\n"
            f"**Roles actuales:** {current_text}\n\n"
            "Selecciona los roles en el menú de abajo y presiona **💾 Guardar**.\n"
            "*Seleccionar ningún rol = sin restricción (cualquiera puede usar esta acción).*"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def show_channel_editor(self, interaction: discord.Interaction, channel_key: str) -> None:
        self.editing_channel = channel_key
        self.pending_channel_id = None

        label = CHANNEL_CATEGORIES.get(channel_key, channel_key).strip()
        config = db.get_guild_config(str(interaction.guild.id))
        current_channel_id = getattr(config, channel_key, None) if config else None
        current_text = (
            f"<#{current_channel_id}>" if current_channel_id else "*No configurado*"
        )

        self.clear_items()
        self.add_item(ModeSelect())
        self.add_item(ChannelCategorySelect())
        self.add_item(ChannelConfigSelect(channel_key))
        self.add_item(SaveButton())
        self.add_item(BackButton())

        embed = build_channels_embed(interaction.guild, highlight=channel_key)
        embed.description = (
            f"**Editando:** {label}\n"
            f"**Canal actual:** {current_text}\n\n"
            "Selecciona el canal en el menú de abajo y presiona **💾 Guardar**.\n"
            "*Seleccionar ningún canal = no configurado.*"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


# ------------------------------------------------------------------ #
#  Cog                                                                 #
# ------------------------------------------------------------------ #

class Config(commands.Cog, name="Configuración"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="config",
        description="[ADMIN] Abre el panel visual de configuración de roles y canales.",
    )
    @app_commands.default_permissions(administrator=True)
    async def config_cmd(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🔒 Acceso Denegado",
                    description="Solo los administradores del servidor pueden usar `/config`.",
                    color=cfg.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        view = ConfigView()
        embed = build_config_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Config(bot))
