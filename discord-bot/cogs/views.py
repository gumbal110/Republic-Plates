"""
Persistent UI components — buttons and modals for the badge approval flow.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

import discord

import config
import database as db

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Permission helper                                                   #
# ------------------------------------------------------------------ #

def member_has_action(member: discord.Member, action: str) -> bool:
    """Return True if the member may perform `action`.

    - Administrators always pass.
    - If roles are configured: member must hold at least one.
    - If no roles configured:
        - USER_ACTIONS (turno, actividad) → open to all.
        - Other actions → require Manage Server.
    """
    if member.guild_permissions.administrator:
        return True
    role_ids = db.get_roles(str(member.guild.id), action)
    if not role_ids:
        return action in db.USER_ACTIONS or member.guild_permissions.manage_guild
    return any(
        member.guild.get_role(int(rid)) in member.roles
        for rid in role_ids
        if rid
    )


# ------------------------------------------------------------------ #
#  Nickname helpers                                                    #
# ------------------------------------------------------------------ #

_BADGE_PREFIX_RE = re.compile(r"^\[PN-\d+\]\s*")


def _base_name(member: discord.Member) -> str:
    """Return display name with any existing [PN-XXX] prefix stripped."""
    return _BADGE_PREFIX_RE.sub("", member.display_name).strip()


async def set_badge_nickname(
    member: discord.Member, badge_number: str, channel: Optional[discord.abc.Messageable] = None
) -> None:
    """Set nickname to [PN-XXX] Name, zero-padding the number to 3 digits."""
    raw_digits = badge_number.split("-", 1)[1]
    padded = raw_digits.zfill(3)
    prefix = f"[PN-{padded}]"
    base = _base_name(member)
    new_nick = f"{prefix} {base}"
    if len(new_nick) > 32:
        allowed = 32 - len(prefix) - 1
        new_nick = f"{prefix} {base[:allowed]}"
    try:
        await member.edit(nick=new_nick)
        logger.info("Apodo actualizado para %s → %s", member, new_nick)
    except discord.Forbidden:
        logger.warning("Sin permisos para cambiar apodo de %s.", member)
        if channel:
            try:
                await channel.send(
                    embed=discord.Embed(
                        title="⚠️ Sin Permisos para Cambiar Apodo",
                        description=(
                            f"No tengo permisos para cambiar el apodo de {member.mention}.\n"
                            f"Por favor, actualízalo manualmente a: **{new_nick}**"
                        ),
                        color=config.COLOR_GOLD,
                    )
                )
            except Exception:
                pass
    except Exception as e:
        logger.error("Error al cambiar apodo de %s: %s", member, e)


async def clear_badge_nickname(
    member: discord.Member, channel: Optional[discord.abc.Messageable] = None
) -> None:
    """Remove [PN-XXX] prefix from nickname, restoring the plain name."""
    base = _base_name(member)
    try:
        await member.edit(nick=base if base != member.name else None)
        logger.info("Apodo limpiado para %s → %s", member, base)
    except discord.Forbidden:
        logger.warning("Sin permisos para limpiar apodo de %s.", member)
        if channel:
            try:
                await channel.send(
                    embed=discord.Embed(
                        title="⚠️ Sin Permisos para Cambiar Apodo",
                        description=(
                            f"No tengo permisos para limpiar el apodo de {member.mention}.\n"
                            f"Por favor, retira manualmente el prefijo de la placa de su apodo."
                        ),
                        color=config.COLOR_GOLD,
                    )
                )
            except Exception:
                pass
    except Exception as e:
        logger.error("Error al limpiar apodo de %s: %s", member, e)


def _denied_embed(action: str) -> discord.Embed:
    role_id = None
    return discord.Embed(
        title="🔒 Acceso Denegado",
        description=(
            f"No tienes el rol necesario para **{action}** placas.\n"
            "Contacta a un administrador para configurar los permisos con `/config`."
        ),
        color=config.COLOR_RED,
    )


# ------------------------------------------------------------------ #
#  Modal — Asignar Placa                                               #
# ------------------------------------------------------------------ #

class AsignarPlacaModal(discord.ui.Modal, title="Asignación de Placa Institucional"):
    badge_number: discord.ui.TextInput = discord.ui.TextInput(
        label="Número de Placa",
        placeholder="PN-025  /  PN-125  /  PN-1025",
        min_length=6,
        max_length=10,
        required=True,
    )
    user_id_input: discord.ui.TextInput = discord.ui.TextInput(
        label="ID del oficial (User ID numérico)",
        placeholder="Ej: 123456789012345678",
        min_length=15,
        max_length=20,
        required=True,
    )

    def __init__(self, request_id: int, requester_id: str) -> None:
        super().__init__()
        self.request_id = request_id
        self.requester_id = requester_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not member_has_action(interaction.user, "asignar"):
            await interaction.followup.send(
                embed=_denied_embed("asignar"), ephemeral=True
            )
            return

        badge_raw = self.badge_number.value.strip().upper()
        uid_raw = self.user_id_input.value.strip().lstrip("<@!").rstrip(">")

        # Validate badge format
        if not re.match(config.BADGE_REGEX, badge_raw):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Formato inválido",
                    description=(
                        "El número de placa debe tener el formato **PN-###** "
                        "(mínimo 3 dígitos).\nEjemplos: `PN-001`, `PN-025`, `PN-125`"
                    ),
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        # Validate user ID
        if not uid_raw.isdigit():
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ ID de usuario inválido",
                    description="Proporciona el ID numérico del usuario (no una mención).",
                    color=config.COLOR_RED,
                ),
                ephemeral=True,
            )
            return

        # Check: badge already taken
        if db.badge_number_exists(badge_raw):
            existing = db.get_badge_by_number(badge_raw)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Placa Ocupada",
                    description=(
                        f"La placa **{badge_raw}** ya está asignada al oficial "
                        f"**{existing['username']}**."
                    ),
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        # Check: user already has a badge
        if db.user_has_badge(uid_raw):
            existing = db.get_badge_by_user(uid_raw)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="⚠️ Oficial Ya Tiene Placa",
                    description=(
                        f"Este oficial ya posee la placa institucional **{existing['badge_number']}**."
                    ),
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        # Resolve member
        member: Optional[discord.Member] = None
        try:
            member = await interaction.guild.fetch_member(int(uid_raw))
        except (discord.NotFound, discord.HTTPException):
            pass

        username = str(member) if member else f"ID:{uid_raw}"

        # Assign badge
        db.assign_badge(
            badge_number=badge_raw,
            user_id=uid_raw,
            username=username,
            assigned_by=str(interaction.user),
        )
        db.mark_request(self.request_id, "aprobada")

        # Update review embed buttons (disable them)
        await _disable_request_buttons(interaction, self.request_id)

        # Change nickname immediately
        if member:
            await set_badge_nickname(member, badge_raw, channel=interaction.channel)

        # Official confirmation embed
        confirm_embed = discord.Embed(
            title="🚔 Policía Nacional de la República Dominicana",
            description=(
                f"Se le asigna oficialmente al oficial {member.mention if member else f'<@{uid_raw}>'} "
                f"la placa institucional **{badge_raw}**.\n\n"
                "_Registro institucional actualizado._"
            ),
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        confirm_embed.set_footer(
            text="Policía Nacional · Dirección de Recursos Humanos",
        )
        await _send_configured_channel_embed(
            interaction.guild,
            "channel_aceptadas",
            confirm_embed,
            fallback=interaction.channel,
        )
        await _send_log_embed(
            interaction.guild,
            title="Placa asignada",
            description=f"{interaction.user.mention} asigno **{badge_raw}** a {member.mention if member else f'<@{uid_raw}>'}.",
            color=config.COLOR_GREEN,
        )

        # DM the officer
        if member:
            await _dm_officer(
                member=member,
                title="✅ Placa Institucional Asignada",
                description=(
                    f"Felicitaciones, oficial.\n\n"
                    f"Se te ha asignado oficialmente la placa **{badge_raw}**.\n"
                    "Bienvenido al Registro Institucional de la Policía Nacional."
                ),
                color=config.COLOR_GREEN,
            )

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Placa Asignada",
                description=f"La placa **{badge_raw}** fue asignada a **{username}** correctamente.",
                color=config.COLOR_GREEN,
            ),
            ephemeral=True,
        )
        logger.info("Placa %s asignada a %s por %s", badge_raw, username, interaction.user)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.error("Error en AsignarPlacaModal: %s", error, exc_info=True)
        try:
            await interaction.followup.send(
                "Ocurrió un error inesperado. Inténtalo de nuevo.", ephemeral=True
            )
        except Exception:
            pass


# ------------------------------------------------------------------ #
#  View — Solicitud Buttons                                            #
# ------------------------------------------------------------------ #

class SolicitudView(discord.ui.View):
    """Persistent view attached to each badge request embed."""

    def __init__(self, request_id: int, requester_id: str) -> None:
        super().__init__(timeout=None)
        self.request_id = request_id
        self.requester_id = requester_id
        self.aceptar_button.custom_id = f"solicitud_aceptar:{request_id}"
        self.rechazar_button.custom_id = f"solicitud_rechazar:{request_id}"

    @discord.ui.button(
        label="✅  Aceptar",
        style=discord.ButtonStyle.success,
        custom_id="solicitud_aceptar:0",
    )
    async def aceptar_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not member_has_action(interaction.user, "aprobar"):
            await interaction.response.send_message(
                embed=_denied_embed("aprobar"), ephemeral=True
            )
            return

        request = db.get_request(self.request_id)
        if not request or request["status"] != "pendiente":
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⚠️ Solicitud Ya Procesada",
                    description="Esta solicitud ya fue atendida.",
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            AsignarPlacaModal(self.request_id, self.requester_id)
        )

    @discord.ui.button(
        label="❌  Rechazar",
        style=discord.ButtonStyle.danger,
        custom_id="solicitud_rechazar:0",
    )
    async def rechazar_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not member_has_action(interaction.user, "rechazar"):
            await interaction.response.send_message(
                embed=_denied_embed("rechazar"), ephemeral=True
            )
            return

        request = db.get_request(self.request_id)
        if not request or request["status"] != "pendiente":
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⚠️ Solicitud Ya Procesada",
                    description="Esta solicitud ya fue atendida.",
                    color=config.COLOR_GOLD,
                ),
                ephemeral=True,
            )
            return

        db.mark_request(self.request_id, "rechazada")
        await _disable_request_buttons(interaction, self.request_id, rejected=True)

        # DM the officer
        guild = interaction.guild
        try:
            member = await guild.fetch_member(int(request["user_id"]))
            await _dm_officer(
                member=member,
                title="❌ Solicitud de Placa Denegada",
                description=(
                    "Tu solicitud de placa institucional ha sido **denegada** "
                    "por un superior.\n\nPuedes volver a solicitarla cuando estés listo."
                ),
                color=config.COLOR_RED,
            )
        except Exception:
            pass

        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Solicitud Rechazada",
                description=f"La solicitud de **{request['username']}** fue rechazada.",
                color=config.COLOR_RED,
            ),
            ephemeral=True,
        )
        rejected_embed = discord.Embed(
            title="Solicitud de placa rechazada",
            description=f"La solicitud de **{request['username']}** fue rechazada por {interaction.user.mention}.",
            color=config.COLOR_RED,
            timestamp=datetime.utcnow(),
        )
        await _send_configured_channel_embed(
            interaction.guild,
            "channel_rechazadas",
            rejected_embed,
            fallback=interaction.channel,
        )
        await _send_log_embed(
            interaction.guild,
            title="Solicitud rechazada",
            description=f"{interaction.user.mention} rechazo la solicitud #{self.request_id} de **{request['username']}**.",
            color=config.COLOR_RED,
        )
        logger.info("Solicitud #%d rechazada por %s", self.request_id, interaction.user)


# ------------------------------------------------------------------ #
#  Paginated Badges View                                               #
# ------------------------------------------------------------------ #

class PlacasView(discord.ui.View):
    PER_PAGE = 10

    def __init__(self, badges: list, page: int = 0) -> None:
        super().__init__(timeout=120)
        self.badges = badges
        self.page = page
        self._update_buttons()

    def _update_buttons(self) -> None:
        total_pages = max(1, -(-len(self.badges) // self.PER_PAGE))
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= total_pages - 1

    def build_embed(self) -> discord.Embed:
        total = len(self.badges)
        total_pages = max(1, -(-total // self.PER_PAGE))
        start = self.page * self.PER_PAGE
        chunk = self.badges[start : start + self.PER_PAGE]

        embed = discord.Embed(
            title="🪪 Registro Oficial de Placas — Policía Nacional RD",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        if not chunk:
            embed.description = "_No hay placas registradas en el sistema._"
        else:
            lines = []
            for b in chunk:
                lines.append(f"**`{b['badge_number']}`** — <@{b['user_id']}>")
            embed.description = "\n".join(lines)

        embed.set_footer(text=f"Página {self.page + 1} de {total_pages}  ·  Total: {total} placa(s)")
        return embed

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Siguiente ▶", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

async def _disable_request_buttons(
    interaction: discord.Interaction,
    request_id: int,
    rejected: bool = False,
) -> None:
    """Disable the Aceptar/Rechazar buttons on the original request embed."""
    try:
        request = db.get_request(request_id)
        if not request or not request["message_id"] or not request["channel_id"]:
            return
        channel = interaction.guild.get_channel(int(request["channel_id"]))
        if not channel:
            return
        message = await channel.fetch_message(int(request["message_id"]))
        if not message:
            return

        label = "❌ Rechazada" if rejected else "✅ Aprobada"
        color = config.COLOR_RED if rejected else config.COLOR_GREEN

        new_embed = message.embeds[0] if message.embeds else discord.Embed()
        new_embed.color = color
        new_embed.set_footer(text=f"Estado: {label}  ·  Procesada por {interaction.user}")

        disabled_view = discord.ui.View()
        b1 = discord.ui.Button(
            label="✅  Aceptar", style=discord.ButtonStyle.success, disabled=True
        )
        b2 = discord.ui.Button(
            label="❌  Rechazar", style=discord.ButtonStyle.danger, disabled=True
        )
        disabled_view.add_item(b1)
        disabled_view.add_item(b2)

        await message.edit(embed=new_embed, view=disabled_view)
    except Exception as e:
        logger.warning("No se pudo actualizar el mensaje de solicitud: %s", e)


async def _dm_officer(
    member: discord.Member,
    title: str,
    description: str,
    color: int,
) -> None:
    try:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Policía Nacional · República Dominicana")
        await member.send(embed=embed)
    except discord.Forbidden:
        logger.debug("No se pudo enviar DM a %s (DMs cerrados).", member)
    except Exception as e:
        logger.warning("Error enviando DM a %s: %s", member, e)


async def _send_configured_channel_embed(
    guild: discord.Guild,
    channel_key: str,
    embed: discord.Embed,
    fallback: Optional[discord.abc.Messageable] = None,
) -> None:
    guild_config = db.get_guild_config(str(guild.id))
    channel_id = guild_config[channel_key] if guild_config and channel_key in guild_config.keys() else None
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    target = channel or fallback
    if not target:
        return
    try:
        await target.send(embed=embed)
    except discord.Forbidden:
        logger.warning("Sin permisos para enviar al canal configurado %s.", channel_key)
    except Exception as e:
        logger.warning("Error enviando embed al canal %s: %s", channel_key, e)


async def _send_log_embed(
    guild: discord.Guild,
    title: str,
    description: str,
    color: int,
) -> None:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.set_footer(text="Policia Nacional · Logs administrativos")
    await _send_configured_channel_embed(guild, "channel_logs", embed)
