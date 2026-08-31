import asyncio, os, uuid
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ["DB_NAME"]]
A = "3c45966b9bbf4bf59035ebae8237faa4"  # Demo Survivor
B = "96dffc3fe0de4217a969e56f2eec716f"  # Demo Trader

def iso(): return datetime.now(timezone.utc).isoformat()

def snap(doc, qty):
    return {"inv_id": doc["id"], "qty": qty, "item_id": doc.get("item_id"),
            "name": doc["name"], "image": doc.get("image"), "category": doc["category"],
            "rarity": doc.get("rarity"), "tier": doc.get("tier")}

async def main():
    a = await db.users.find_one({"id": A}); b = await db.users.find_one({"id": B})
    a_egg = await db.inventory.find_one({"user_id": A, "item_id": "egg_common"})
    a_skin = await db.inventory.find_one({"user_id": A, "item_id": "skin_verde"})
    b_egg = await db.inventory.find_one({"user_id": B, "item_id": "egg_rare"})
    b_crate = await db.inventory.find_one({"user_id": B, "item_id": "crate_bronce"})
    await db.trade_sessions.delete_many({})
    sid = uuid.uuid4().hex
    sess = {
        "id": sid, "a_id": A, "a_name": a.get("persona_name"), "a_avatar": a.get("avatar"),
        "b_id": B, "b_name": b.get("persona_name"), "b_avatar": b.get("avatar"),
        "a_offer": {"items": [snap(a_egg, 2), snap(a_skin, 1)], "amber": 150},
        "b_offer": {"items": [snap(b_egg, 3), snap(b_crate, 1)], "amber": 0},
        "a_locked": True, "b_locked": False, "a_confirmed": False, "b_confirmed": False,
        "status": "active", "created_at": iso(), "updated_at": iso(),
    }
    await db.trade_sessions.insert_one(sess)
    print("SESSION", sid)
    cli.close()

asyncio.run(main())
