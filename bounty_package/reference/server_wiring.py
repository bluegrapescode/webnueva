# Sistema Global de Bounties (bounty.py): selección server-side, validación de
# muerte atómica/idempotente, desconexión con gracia, ciclo automático, WS + Discord.
import bounty


async def _bounty_online_players():
    """Roster de jugadores online para el motor de bounties. Devuelve None cuando
    NO hay servidor de juego real conectado (RCON/mod offline) -> bounty.py entra
    en modo simulación para el preview."""
    if not (rcon_client.is_configured() or game_ipc.mod_alive()):
        return None
    ids, _names = await _rcon_online_players()
    _counts, _unknown, details = await asyncio.to_thread(game_tele.population, ids)
    return [{"sid": str(d.get("steam_id")), "name": d.get("name"),
             "species": d.get("species"), "slug": d.get("slug"), "alive": True}
            for d in details if d.get("steam_id")]


async def _bounty_resolve_user_id(sid: str):
    if not sid:
        return None
    u = await db.users.find_one({"steam_id": str(sid)}, {"_id": 0, "id": 1})
    return u["id"] if u else None


async def _bounty_user_info(uid: str):
    if not uid:
        return None
    u = await db.users.find_one({"id": uid}, {"_id": 0})
    if not u:
        return None
    return {"steam_id": u.get("steam_id"), "name": u.get("persona_name"),
            "avatar": u.get("avatar"), "coins": u.get("coins", 0), "vip_coins": u.get("vip_coins", 0)}


async def _bounty_charge_wallet(uid: str, prime: int, amber: int, ref: str) -> bool:
    """Cobro atómico: solo descuenta si hay saldo suficiente en ambas monedas."""
    prime, amber = int(prime or 0), int(amber or 0)
    q = {"id": uid}
    if prime:
        q["coins"] = {"$gte": prime}
    if amber:
        q["vip_coins"] = {"$gte": amber}
    res = await db.users.update_one(q, {"$inc": {"coins": -prime, "vip_coins": -amber}})
    if res.modified_count != 1:
        return False
    if prime:
        await add_transaction(uid, "normal", -prime, "spend", ref)
    if amber:
        await add_transaction(uid, "vip", -amber, "spend", ref)
    return True


async def _bounty_refund_wallet(uid: str, prime: int, amber: int, ref: str):
    prime, amber = int(prime or 0), int(amber or 0)
    inc = {}
    if prime:
        inc["coins"] = prime
    if amber:
        inc["vip_coins"] = amber
    if inc:
        await db.users.update_one({"id": uid}, {"$inc": inc})
    if prime:
        await add_transaction(uid, "normal", prime, "refund", ref)
    if amber:
        await add_transaction(uid, "vip", amber, "refund", ref)


async def _bounty_award_reward(user_id: str, prime: int, amber: int, xp: int, ref: str):
    """Entrega recompensa a la billetera web. PrimeMeat -> coins, Amberium -> vip_coins,
    EXP -> XP del Pase de Batalla."""
    inc = {}
    if prime:
        inc["coins"] = int(prime)
    if amber:
        inc["vip_coins"] = int(amber)
    if inc:
        await db.users.update_one({"id": user_id}, {"$inc": inc})
    if prime:
        await add_transaction(user_id, "normal", int(prime), "reward", ref)
    if amber:
        await add_transaction(user_id, "vip", int(amber), "reward", ref)
    if xp:
        try:
            await battle_pass._add_xp(user_id, int(xp), ref)
        except Exception as e:
            logger.warning("[bounty] xp grant failed: %r", e)


def _bounty_ingame_grant(sid: str, prime: int, amber: int, xp: int):
    """Intento best-effort de entregar los items dentro del juego vía comando al
    mod. Se ignora silenciosamente cuando el servidor de juego está offline."""
    try:
        game_ipc.write_game_command({
            "action": "bounty_reward", "steamid": str(sid),
            "prime_meat": int(prime), "amberium": int(amber), "experience": int(xp)})
    except Exception:
        pass


bounty.configure(
    db, admin_ids=ADMIN_STEAM_IDS, online_provider=_bounty_online_players,
    resolve_user_id=_bounty_resolve_user_id, user_info=_bounty_user_info,
    charge_wallet=_bounty_charge_wallet, refund_wallet=_bounty_refund_wallet,
    award_reward=_bounty_award_reward, ingame_grant=_bounty_ingame_grant,
    jwt_secret=JWT_SECRET, jwt_algo=JWT_ALGO)
app.include_router(bounty.build_router(get_current_user, get_admin_user), prefix="/api")
