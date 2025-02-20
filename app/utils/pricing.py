# app/utils/pricing.py
from typing import List, Optional, Dict, Any
from app.database import promos_collection
from datetime import datetime, timezone

def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

async def calculate_total_price(
    seats: List[Dict[str, Any]],
    event_pricing: Dict[str, float],  # e.g. {'VIP': event.vip_price, 'Standard': event.standard_price}
    dynamic_pricing_multiplier: Optional[float] = None,
    promo_code: Optional[str] = None,
    cancellation_insurance: bool = False
) -> Dict[str, Any]:
    """
    Calculate the total price for the selected seats.
    """
    # Base price calculation using event-specific pricing
    base_price = sum(event_pricing.get(seat.get("seat_type", "Standard"), 50.0) for seat in seats)
    
    final_price = base_price
    discount_applied = 0.0

    # Apply dynamic pricing multiplier if provided
    if dynamic_pricing_multiplier is not None:
        final_price *= dynamic_pricing_multiplier

    # Apply group discount (10% discount if booking 4 or more seats)
    if len(seats) >= 4:
        group_discount = 0.10 * final_price
        final_price -= group_discount
        discount_applied += group_discount

    # Handle promo code validation and application
    if promo_code:
        now = datetime.now(timezone.utc)  # Ensure UTC-aware datetime
        promo = await promos_collection.find_one({"code": promo_code})

        if not promo or not promo.get("active", False):
            raise ValueError("Promo code is no longer active.")

        expiry = promo.get("expiry")
        if expiry:
            expiry = ensure_utc(expiry)

        if (expiry and expiry < now) or (promo.get("current_usage", 0) >= promo.get("max_usage", 0)):
            await promos_collection.update_one({"code": promo_code}, {"$set": {"active": False}})
            raise ValueError("Promo code is no longer active.")

        discount_type = promo.get("discount_type", "percentage")
        discount_value = promo.get("discount_value", 0)

        promo_discount = (discount_value / 100.0) * final_price if discount_type == "percentage" else discount_value
        promo_discount = min(promo_discount, final_price)  # Avoid over-discounting

        final_price -= promo_discount
        discount_applied += promo_discount

    return {
        "base_price": base_price,
        "total_cost": round(final_price, 2),
        "discount_applied": round(discount_applied, 2),
        "promo_code": promo_code,
        "dynamic_pricing_multiplier": dynamic_pricing_multiplier,
        "cancellation_insurance": cancellation_insurance
    }
