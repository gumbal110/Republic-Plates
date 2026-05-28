import sqlite3
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "pn_bot.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent column migrations — safe to run on every startup."""
    migrations = [
        "ALTER TABLE role_config ADD COLUMN role_ids TEXT DEFAULT '[]'",
        "ALTER TABLE activities ADD COLUMN status TEXT NOT NULL DEFAULT 'pendiente'",
        "ALTER TABLE activities ADD COLUMN reviewed_by TEXT",
        "ALTER TABLE activities ADD COLUMN reviewed_at TEXT",
        "ALTER TABLE activities ADD COLUMN message_id TEXT",
        "ALTER TABLE activities ADD COLUMN channel_id TEXT",
        "ALTER TABLE guild_config ADD COLUMN channel_logs TEXT",
        "ALTER TABLE guild_config ADD COLUMN channel_support_panel TEXT",
        "ALTER TABLE guild_config ADD COLUMN channel_application_panel TEXT",
        "ALTER TABLE guild_config ADD COLUMN channel_applications TEXT",
        "ALTER TABLE guild_config ADD COLUMN ticket_category TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass


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

            CREATE TABLE IF NOT EXISTS shifts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT NOT NULL,
                username        TEXT NOT NULL,
                guild_id        TEXT NOT NULL,
                badge_number    TEXT NOT NULL,
                start_time      TEXT NOT NULL,
                pause_start     TEXT,
                paused_seconds  INTEGER NOT NULL DEFAULT 0,
                end_time        TEXT,
                status          TEXT NOT NULL DEFAULT 'activo',
                message_id      TEXT,
                channel_id      TEXT
            );

            CREATE TABLE IF NOT EXISTS activities (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       TEXT NOT NULL,
                username      TEXT NOT NULL,
                guild_id      TEXT NOT NULL,
                badge_number  TEXT NOT NULL,
                description   TEXT NOT NULL,
                image_urls    TEXT NOT NULL,
                registered_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id             TEXT PRIMARY KEY,
                channel_solicitudes  TEXT,
                channel_aceptadas    TEXT,
                channel_rechazadas   TEXT,
                channel_logs         TEXT,
                channel_support_panel TEXT,
                channel_application_panel TEXT,
                channel_applications TEXT,
                ticket_category      TEXT,
                welcome_message      TEXT
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                username     TEXT NOT NULL,
                channel_id   TEXT NOT NULL,
                ticket_type  TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'abierto',
                created_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS applications (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                username     TEXT NOT NULL,
                answers      TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'pendiente',
                created_at   TEXT NOT NULL
            );
        """)
        _migrate(conn)
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

ACTIONS = (
    "aprobar", "rechazar", "asignar", "eliminar", "ver",
    "turno", "actividad", "revisar_actividad", "soporte", "postulaciones",
)

# Actions where "no roles configured" means open to anyone (not just admins)
USER_ACTIONS = frozenset({"turno", "actividad"})


def set_roles(guild_id: str, action: str, role_ids: list[str]) -> None:
    import json as _json
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO role_config (guild_id, action, role_id, role_ids)
               VALUES (?, ?, '', ?)
               ON CONFLICT(guild_id, action) DO UPDATE SET role_ids=excluded.role_ids""",
            (guild_id, action, _json.dumps(role_ids)),
        )


def get_roles(guild_id: str, action: str) -> list[str]:
    import json as _json
    with get_connection() as conn:
        row = conn.execute(
            "SELECT role_ids FROM role_config WHERE guild_id=? AND action=?",
            (guild_id, action),
        ).fetchone()
        if not row or not row["role_ids"]:
            return []
        try:
            return _json.loads(row["role_ids"]) or []
        except Exception:
            return []


def get_all_roles_multi(guild_id: str) -> dict[str, list[str]]:
    import json as _json
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT action, role_ids FROM role_config WHERE guild_id=?", (guild_id,)
        ).fetchall()
        result: dict[str, list[str]] = {a: [] for a in ACTIONS}
        for r in rows:
            try:
                result[r["action"]] = _json.loads(r["role_ids"] or "[]") or []
            except Exception:
                pass
        return result


# Legacy single-role helpers kept for any existing call sites
def set_role(guild_id: str, action: str, role_id: str) -> None:
    set_roles(guild_id, action, [role_id] if role_id else [])


def get_role(guild_id: str, action: str) -> Optional[str]:
    ids = get_roles(guild_id, action)
    return ids[0] if ids else None


