import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
MONGO = os.environ["MONGO_URL"]; DB = os.environ["DB_NAME"]

async def main():
    cli = AsyncIOMotorClient(MONGO); db = cli[DB]
    ids = ["3c45966b9bbf4bf59035ebae8237faa4", "96dffc3fe0de4217a969e56f2eec716f"]
    r = await db.trade_sessions.delete_many({})
    await db.users.update_many({"id": {"$in": ids}},
        {"$set": {"trade_amber_sent": 0, "trade_amber_day": "", "last_item_trade_at": None}})
    print("sessions_cleared", r.deleted_count, "cooldowns_reset", ids)
    cli.close()

asyncio.run(main())
