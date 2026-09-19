            except Exception as e:
                logger.warning("[bp] hook failed: %r", e)
        # Sistema de Bounties: una muerte PVP validada por el log del juego puede
        # completar el bounty activo (killer != target, atómico e idempotente).
        try:
            if k.get("killer_sid") and k.get("victim_sid"):
                await bounty.on_kill(str(k["killer_sid"]), str(k["victim_sid"]))
        except Exception as e:
            logger.warning("[bounty] on_kill hook failed: %r", e)
    try:
        await battle_pass.periodic()
