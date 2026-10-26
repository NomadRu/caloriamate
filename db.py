import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def upsert_user(tg_id: int, username: str | None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO users (id, username) VALUES (%s, %s)
                   ON CONFLICT (id) DO UPDATE SET username = EXCLUDED.username""",
                (tg_id, username)
            )
        conn.commit()

def get_partner(tg_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT partner_id FROM users WHERE id = %s", (tg_id,))
            row = cur.fetchone()
            return row["partner_id"] if row else None

def link_partners(a: int, b: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET partner_id = %s WHERE id = %s", (b, a))
            cur.execute("UPDATE users SET partner_id = %s WHERE id = %s", (a, b))
        conn.commit()

def save_meal(user_id: int, dish: str, kcal100: int, grams: int, plates: float):
    total = round(plates * (grams / 100) * kcal100)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meals (user_id, dish_name, kcal_per_100g, grams_per_plate, plates, total_kcal)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user_id, dish, kcal100, grams, plates, total)
            )
        conn.commit()
    return total

def stats(user_id: int, since_iso: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(total_kcal), 0) FROM meals WHERE user_id = %s AND created_at >= %s",
                (user_id, since_iso)
            )
            return int(cur.fetchone()[0])
