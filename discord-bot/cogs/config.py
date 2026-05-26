"""
/config — Panel visual de configuración de roles con Role Select Menus.
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


# ------------------------------------------------------------------ #
#  Embed builder                                                       #
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


# ------------------------------------------------------------------ #
#  UI Components                                                       #
# ------------------------------------------------------------------ #

class CategorySelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=label.strip(), value=action)
            for action, label in CATEGORIES.items()
        ]
        super().__init__(
            placeholder="Selecciona qué permisos deseas configurar...",
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.show_role_editor(interaction, self.values[0])


class RoleConfigSelect(discord.ui.RoleSelect):
    def __init__(self, action: str) -> None:
        self.action = action
        label = CATEGORIES.get(action, action).strip()
        super().__init__(
            placeholder=f"Roles para: {label}  (vacío = sin restricción)",
            min_values=0,
            max_values=10,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.pending_role_ids = [str(r.id) for r in self.values]
        await interaction.response.defer()


class SaveButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="💾  Guardar configuración",
            style=discord.ButtonStyle.success,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
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
        self.view.add_item(CategorySelect())
        self.view.editing_action = None
        self.view.pending_role_ids = None

        embed = build_config_embed(interaction.guild)
        embed.description = f"✅ **{label}** actualizado → {saved_text}"
        await interaction.response.edit_message(embed=embed, view=self.view)


class BackButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="← Volver",
            style=discord.ButtonStyle.secondary,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.clear_items()
        self.view.add_item(CategorySelect())
        self.view.editing_action = None
        self.view.pending_role_ids = None
        embed = build_config_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)


# ------------------------------------------------------------------ #
#  View                                                                #
# ------------------------------------------------------------------ #

class ConfigView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.editing_action: Optional[str] = None
        self.pending_role_ids: Optional[list[str]] = None
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
        description="[ADMIN] Abre el panel visual de configuración de roles del bot.",
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
