from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from config import DATABASE_URL, DEFAULT_DAILY_LIMIT, DEFAULT_PRICE_USD


def _conn():
    return psycopg2.connect(DATABASE_URL)


def init_db() -> None:
    conn = _conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id BIGINT PRIMARY KEY,
        balance NUMERIC(12,2) NOT NULL DEFAULT 0,
        is_allowed BOOLEAN NOT NULL DEFAULT FALSE,
        is_banned BOOLEAN NOT NULL DEFAULT FALSE,
        daily_limit INT NOT NULL DEFAULT %s,
        daily_count INT NOT NULL DEFAULT 0,
        daily_date DATE NOT NULL DEFAULT CURRENT_DATE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """, (DEFAULT_DAILY_LIMIT,))

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_logs(
        id SERIAL PRIMARY KEY,
        admin_id BIGINT NOT NULL,
        action TEXT NOT NULL,
        payload JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        amount NUMERIC(12,2) NOT NULL,
        kind TEXT NOT NULL, -- 'topup','deduct','adjust'
        note TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS topup_requests(
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        amount NUMERIC(12,2) NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', -- pending/approved/rejected
        admin_id BIGINT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        decided_at TIMESTAMP
    )
    """)

    # Prepared for future provider integration (not implemented here)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        country TEXT NOT NULL DEFAULT 'UK',
        service_code TEXT NOT NULL DEFAULT 'UK_SERVICE',
        sell_price NUMERIC(12,2) NOT NULL,
        provider_order_id TEXT,
        phone_number TEXT,
        status TEXT NOT NULL DEFAULT 'created', -- created/waiting/received/cancelled/refunded
        sms_code TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """)

    _set_default(cur, "price_usd", str(DEFAULT_PRICE_USD))
    _set_default(cur, "maintenance", "0")
    _set_default(cur, "start_message", DEFAULT_START_MESSAGE())

    conn.commit()
    cur.close()
    conn.close()


def _set_default(cur, key: str, value: str) -> None:
    cur.execute("SELECT key FROM settings WHERE key=%s", (key,))
    if not cur.fetchone():
        cur.execute("INSERT INTO settings(key,value) VALUES(%s,%s)", (key, value))


def DEFAULT_START_MESSAGE() -> str:
    return (
        "👋 أهلاً بك في بوت الأرقام التجريبية\n\n"
        "يتيح لك هذا البوت الحصول على رقم مؤقت 🇬🇧 بسرعة وسهولة، مع إمكانية متابعة حالة الطلب "
        "واستلام كود التفعيل مباشرة داخل البوت.\n\n"
        "💰 يعتمد البوت على نظام رصيد داخلي، حيث يتم خصم 0.50$ لكل رقم يتم طلبه.\n"
        "📩 يمكنك في أي وقت متابعة الأرقام التي قمت بطلبها من قسم طلباتي وتحديث حالة الرسائل الواردة.\n\n"
        "اختر أحد الخيارات من الأزرار أدناه للمتابعة:"
    )


# ---------- Settings ----------
def get_setting(key: str) -> Optional[str]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings(key,value,updated_at)
        VALUES(%s,%s,NOW())
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
    """, (key, value))
    conn.commit()
    cur.close()
    conn.close()


def get_price_usd() -> float:
    v = get_setting("price_usd")
    try:
        return float(v) if v is not None else DEFAULT_PRICE_USD
    except Exception:
        return DEFAULT_PRICE_USD


def is_maintenance() -> bool:
    return get_setting("maintenance") == "1"


def get_start_message() -> str:
    v = get_setting("start_message")
    return v if v else DEFAULT_START_MESSAGE()


# ---------- Users ----------
@dataclass
class User:
    user_id: int
    balance: float
    is_allowed: bool
    is_banned: bool
    daily_limit: int
    daily_count: int
    daily_date: date


def ensure_user(user_id: int) -> User:
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id) VALUES(%s)", (user_id,))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        row = cur.fetchone()

    user = User(
        user_id=int(row["user_id"]),
        balance=float(row["balance"]),
        is_allowed=bool(row["is_allowed"]),
        is_banned=bool(row["is_banned"]),
        daily_limit=int(row["daily_limit"]),
        daily_count=int(row["daily_count"]),
        daily_date=row["daily_date"],
    )

    cur.close()
    conn.close()
    return user


