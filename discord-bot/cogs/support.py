from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

import config
import database as db

logger = logging.getLogger(__name__)

SUPPORT_TYPES: dict[str, tuple[str, str]] = {
    "general": ("Soporte general", "Ayuda general con el servidor o el sistema."),
    "placa": ("Soporte de placa", "Problemas con solicitudes, placas o apodos."),
    "reporte": ("Reporte interno", "Reportar una situacion que requiere revision."),
    "otro": ("Otro", "Cualquier otro asunto administrativo."),
}

APPLICATION_QUESTIONS: list[str] = [
    "Cual es tu nombre o usuario principal?",
    "Cual es tu edad?",
    "Por que quieres postularte a la Policia Nacional?",
    "Que experiencia tienes en roleplay o moderacion?",
    "Cual es tu disponibilidad semanal?",
    "Que harias si un usuario rompe las normas?",
]


def _configured_channel(guild: discord.Guild, key: str) -> Optional[discord.abc.GuildChannel]:
    cfg = db.get_guild_config(str(guild.id))
    channel_id = cfg[key] if cfg and key in cfg.keys() else None
    return guild.get_channel(int(channel_id)) if channel_id else None


def _role_mentions(guild: discord.Guild, action: str) -> str:
    role_ids = db.get_roles(str(guild.id), action)
    mentions = []
    for role_id in role_ids:
        role = guild.get_role(int(role_id)) if role_id.isdigit() else None
        if role:
            mentions.append(role.mention)
    return " ".join(mentions)


class SupportPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir ticket",
        style=discord.ButtonStyle.primary,
        custom_id="pn_support_open",
    )
    async def open_ticket_menu(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            "Selecciona el tipo de soporte:",
            view=SupportOptionsView(),
            ephemeral=True,
        )


class SupportOptionsView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=120)

    async def _create_ticket(self, interaction: discord.Interaction, ticket_type: str) -> None:
        await interaction.response.defer(ephemeral=True)

        existing = db.get_open_ticket(str(interaction.guild.id), str(interaction.user.id))
        if existing:
            await interaction.followup.send(
                f"Ya tienes un ticket abierto: <#{existing['channel_id']}>",
                ephemeral=True,
            )
            return

        label, description = SUPPORT_TYPES[ticket_type]
        category = _configured_channel(interaction.guild, "ticket_category")
        if category and not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }

        support_role_ids = db.get_roles(str(interaction.guild.id), "soporte")
        for role_id in support_role_ids:
            role = interaction.guild.get_role(int(role_id)) if role_id.isdigit() else None
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )

        channel_name = f"ticket-{interaction.user.name}".lower().replace(" ", "-")[:90]
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket de soporte creado por {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permisos para crear canales de ticket.",
                ephemeral=True,
            )
            return
        except Exception as e:
            logger.error("Error creando ticket: %s", e, exc_info=True)
            await interaction.followup.send("No se pudo crear el ticket.", ephemeral=True)
            return
        ticket_id = db.create_ticket(
            guild_id=str(interaction.guild.id),
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            channel_id=str(channel.id),
            ticket_type=ticket_type,
        )

        embed = discord.Embed(
            title=f"Ticket #{ticket_id} - {label}",
            description=(
                f"Creado por {interaction.user.mention}\n\n"
                f"**Tipo:** {label}\n"
                f"**Descripcion:** {description}\n\n"
                "Describe tu situacion con detalle. Un encargado te respondera pronto."
            ),
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text="Policia Nacional · Soporte")
        mentions = _role_mentions(interaction.guild, "soporte")
        await channel.send(
            content=f"{mentions} {interaction.user.mention}".strip(),
            embed=embed,
            view=TicketCloseView(),
        )
        await interaction.followup.send(f"Ticket creado: {channel.mention}", ephemeral=True)

    @discord.ui.button(label="Soporte general", style=discord.ButtonStyle.secondary)
    async def general(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._create_ticket(interaction, "general")

    @discord.ui.button(label="Placa", style=discord.ButtonStyle.secondary)
    async def placa(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._create_ticket(interaction, "placa")

    @discord.ui.button(label="Reporte", style=discord.ButtonStyle.secondary)
    async def reporte(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._create_ticket(interaction, "reporte")

    @discord.ui.button(label="Otro", style=discord.ButtonStyle.secondary)
    async def otro(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._create_ticket(interaction, "otro")


class TicketCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Cerrar ticket",
        style=discord.ButtonStyle.danger,
        custom_id="pn_ticket_close",
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        can_close = (
            interaction.user.guild_permissions.manage_channels
            or any(
                role.id in {int(rid) for rid in db.get_roles(str(interaction.guild.id), "soporte") if rid.isdigit()}
                for role in interaction.user.roles
            )
        )
        if not can_close:
            await interaction.response.send_message("No puedes cerrar este ticket.", ephemeral=True)
            return

        await interaction.response.send_message("Cerrando ticket en 5 segundos...", ephemeral=True)
        db.close_ticket(str(interaction.channel.id))
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket cerrado por {interaction.user}")


class ApplicationPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Postularme",
        style=discord.ButtonStyle.success,
        custom_id="pn_application_start",
    )
    async def start_application(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            dm = await interaction.user.create_dm()
            await dm.send(
                "Vamos a iniciar tu postulacion. Responde cada pregunta en este DM. "
                "Tienes 5 minutos por pregunta."
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "No pude enviarte DM. Abre tus mensajes privados e intenta de nuevo.",
                ephemeral=True,
            )
            return

        await interaction.followup.send("Te envie las preguntas por DM.", ephemeral=True)

        answers: dict[str, str] = {}

        def check(message: discord.Message) -> bool:
            return message.author.id == interaction.user.id and message.channel.id == dm.id

        for index, question in enumerate(APPLICATION_QUESTIONS, start=1):
            await dm.send(f"**Pregunta {index}/{len(APPLICATION_QUESTIONS)}:** {question}")
            try:
                message = await self.bot.wait_for("message", check=check, timeout=300)
            except asyncio.TimeoutError:
                await dm.send("La postulacion fue cancelada por tiempo de espera.")
                return
            answers[question] = message.content.strip()[:1000]

        application_id = db.create_application(
            guild_id=str(interaction.guild.id),
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            answers=answers,
        )

        target = _configured_channel(interaction.guild, "channel_applications")
        if not target or not isinstance(target, discord.TextChannel):
            await dm.send("Postulacion recibida, pero el canal de postulaciones no esta configurado.")
            return

        embed = discord.Embed(
            title=f"Postulacion #{application_id}",
            description=f"Postulante: {interaction.user.mention}\nID: `{interaction.user.id}`",
            color=config.COLOR_NAVY,
            timestamp=datetime.utcnow(),
        )
        for question, answer in answers.items():
            embed.add_field(name=question, value=answer or "*Sin respuesta*", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Policia Nacional · Postulaciones")
        mentions = _role_mentions(interaction.guild, "postulaciones")
        await target.send(content=mentions, embed=embed)
        await dm.send("Tu postulacion fue enviada correctamente. Gracias.")


class Support(commands.Cog, name="Soporte"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.add_view(SupportPanelView())
        bot.add_view(TicketCloseView())
        bot.add_view(ApplicationPanelView(bot))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Support(bot))
