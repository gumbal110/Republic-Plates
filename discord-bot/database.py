import sqlite3
import logging
import random
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "discord-bot/placas_rd.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS plate_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL,
                username    TEXT    NOT NULL,
                reason      TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pendiente',
                plate       TEXT,
                reviewed_by TEXT,
                reviewer_name TEXT,
                reject_reason TEXT,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plates (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                plate       TEXT    NOT NULL UNIQUE,
                user_id     TEXT    NOT NULL,
                username    TEXT    NOT NULL,
                request_id  INTEGER NOT NULL REFERENCES plate_requests(id),
                issued_at   TEXT    NOT NULL,
                revoked     INTEGER NOT NULL DEFAULT 0,
                revoked_at  TEXT,
                revoked_by  TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT    NOT NULL,
                actor_id    TEXT    NOT NULL,
                actor_name  TEXT    NOT NULL,
                target_id   TEXT,
                target_name TEXT,
                details     TEXT,
                created_at  TEXT    NOT NULL
            );
        """)
    logger.info("Base de datos inicializada.")


def generate_unique_plate() -> str:
    with get_connection() as conn:
        for _ in range(100):
            number = random.randint(1000, 9999)
            plate = f"RD-{number}"
            exists = conn.execute(
                "SELECT 1 FROM plates WHERE plate = ?", (plate,)
            ).fetchone()
            if not exists:
                return plate
    raise RuntimeError("No se pudo generar una placa única después de 100 intentos.")


def create_request(user_id: str, username: str, reason: str) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO plate_requests (user_id, username, reason, status, created_at, updated_at)
               VALUES (?, ?, ?, 'pendiente', ?, ?)""",
            (user_id, username, reason, now, now),
        )
        return cur.lastrowid


def get_pending_requests() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM plate_requests WHERE status = 'pendiente' ORDER BY created_at ASC"
        ).fetchall()


def get_request(request_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM plate_requests WHERE id = ?", (request_id,)
        ).fetchone()


def approve_request(request_id: int, reviewer_id: str, reviewer_name: str) -> str:
    now = datetime.utcnow().isoformat()
    plate = generate_unique_plate()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM plate_requests WHERE id = ? AND status = 'pendiente'",
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError("Solicitud no encontrada o ya procesada.")
        conn.execute(
            """UPDATE plate_requests
               SET status='aprobada', plate=?, reviewed_by=?, reviewer_name=?, updated_at=?
               WHERE id=?""",
            (plate, reviewer_id, reviewer_name, now, request_id),
        )
        conn.execute(
            """INSERT INTO plates (plate, user_id, username, request_id, issued_at)
               VALUES (?, ?, ?, ?, ?)""",
            (plate, row["user_id"], row["username"], request_id, now),
        )
        log_action(
            conn,
            action="APROBACION_PLACA",
            actor_id=reviewer_id,
            actor_name=reviewer_name,
            target_id=row["user_id"],
            target_name=row["username"],
            details=f"Placa asignada: {plate} | Solicitud ID: {request_id}",
        )
    return plate


def reject_request(
    request_id: int, reviewer_id: str, reviewer_name: str, reason: str
) -> sqlite3.Row:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM plate_requests WHERE id = ? AND status = 'pendiente'",
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError("Solicitud no encontrada o ya procesada.")
        conn.execute(
            """UPDATE plate_requests
               SET status='rechazada', reviewed_by=?, reviewer_name=?, reject_reason=?, updated_at=?
               WHERE id=?""",
            (reviewer_id, reviewer_name, reason, now, request_id),
        )
        log_action(
            conn,
            action="RECHAZO_PLACA",
            actor_id=reviewer_id,
            actor_name=reviewer_name,
            target_id=row["user_id"],
            target_name=row["username"],
            details=f"Motivo: {reason} | Solicitud ID: {request_id}",
        )
        return row


def get_user_plates(user_id: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM plates WHERE user_id = ? AND revoked = 0 ORDER BY issued_at DESC",
            (user_id,),
        ).fetchall()


def lookup_plate(plate: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM plates WHERE plate = ?", (plate.upper(),)
        ).fetchone()


def revoke_plate(plate: str, revoker_id: str, revoker_name: str) -> sqlite3.Row:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM plates WHERE plate = ? AND revoked = 0", (plate.upper(),)
        ).fetchone()
        if not row:
            raise ValueError("Placa no encontrada o ya revocada.")
        conn.execute(
            "UPDATE plates SET revoked=1, revoked_at=?, revoked_by=? WHERE plate=?",
            (now, revoker_id, plate.upper()),
        )
        log_action(
            conn,
            action="REVOCACION_PLACA",
            actor_id=revoker_id,
            actor_name=revoker_name,
            target_id=row["user_id"],
            target_name=row["username"],
            details=f"Placa revocada: {plate.upper()}",
        )
        return row


def get_user_requests(user_id: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM plate_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,),
        ).fetchall()


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


def get_stats() -> dict:
    with get_connection() as conn:
        total_plates = conn.execute("SELECT COUNT(*) FROM plates WHERE revoked=0").fetchone()[0]
        total_requests = conn.execute("SELECT COUNT(*) FROM plate_requests").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM plate_requests WHERE status='pendiente'"
        ).fetchone()[0]
        approved = conn.execute(
            "SELECT COUNT(*) FROM plate_requests WHERE status='aprobada'"
        ).fetchone()[0]
        rejected = conn.execute(
            "SELECT COUNT(*) FROM plate_requests WHERE status='rechazada'"
        ).fetchone()[0]
    return {
        "total_plates": total_plates,
        "total_requests": total_requests,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
    }