def set_allowed(user_id: int, allowed: bool) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_allowed=%s, updated_at=NOW() WHERE user_id=%s", (allowed, user_id))
    conn.commit()
    cur.close()
    conn.close()


def set_banned(user_id: int, banned: bool) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_banned=%s, updated_at=NOW() WHERE user_id=%s", (banned, user_id))
    conn.commit()
    cur.close()
    conn.close()


def set_daily_limit(user_id: int, limit: int) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET daily_limit=%s, updated_at=NOW() WHERE user_id=%s", (limit, user_id))
    conn.commit()
    cur.close()
    conn.close()


def reset_daily_if_needed(user_id: int) -> None:
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT daily_date FROM users WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return
    if row["daily_date"] != date.today():
        cur.execute("""
            UPDATE users SET daily_date=CURRENT_DATE, daily_count=0, updated_at=NOW()
            WHERE user_id=%s
        """, (user_id,))
        conn.commit()
    cur.close()
    conn.close()


def increment_daily(user_id: int) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET daily_count=daily_count+1, updated_at=NOW() WHERE user_id=%s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


# ---------- Balance / Transactions ----------
def add_balance(user_id: int, amount: float, kind: str, note: str | None = None) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users(user_id,balance)
        VALUES(%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET balance = users.balance + EXCLUDED.balance, updated_at=NOW()
    """, (user_id, amount))
    cur.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(%s,%s,%s,%s)",
                (user_id, amount, kind, note))
    conn.commit()
    cur.close()
    conn.close()


def deduct_balance(user_id: int, amount: float, kind: str, note: str | None = None) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance=balance-%s, updated_at=NOW() WHERE user_id=%s", (amount, user_id))
    cur.execute("INSERT INTO transactions(user_id,amount,kind,note) VALUES(%s,%s,%s,%s)",
                (user_id, -abs(amount), kind, note))
    conn.commit()
    cur.close()
    conn.close()


# ---------- Topup Requests ----------
def create_topup_request(user_id: int, amount: float) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO topup_requests(user_id,amount) VALUES(%s,%s) RETURNING id", (user_id, amount))
    req_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return int(req_id)


def list_pending_topups(limit: int = 20) -> List[Tuple]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, amount, created_at
        FROM topup_requests
        WHERE status='pending'
        ORDER BY id ASC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def decide_topup(req_id: int, admin_id: int, approve: bool) -> Optional[Tuple[int, float]]:
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM topup_requests WHERE id=%s AND status='pending'", (req_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return None

    status = "approved" if approve else "rejected"
    cur.execute("""
        UPDATE topup_requests
        SET status=%s, admin_id=%s, decided_at=NOW()
        WHERE id=%s
    """, (status, admin_id, req_id))
    conn.commit()
    user_id = int(row["user_id"])
    amount = float(row["amount"])
    cur.close()
    conn.close()
    return (user_id, amount)


# ---------- Admin Logs ----------
def admin_log(admin_id: int, action: str, payload: Dict[str, Any] | None = None) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO admin_logs(admin_id,action,payload) VALUES(%s,%s,%s)",
                (admin_id, action, json.dumps(payload or {})))
    conn.commit()
    cur.close()
    conn.close()


# ---------- Stats ----------
def stats_today() -> Dict[str, Any]:
    conn = _conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM transactions WHERE created_at::date = CURRENT_DATE")
    tx_count = int(cur.fetchone()[0])

    cur.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE created_at::date = CURRENT_DATE")
    sum_amount = float(cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM users")
    users_count = int(cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM users WHERE updated_at::date = CURRENT_DATE")
    active_today = int(cur.fetchone()[0])

    cur.close()
    conn.close()
    return {
        "tx_count": tx_count,
        "sum_amount": sum_amount,
        "users_count": users_count,
        "active_today": active_today,
    }


# ---------- User listing (for broadcast) ----------
def list_user_ids_nonbanned() -> List[int]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE is_banned=FALSE")
    ids = [int(r[0]) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return ids
