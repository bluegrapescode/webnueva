"""The stripe v15 SDK returns objects that are NOT dicts (no .get, no keys,
dict(obj) fails). battle_pass._plain() flattens them at the three boundaries
(catalog scan, session re-fetch, webhook event). This test runs against the
REAL pinned SDK when it is installed and skips cleanly when it is not, so the
rest of the battery stays independent of the library."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_plain_flattens_real_stripe_objects():
    try:
        import stripe
    except Exception:
        import pytest
        pytest.skip("stripe not installed locally")
    import battle_pass as bp

    ev = stripe.StripeObject.construct_from(
        {"id": "evt_1", "type": "checkout.session.completed",
         "data": {"object": {"id": "cs_1", "payment_status": "paid",
                             "metadata": {"user_id": "u1", "season": "2026-08",
                                          "tier": "regular"}}}}, None)
    d = bp._plain(ev)
    assert isinstance(d, dict)
    assert (d.get("data") or {}).get("object", {}).get("metadata", {}).get("season") == "2026-08"

    sess = stripe.StripeObject.construct_from(
        {"id": "cs_1", "payment_status": "paid", "metadata": {"tier": "premium_plus"}}, None)
    p = bp._plain(sess)
    assert p.get("payment_status") == "paid"
    assert p.get("metadata", {}).get("tier") == "premium_plus"

    prod = stripe.StripeObject.construct_from(
        {"id": "prod_1", "metadata": {"bp_product_key": "bp_regular"}}, None)
    assert (bp._plain(prod).get("metadata") or {}).get("bp_product_key") == "bp_regular"

    assert bp._plain({"a": 1}) == {"a": 1}
    assert bp._plain(None) == {}