def get_all_roles(guild_id: str) -> dict[str, Optional[str]]:
    multi = get_all_roles_multi(guild_id)
    return {k: (v[0] if v else None) for k, v in multi.items()}


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


# ------------------------------------------------------------------ #
#  Shifts                                                              #
# ------------------------------------------------------------------ #

def create_shift(
    user_id: str, username: str, guild_id: str, badge_number: str
) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO shifts (user_id, username, guild_id, badge_number, start_time)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, username, guild_id, badge_number, now),
        )
        return cur.lastrowid


def update_shift_message(shift_id: int, message_id: str, channel_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE shifts SET message_id=?, channel_id=? WHERE id=?",
            (message_id, channel_id, shift_id),
        )


def get_shift(shift_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()


def get_active_shift(user_id: str, guild_id: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM shifts WHERE user_id=? AND guild_id=? AND status IN ('activo','pausado')",
            (user_id, guild_id),
        ).fetchone()


def get_all_active_shifts(guild_id: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM shifts WHERE guild_id=? AND status IN ('activo','pausado') ORDER BY start_time ASC",
            (guild_id,),
        ).fetchall()


def get_all_active_shifts_globally() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM shifts WHERE status IN ('activo','pausado')"
        ).fetchall()


def pause_shift(shift_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE shifts SET status='pausado', pause_start=? WHERE id=?",
            (now, shift_id),
        )


def resume_shift(shift_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
        if not row or not row["pause_start"]:
            conn.execute("UPDATE shifts SET status='activo', pause_start=NULL WHERE id=?", (shift_id,))
            return
        pause_start_dt = datetime.fromisoformat(row["pause_start"])
        extra = int((datetime.utcnow() - pause_start_dt).total_seconds())
        new_paused = row["paused_seconds"] + extra
        conn.execute(
            "UPDATE shifts SET status='activo', pause_start=NULL, paused_seconds=? WHERE id=?",
            (new_paused, shift_id),
        )


def end_shift(shift_id: int) -> Optional[sqlite3.Row]:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()
        if not row:
            return None
        paused = row["paused_seconds"]
        if row["status"] == "pausado" and row["pause_start"]:
            pause_start_dt = datetime.fromisoformat(row["pause_start"])
            paused += int((datetime.utcnow() - pause_start_dt).total_seconds())
        conn.execute(
            "UPDATE shifts SET status='finalizado', end_time=?, paused_seconds=?, pause_start=NULL WHERE id=?",
            (now, paused, shift_id),
        )
        return conn.execute("SELECT * FROM shifts WHERE id=?", (shift_id,)).fetchone()


def elapsed_seconds(shift: sqlite3.Row) -> int:
    start = datetime.fromisoformat(shift["start_time"])
    paused = shift["paused_seconds"]
    if shift["status"] == "finalizado" and shift["end_time"]:
        end = datetime.fromisoformat(shift["end_time"])
        total = (end - start).total_seconds()
    elif shift["status"] == "pausado" and shift["pause_start"]:
        pause_start = datetime.fromisoformat(shift["pause_start"])
        total = (pause_start - start).total_seconds()
    else:
        total = (datetime.utcnow() - start).total_seconds()
    return max(0, int(total) - paused)


# ------------------------------------------------------------------ #
#  Activities                                                          #
# ------------------------------------------------------------------ #

def create_activity(
    user_id: str,
    username: str,
    guild_id: str,
    badge_number: str,
    description: str,
    image_urls: list[str],
) -> int:
    import json as _json
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO activities
               (user_id, username, guild_id, badge_number, description, image_urls, registered_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente')""",
            (user_id, username, guild_id, badge_number, description, _json.dumps(image_urls), now),
        )
        return cur.lastrowid


def get_activity(activity_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM activities WHERE id=?", (activity_id,)
        ).fetchone()


def update_activity_message(activity_id: int, message_id: str, channel_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE activities SET message_id=?, channel_id=? WHERE id=?",
            (message_id, channel_id, activity_id),
        )


def update_activity_status(
    activity_id: int, status: str, reviewer_name: str, reviewer_id: str
) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE activities SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
            (status, f"{reviewer_name} ({reviewer_id})", now, activity_id),
        )


def get_pending_activities() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM activities WHERE status='pendiente' AND message_id IS NOT NULL"
        ).fetchall()


# ------------------------------------------------------------------ #
#  Tickets y postulaciones                                             #
# ------------------------------------------------------------------ #

def create_ticket(
    guild_id: str,
    user_id: str,
    username: str,
    channel_id: str,
    ticket_type: str,
) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO tickets (guild_id, user_id, username, channel_id, ticket_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, username, channel_id, ticket_type, now),
        )
        return cur.lastrowid


