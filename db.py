import os
from supabase import create_client

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def upsert_user(tg_id: int, username: str | None):
    sb.table("users").upsert({"id": tg_id, "username": username}).execute()

def get_partner(tg_id: int):
    res = sb.table("users").select("partner_id").eq("id", tg_id).execute()
    return res.data[0]["partner_id"] if res.data else None

def link_partners(a: int, b: int):
    sb.table("users").update({"partner_id": b}).eq("id", a).execute()
    sb.table("users").update({"partner_id": a}).eq("id", b).execute()

def save_meal(user_id: int, dish, kcal100, grams, plates):
    total = round(plates * (grams / 100) * kcal100)
    sb.table("meals").insert({
        "user_id": user_id, "dish_name": dish,
        "kcal_per_100g": kcal100, "grams_per_plate": grams,
        "plates": plates, "total_kcal": total
    }).execute()
    return total

def stats(user_id: int, since_sql: str):
    res = sb.table("meals").select("total_kcal") \
        .eq("user_id", user_id).gte("created_at", since_sql).execute()
    return sum(r["total_kcal"] for r in res.data)
