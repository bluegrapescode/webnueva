"""Seed rico del clan demo (Escuadron Prueba / TEST) para que el Hub luzca como el mockup:
miembros con roles de colores, chat de conversación, invitar jugadores, invitaciones y solicitudes.
Idempotente: se puede correr varias veces. Uso: python3 /app/backend/_seed_clan_demo.py
"""
import asyncio, os, uuid
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


def nid():
    return uuid.uuid4().hex


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


AV = lambda n: f"https://i.pravatar.cc/120?img={n}"

RANKS = [
    {"id": "leader", "name": "Líder", "order": 0,
     "perms": {k: True for k in ["edit_clan", "manage_ranks", "assign_ranks", "invite", "kick", "manage_members"]}},
    {"id": "comandante", "name": "Comandante", "order": 1,
     "perms": {"edit_clan": False, "manage_ranks": False, "assign_ranks": True, "invite": True, "kick": True, "manage_members": True}},
    {"id": "oficial", "name": "Oficial", "order": 1,
     "perms": {"edit_clan": False, "manage_ranks": False, "assign_ranks": False, "invite": True, "kick": True, "manage_members": False}},
    {"id": "veterano", "name": "Veterano", "order": 2,
     "perms": {"edit_clan": False, "manage_ranks": False, "assign_ranks": False, "invite": True, "kick": False, "manage_members": False}},
    {"id": "cazador", "name": "Cazador", "order": 3, "perms": {}},
    {"id": "member", "name": "Miembro", "order": 5, "perms": {}},
]

# persona, steam, rank, level, avatar_img
MEMBERS = [
    ("Xirow", "seed_xirow", "comandante", 35, 12),
    ("Luna", "seed_luna", "veterano", 28, 45),
    ("DarkRex", "seed_darkrex", "oficial", 40, 33),
    ("Maya", "seed_maya", "member", 22, 47),
    ("BlueHunter", "seed_bluehunter", "cazador", 30, 15),
    ("RaptorsPR", "seed_raptorspr", "veterano", 33, 8),
    ("NeonCL", "seed_neoncl", "cazador", 27, 52),
    ("AztecX", "seed_aztecx", "member", 19, 60),
    ("VolcanDino", "seed_volcandino", "member", 24, 11),
    ("SelvaCO", "seed_selvaco", "oficial", 37, 3),
    ("CieloISLA", "seed_cieloisla", "cazador", 31, 7),
    ("TitanGG", "seed_titangg", "member", 26, 68),
    ("EmberX", "seed_emberx", "veterano", 29, 50),
    ("OnyxPro", "seed_onyxpro", "member", 21, 51),
]

# persona, steam, level, avatar_img, status  (status: online/partida/ausente)
POOL = [
    ("Nova", "seed_nova", 28, 5, "online"),
    ("CrisPR", "seed_crispr", 31, 51, "online"),
    ("ShadowPR", "seed_shadowpr", 32, 59, "partida"),
    ("RaptorQueen", "seed_raptorqueen", 38, 44, "online"),
    ("TTV_Killer", "seed_ttvkiller", 45, 68, "ausente"),
    ("CrosFight", "seed_crosfight", 29, 13, "online"),
    ("Zylux", "seed_zylux", 35, 60, "ausente"),
]

MESSAGES = [
    (None, "Sistema", "RaptorsPR se ha unido al clan.", True),
    ("__leader__", None, "Todos a Highland, necesitan apoyo.", False),
    ("Xirow", None, "Ya vamos, 8 jugadores en camino.", False),
    ("Luna", None, "Cuiden el flanco norte.", False),
    ("DarkRex", None, "En 2 minutos llegamos.", False),
    (None, "Sistema", "Maya puso un marcador en el mapa.", True),
    ("Maya", None, "Reunámonos en Delta después de capturar.", False),
    ("BlueHunter", None, "Voy con 3 más.", False),
]