def get_open_ticket(guild_id: str, user_id: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """SELECT * FROM tickets
               WHERE guild_id=? AND user_id=? AND status='abierto'
               ORDER BY id DESC LIMIT 1""",
            (guild_id, user_id),
        ).fetchone()


def close_ticket(channel_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tickets SET status='cerrado' WHERE channel_id=? AND status='abierto'",
            (channel_id,),
        )


def create_application(
    guild_id: str,
    user_id: str,
    username: str,
    answers: dict[str, str],
) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO applications (guild_id, user_id, username, answers, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, user_id, username, json.dumps(answers, ensure_ascii=False), now),
        )
        return cur.lastrowid


# ------------------------------------------------------------------ #
#  Guild Config (Canales y configuración por servidor)                 #
# ------------------------------------------------------------------ #

def get_guild_config(guild_id: str) -> Optional[sqlite3.Row]:
    """Obtiene la configuración de un servidor."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)
        ).fetchone()


def set_guild_config(
    guild_id: str,
    channel_solicitudes: Optional[str] = None,
    channel_aceptadas: Optional[str] = None,
    channel_rechazadas: Optional[str] = None,
    channel_logs: Optional[str] = None,
    welcome_message: Optional[str] = None,
) -> None:
    """Actualiza la configuración de un servidor."""
    with get_connection() as conn:
        # Obtener configuración actual
        current = conn.execute(
            "SELECT * FROM guild_config WHERE guild_id=?", (guild_id,)
        ).fetchone()
        
        if current:
            # Actualizar solo los campos proporcionados
            updates = {}
            if channel_solicitudes is not None:
                updates["channel_solicitudes"] = channel_solicitudes
            if channel_aceptadas is not None:
                updates["channel_aceptadas"] = channel_aceptadas
            if channel_rechazadas is not None:
                updates["channel_rechazadas"] = channel_rechazadas
            if channel_logs is not None:
                updates["channel_logs"] = channel_logs
            if welcome_message is not None:
                updates["welcome_message"] = welcome_message
            
            if updates:
                set_clause = ", ".join(f"{k}=?" for k in updates.keys())
                values = list(updates.values()) + [guild_id]
                conn.execute(
                    f"UPDATE guild_config SET {set_clause} WHERE guild_id=?",
                    values,
                )
        else:
            # Insertar nueva configuración
            conn.execute(
                """INSERT INTO guild_config
                   (guild_id, channel_solicitudes, channel_aceptadas, channel_rechazadas, channel_logs, welcome_message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_solicitudes, channel_aceptadas, channel_rechazadas, channel_logs, welcome_message),
            )


def set_guild_channel(guild_id: str, channel_key: str, channel_id: Optional[str]) -> None:
    """Actualiza un canal de guild_config, permitiendo limpiarlo con None."""
    allowed = {
        "channel_solicitudes",
        "channel_aceptadas",
        "channel_rechazadas",
        "channel_logs",
        "channel_support_panel",
        "channel_application_panel",
        "channel_applications",
        "ticket_category",
    }
    if channel_key not in allowed:
        raise ValueError(f"Canal no permitido: {channel_key}")

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
            (guild_id,),
        )
        conn.execute(
            f"UPDATE guild_config SET {channel_key}=? WHERE guild_id=?",
            (channel_id, guild_id),
        )


def get_channel_solicitudes(guild_id: str) -> Optional[str]:
    """Obtiene el canal de solicitudes de un servidor."""
    config = get_guild_config(guild_id)
    return config["channel_solicitudes"] if config else None


def get_channel_aceptadas(guild_id: str) -> Optional[str]:
    """Obtiene el canal de solicitudes aceptadas de un servidor."""
    config = get_guild_config(guild_id)
    return config["channel_aceptadas"] if config else None


def get_channel_rechazadas(guild_id: str) -> Optional[str]:
    """Obtiene el canal de solicitudes rechazadas de un servidor."""
    config = get_guild_config(guild_id)
    return config["channel_rechazadas"] if config else None


def get_channel_logs(guild_id: str) -> Optional[str]:
    """Obtiene el canal de logs administrativos de un servidor."""
    config = get_guild_config(guild_id)
    return config["channel_logs"] if config and "channel_logs" in config.keys() else None


def get_welcome_message(guild_id: str) -> Optional[str]:
    """Obtiene el mensaje de bienvenida personalizado."""
    config = get_guild_config(guild_id)
    return config["welcome_message"] if config else None
