"""
Stripe billing integration — checkout + webhooks.
Flow: Customer clicks "Buy" → Stripe Checkout → Payment → Webhook → API key generated.
"""

import os
import stripe
from .auth import key_store

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
DOMAIN = os.environ.get("DOMAIN", "https://drmadmeow.up.railway.app")

# Price IDs — set these in Railway env vars, or defaults
PRICE_IDS = {
    "pro": os.environ.get("STRIPE_PRICE_PRO", "price_1TZfqJHMkYtoDU24yPATdwHt"),
    "team": os.environ.get("STRIPE_PRICE_TEAM", "price_1TZft1HMkYtoDU24ogtfAbqL"),
    "business": os.environ.get("STRIPE_PRICE_BUSINESS", "price_1TZfw3HMkYtoDU24U9ngLp6y"),
}


async def create_checkout_session(plan: str = "pro") -> dict:
    """Create a Stripe Checkout session for a plan purchase.
    
    Returns {"url": "https://checkout.stripe.com/..."}
    """
    if not stripe.api_key or stripe.api_key == "":
        raise ValueError("STRIPE_SECRET_KEY not configured")
    
    price_id = PRICE_IDS.get(plan, PRICE_IDS["pro"])
    
    session = stripe.checkout.Session.create(
        line_items=[{
            "price": price_id,
            "quantity": 1,
        }],
        mode="subscription",
        success_url=f"{DOMAIN}/v1/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{DOMAIN}/#pricing",
        metadata={"plan": plan},
        allow_promotion_codes=True,
    )
    
    return {"url": session.url, "session_id": session.id}


async def handle_webhook(payload: bytes, signature: str) -> dict:
    """Process a Stripe webhook event. On checkout.session.completed, 
    generates an API key and stores it for the success page.
    """
    if not WEBHOOK_SECRET:
        return {"status": "error", "message": "Webhook secret not configured"}
    
    try:
        event = stripe.Webhook.construct_event(payload, signature, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        return {"status": "error", "message": "Invalid signature"}
    
    # Handle checkout completion
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        plan = session.get("metadata", {}).get("plan", "pro")
        customer_email = session.get("customer_details", {}).get("email", "unknown")
        
        # Generate API key
        key_name = f"stripe-{customer_email}"[:32]
        api_key = await key_store.create(key_name, plan)
        
        # Store mapping so success page can find it
        from .auth import DATA_DIR
        import json
        mapping_path = DATA_DIR / "stripe_sessions.json"
        mappings = {}
        if mapping_path.exists():
            mappings = json.loads(mapping_path.read_text())
        mappings[session["id"]] = {
            "api_key": api_key,
            "plan": plan,
            "email": customer_email,
        }
        mapping_path.write_text(json.dumps(mappings))
        
        return {"status": "ok", "plan": plan, "email": customer_email}
    
    return {"status": "ignored", "type": event["type"]}


async def get_key_for_session(session_id: str) -> dict | None:
    """Retrieve the API key generated for a Stripe session."""
    from .auth import DATA_DIR
    import json
    mapping_path = DATA_DIR / "stripe_sessions.json"
    if mapping_path.exists():
        mappings = json.loads(mapping_path.read_text())
        return mappings.get(session_id)
    return None
