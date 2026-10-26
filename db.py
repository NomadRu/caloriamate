import os
import psycopg2

URL = os.getenv("DATABASE_URL")

def conn():
    return psycopg2.connect(URL)

def save_user(tg_id, username):
    with conn() as c, c.cursor() as cur:
        cur.execute("INSERT INTO users (id, username) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET username = EXCLUDED.username", (tg_id, username))

def get_partner(tg_id):
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT partner_id FROM users WHERE id = %s", (tg_id,))
        row = cur.fetchone()
        return row[0] if row else None

def link_partners(a, b):
    with conn() as c, c.cursor() as cur:
        cur.execute("UPDATE users SET partner_id = %s WHERE id = %s", (b, a))
        cur.execute("UPDATE users SET partner_id = %s WHERE id = %s", (a, b))

def save_meal(uid, dish, kcal100, grams, plates):
    total = round(plates * (grams / 100) * kcal100)
    with conn() as c, c.cursor() as cur:
        cur.execute("INSERT INTO meals (user_id, dish_name, kcal_per_100g, grams_per_plate, plates, total_kcal) VALUES (%s, %s, %s, %s, %s, %s)", (uid, dish, kcal100, grams, plates, total))
    return total

def get_stats(uid, since):
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(total_kcal), 0) FROM meals WHERE user_id = %s AND created_at >= %s", (uid, since))
        return int(cur.fetchone()[0])
