import sqlite3
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "discord-bot/pn_bot.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS badge_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                username    TEXT NOT NULL,
                guild_id    TEXT NOT NULL,
                message_id  TEXT,
                channel_id  TEXT,
                status      TEXT NOT NULL DEFAULT 'pendiente',
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS badges (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                badge_number TEXT NOT NULL UNIQUE,
                user_id      TEXT NOT NULL UNIQUE,
                username     TEXT NOT NULL,
                assigned_by  TEXT NOT NULL,
                assigned_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS role_config (
                guild_id TEXT NOT NULL,
                action   TEXT NOT NULL,
                role_id  TEXT NOT NULL,
                PRIMARY KEY (guild_id, action)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT NOT NULL,
                actor_id    TEXT NOT NULL,
                actor_name  TEXT NOT NULL,
                target_id   TEXT,
                target_name TEXT,
                details     TEXT,
                created_at  TEXT NOT NULL
            );
        """)
    logger.info("Base de datos inicializada: %s", DB_PATH)


# ------------------------------------------------------------------ #
#  Requests                                                            #
# ------------------------------------------------------------------ #

def create_request(user_id: str, username: str, guild_id: str) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO badge_requests (user_id, username, guild_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, username, guild_id, now),
        )
        return cur.lastrowid


def update_request_message(request_id: int, message_id: str, channel_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE badge_requests SET message_id=?, channel_id=? WHERE id=?",
            (message_id, channel_id, request_id),
        )


def get_request(request_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM badge_requests WHERE id=?", (request_id,)
        ).fetchone()


def mark_request(request_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE badge_requests SET status=? WHERE id=?",
            (status, request_id),
        )


def has_pending_request(user_id: str, guild_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM badge_requests WHERE user_id=? AND guild_id=? AND status='pendiente'",
            (user_id, guild_id),
        ).fetchone()
        return row is not None


# ------------------------------------------------------------------ #
#  Badges                                                              #
# ------------------------------------------------------------------ #

def badge_number_exists(badge_number: str) -> bool:
    with get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM badges WHERE badge_number=?", (badge_number,)
        ).fetchone() is not None


def user_has_badge(user_id: str) -> bool:
    with get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM badges WHERE user_id=?", (user_id,)
        ).fetchone() is not None


def get_badge_by_user(user_id: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM badges WHERE user_id=?", (user_id,)
        ).fetchone()


def get_badge_by_number(badge_number: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM badges WHERE badge_number=?", (badge_number,)
        ).fetchone()


def assign_badge(
    badge_number: str, user_id: str, username: str, assigned_by: str
) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO badges (badge_number, user_id, username, assigned_by, assigned_at)
               VALUES (?, ?, ?, ?, ?)""",
            (badge_number, user_id, username, assigned_by, now),
        )
        log_action(
            conn,
            action="ASIGNACION_PLACA",
            actor_id=assigned_by,
            actor_name=assigned_by,
            target_id=user_id,
            target_name=username,
            details=f"Placa asignada: {badge_number}",
        )


def remove_badge(user_id: str, removed_by: str, removed_by_name: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM badges WHERE user_id=?", (user_id,)
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM badges WHERE user_id=?", (user_id,))
        log_action(
            conn,
            action="ELIMINACION_PLACA",
            actor_id=removed_by,
            actor_name=removed_by_name,
            target_id=user_id,
            target_name=row["username"],
            details=f"Placa eliminada: {row['badge_number']}",
        )
        return row


def get_all_badges() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM badges ORDER BY badge_number ASC"
        ).fetchall()


# ------------------------------------------------------------------ #
#  Role Config                                                         #
# ------------------------------------------------------------------ #

ACTIONS = ("aprobar", "rechazar", "asignar", "eliminar", "ver")


def set_role(guild_id: str, action: str, role_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO role_config (guild_id, action, role_id)
               VALUES (?, ?, ?)
               ON CONFLICT(guild_id, action) DO UPDATE SET role_id=excluded.role_id""",
            (guild_id, action, role_id),
        )


def get_role(guild_id: str, action: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT role_id FROM role_config WHERE guild_id=? AND action=?",
            (guild_id, action),
        ).fetchone()
        return row["role_id"] if row else None


def get_all_roles(guild_id: str) -> dict[str, Optional[str]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT action, role_id FROM role_config WHERE guild_id=?", (guild_id,)
        ).fetchall()
        result = {a: None for a in ACTIONS}
        for r in rows:
            result[r["action"]] = r["role_id"]
        return result


# ------------------------------------------------------------------ #
#  Audit Log                                                           #
# ------------------------------------------------------------------ #

def log_action(
    conn: sqlite3.Connection,
    action: str,
    actor_id: str,
    actor_name: str,
    target_id: Optional[str] = None,
    target_name: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    conn.execute(
        """INSERT INTO audit_log (action, actor_id, actor_name, target_id, target_name, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (action, actor_id, actor_name, target_id, target_name, details, now),
    )
