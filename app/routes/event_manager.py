# app/routes/event_manager.py
from urllib import request
from fastapi import APIRouter, HTTPException, Depends
from app.models.event import EventCreate, Event
from app.models.promo import PromoCreate, Promo
from app.database import events_collection, promos_collection, seats_collection
from app.utils.auth_utils import get_current_user
import uuid
from typing import Union, List

router = APIRouter()

@router.post("/create-event", response_model=Event)
async def create_event(event: EventCreate, user=Depends(get_current_user)):
    # Ensure only event managers can create events
    if user["role"] != "manager":
        raise HTTPException(status_code=403, detail="Only managers can create events")

    event_data = event.model_dump()
    event_data["id"] = str(uuid.uuid4())

    # Insert event into the events collection
    await events_collection.insert_one(event_data)

    # Insert seats into the seats collection using the new format
    seat_list = []
    for seat_number, seat_type in event_data["seats"].items():
        seat_list.append({
            "seat_number": seat_number,
            "seat_type": seat_type,
            "status": "available",  # Default status
            "event_id": event_data["id"]
        })

    await seats_collection.insert_many(seat_list)
    
    return Event(**event_data)


@router.post("/create-promo", response_model=Promo)
async def create_promo(promo: PromoCreate, user=Depends(get_current_user)):
    """Create a new promo code (only for event managers)."""
    if user["role"] != "manager":
        raise HTTPException(status_code=403, detail="Only managers can create promo codes")

    existing_promo = await promos_collection.find_one({"code": promo.code})
    if existing_promo:
        raise HTTPException(status_code=400, detail="Promo code already exists.")

    promo_data = promo.model_dump()
    promo_data["id"] = str(uuid.uuid4())
    promo_data["created_by"] = user["id"]  # Store which manager created it
    await promos_collection.insert_one(promo_data)

    return Promo(**promo_data)


@router.get("/create-promo", response_model=List[Promo])
async def get_promos(user=Depends(get_current_user)):
    """Retrieve all promo codes created by the logged-in manager."""
    if user["role"] != "manager":
        raise HTTPException(status_code=403, detail="Only managers can view promo codes")

    promos = await promos_collection.find({"created_by": user["id"]}).to_list(length=100)
    return [Promo(**promo) for promo in promos]