async def ensure_user(db, persona, steam, level, img, status):
    now = datetime.now(timezone.utc)
    coins = max(0, (level - 1)) * 50000
    last_login = now if status == "online" else (now - timedelta(hours=6))
    doc = {
        "persona_name": persona, "avatar": AV(img), "coins": coins,
        "last_login": iso(last_login),
        "active_dino": ({"species": "raptor"} if status == "partida" else None),
    }
    existing = await db.users.find_one({"steam_id": steam}, {"_id": 0, "id": 1})
    if existing:
        await db.users.update_one({"steam_id": steam}, {"$set": doc})
        return existing["id"]
    uid = nid()
    doc.update({"id": uid, "steam_id": steam, "vip_coins": 0, "role": "user", "created_at": iso(now)})
    await db.users.insert_one(doc)
    return uid


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    clan = await db.clans.find_one({"tag": "TEST"}, {"_id": 0})
    if not clan:
        print("No existe el clan demo TEST. Abortando.")
        return
    cid = clan["id"]
    leader_id = clan["leader_id"]
    print("Clan demo:", clan["name"], cid, "líder:", leader_id[:8])

    # 1) Ranks personalizados
    await db.clans.update_one({"id": cid}, {"$set": {"ranks": RANKS}})

    # 2) Miembros con roles
    name_to_id = {}
    for persona, steam, rank, level, img in MEMBERS:
        uid = await ensure_user(db, persona, steam, level, img, "online")
        name_to_id[persona] = uid
        await db.clan_members.update_one(
            {"user_id": uid},
            {"$set": {"clan_id": cid, "user_id": uid, "rank_id": rank, "name": persona,
                      "avatar": AV(img), "joined_at": iso(datetime.now(timezone.utc))}},
            upsert=True,
        )

    # 3) Pool de jugadores (para invitar / invitaciones / solicitudes)
    pool_ids = {}
    for persona, steam, level, img, status in POOL:
        uid = await ensure_user(db, persona, steam, level, img, status)
        pool_ids[persona] = uid
        # asegurarse de que NO estén en ningún clan
        await db.clan_members.delete_many({"user_id": uid})

    # 4) Chat: limpiar y sembrar conversación del mockup
    await db.clan_messages.delete_many({"clan_id": cid})
    base = datetime.now(timezone.utc) - timedelta(minutes=len(MESSAGES) + 1)
    for i, (who, sysname, text, is_sys) in enumerate(MESSAGES):
        ts = base + timedelta(minutes=i)
        if is_sys:
            uid, name = None, sysname
        elif who == "__leader__":
            uid, name = leader_id, (await db.users.find_one({"id": leader_id}, {"_id": 0, "persona_name": 1}) or {}).get("persona_name", "Líder")
        else:
            uid, name = name_to_id[who], who
        await db.clan_messages.insert_one({
            "id": nid(), "clan_id": cid, "user_id": uid, "name": name,
            "text": text, "system": is_sys, "created_at": iso(ts),
        })

    # 5) Invitaciones pendientes (sent_invites)
    await db.clan_invites.delete_many({"clan_id": cid})
    now = datetime.now(timezone.utc)
    for persona, mins in [("TTV_Killer", 5), ("ShadowPR", 12), ("RaptorQueen", 25)]:
        await db.clan_invites.update_one(
            {"clan_id": cid, "user_id": pool_ids[persona]},
            {"$set": {"id": nid(), "clan_id": cid, "user_id": pool_ids[persona],
                      "invited_by": leader_id, "created_at": iso(now - timedelta(minutes=mins))}},
            upsert=True,
        )

    # 6) Solicitudes para unirse (join_requests)
    await db.clan_requests.delete_many({"clan_id": cid})
    for persona, hrs, img in [("CrosFight", 1, 13), ("Zylux", 3, 60)]:
        await db.clan_requests.update_one(
            {"clan_id": cid, "user_id": pool_ids[persona]},
            {"$set": {"id": nid(), "clan_id": cid, "user_id": pool_ids[persona],
                      "name": persona, "avatar": AV(img),
                      "created_at": iso(now - timedelta(hours=hrs))}},
            upsert=True,
        )

    # 7) Contadores del clan + notoriedad para nivel/XP visibles
    total = await db.clan_members.count_documents({"clan_id": cid})
    await db.clans.update_one({"id": cid}, {"$set": {"member_count": total, "notoriety": 74450, "territories_display": 3}})

    # 8) Liberar zonas que tuviera el clan de jugador (para dejar el chat limpio de turf)
    await db.turf_zones.update_many(
        {"owner_clan_id": cid},
        {"$set": {"owner_clan_id": None, "owner_since": None, "contest_clan_id": None, "contest_progress": 0}},
    )

    print("Miembros totales:", total)
    print("Mensajes:", await db.clan_messages.count_documents({"clan_id": cid}))
    print("Invitaciones:", await db.clan_invites.count_documents({"clan_id": cid}))
    print("Solicitudes:", await db.clan_requests.count_documents({"clan_id": cid}))
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
