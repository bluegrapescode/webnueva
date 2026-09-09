"""Seed de ejemplo para el Catálogo de Skins (agrupadas por dino, con Stripe)."""
import asyncio, os, uuid
from datetime import datetime, timezone
import stripe
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ["DB_NAME"]]

IMG = {
  "rex_obsidian": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/f3077d352819c721696bbcc2c1465862c1dd51084ed2f8cedd08c5e0700f3178.jpeg",
  "rex_crimson": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/e697e0bc2f6292630e2d2854681d6ce550139f7d4bb3addae6997c4092e0a210.jpeg",
  "raptor_frost": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/572dcc266ee3f13e1d9da7fd177214e17fdf42e695a6efebcea36b0ee39dda9f.jpeg",
  "raptor_sable": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/9dcb2be574a440ec8aa3e60edfc51748dd843bdf926a722897072240e498d1f3.jpeg",
  "spino_toxic": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/5a9740a677aa85c8a61e17a892090eca7d4485a0f4a040c034c265fec3f9f0c0.jpeg",
  "spino_glacier": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/ebfc8a3aaf3d8d8003b3840739c0bec78d97153f13495bd01941dedeae90d680.jpeg",
  "cerato_sandstorm": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/2c364cc3a38387df59bc38032ead35889a9b072bfa7b1e289754f425816b0163.jpeg",
  "cerato_razor": "https://static.prod-images.emergentagent.com/jobs/306794df-9995-4a77-8b12-a03738746894/images/6fa8fb7f97e03e6e5b60e6a69a55fd6bce0301470ef2089ecdeb0588e42d4628.jpeg",
}

# (name, dino, slug, rarity, price_usd, skin_type, section)
SKINS = [
  ("Obsidian", "Tyrannosaurus Rex", "rex_obsidian", "legendary", 12.99, "Élite", "destacados"),
  ("Crimson Fade", "Tyrannosaurus Rex", "rex_crimson", "epic", 12.99, "Evento", "destacados"),
  ("Frostbite", "Austroraptor", "raptor_frost", "rare", 9.99, "Clásica", "diario"),
  ("Sable", "Austroraptor", "raptor_sable", "uncommon", 9.99, "Clásica", "diario"),
  ("Toxic Abyss", "Spinosaurus", "spino_toxic", "legendary", 11.49, "Élite", "destacados"),
  ("Glacier", "Spinosaurus", "spino_glacier", "epic", 11.49, "Evento", "diario"),
  ("Sandstorm", "Ceratosaurus", "cerato_sandstorm", "rare", 8.99, "Clásica", "diario"),
  ("Razor", "Ceratosaurus", "cerato_razor", "epic", 8.99, "Evento", "temporada"),
]

def iso(): return datetime.now(timezone.utc).isoformat()

async def main():
    created = 0
    for name, dino, slug, rarity, price, stype, section in SKINS:
        if await db.shop_skins.find_one({"name": name, "dino_species": dino}):
            print("skip (exists):", name, dino); continue
        skin_id = uuid.uuid4().hex
        cents = int(round(price * 100))
        product = stripe.Product.create(name=f"Skin {name} — {dino}", metadata={"skin_id": skin_id})
        price_obj = stripe.Price.create(product=product.id, unit_amount=cents, currency="usd", metadata={"skin_id": skin_id})
        await db.shop_skins.insert_one({
            "id": skin_id, "name": name, "description": f"Skin {rarity} para {dino}.",
            "image_url": IMG[slug], "rarity": rarity, "section": section,
            "dino_species": dino, "skin_type": stype, "price_cents": cents, "currency": "usd",
            "skin_data": None, "start_at": None, "end_at": None, "active": True,
            "stripe_product_id": product.id, "stripe_price_id": price_obj.id,
            "created_at": iso(), "created_by": "seed_catalog",
        })
        created += 1
        print("created:", name, dino, f"${price}")
    print("TOTAL created:", created)
    cli.close()

asyncio.run(main())
