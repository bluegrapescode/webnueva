import asyncio, os, uuid
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import jwt
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
MONGO = os.environ["MONGO_URL"]; DB = os.environ["DB_NAME"]
SECRET = os.environ.get("JWT_SECRET", "devsecret"); ALGO = "HS256"

def now(): return datetime.now(timezone.utc).isoformat()
def nid(): return uuid.uuid4().hex
def tok(uid): return jwt.encode({"sub": uid, "exp": datetime.now(timezone.utc)+timedelta(days=7)}, SECRET, algorithm=ALGO)

async def ensure_user(db, sid, name):
    u = await db.users.find_one({"steam_id": sid})
    if u: return u["id"]
    uid = nid()
    await db.users.insert_one({"id": uid, "steam_id": sid, "persona_name": name,
        "avatar": "https://api.dicebear.com/7.x/adventurer/svg?seed="+name, "role": "user",
        "coins": 2000, "vip_coins": 500, "created_at": now(), "last_login": now()})
    return uid

async def add_inv(db, uid, item_id, name, category, rarity, tier, qty, image):
    await db.inventory.insert_one({"id": nid(), "user_id": uid, "item_id": item_id, "name": name,
        "category": category, "rarity": rarity, "image": image, "tier": tier, "quantity": qty, "acquired_at": now()})

async def main():
    cli = AsyncIOMotorClient(MONGO); db = cli[DB]
    # demo user (user A)
    a = await db.users.find_one({"steam_id": "demo_0000000001"})
    a_id = a["id"] if a else await ensure_user(db, "demo_0000000001", "Demo Survivor")
    await db.users.update_one({"id": a_id}, {"$set": {"vip_coins": 500}})
    b_id = await ensure_user(db, "demo_0000000002", "Demo Trader")
    await db.users.update_one({"id": b_id}, {"$set": {"vip_coins": 500}})
    # clear their tradeable inventory to keep the test deterministic
    await db.inventory.delete_many({"user_id": {"$in": [a_id, b_id]}, "category": {"$in": ["Eggs", "Skins", "Crates"]}})
    IMG = "https://images.unsplash.com/photo-1502082553048-f009c37129b9?w=200"
    # A's items
    await add_inv(db, a_id, "egg_common", "Huevo Común", "Eggs", "Common", "common", 3, IMG)
    await add_inv(db, a_id, "skin_verde", "Skin Verde Selva", "Skins", "Rare", None, 1, IMG)
    # B's items
    await add_inv(db, b_id, "egg_rare", "Huevo Raro", "Eggs", "Rare", "rare", 5, IMG)
    await add_inv(db, b_id, "crate_bronce", "Cofre Bronce", "Crates", "Common", None, 2, IMG)
    print("A_ID", a_id); print("B_ID", b_id)
    print("A_TOKEN", tok(a_id)); print("B_TOKEN", tok(b_id))
    cli.close()

asyncio.run(main())
