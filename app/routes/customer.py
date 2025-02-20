# app/routes/customer.py
import asyncio
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from app.models.ticket import ReservationRequest, TicketCreate, Ticket
from app.database import tickets_collection, seats_collection, promos_collection, events_collection
from app.utils.auth_utils import get_current_user
from app.utils.pricing import calculate_total_price
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from pydantic import BaseModel
from bson import ObjectId
from fastapi.encoders import jsonable_encoder


router = APIRouter()
def customer_required(user=Depends(get_current_user)):
    if user.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Only customers can perform this action")
    return user

def convert_objectid_to_str(document):
    """Convert ObjectId fields in a MongoDB document to strings."""
    if isinstance(document, dict):
        return {k: str(v) if isinstance(v, ObjectId) else v for k, v in document.items()}
    return document


@router.post("/reserve")
async def reserve_ticket(
    event_id: str,
    request: ReservationRequest,
    background_tasks: BackgroundTasks,
    user=Depends(customer_required)
):
    # 1. Check if seats are available
    available_seats = await seats_collection.find({
        "event_id": event_id,
        "seat_number": {"$in": request.seat_numbers},
        "status": "available"
    }).to_list(length=len(request.seat_numbers))

    if len(available_seats) != len(request.seat_numbers):
        raise HTTPException(
            status_code=400,
            detail="One or more selected seats are no longer available."
        )

    # 2. Mark seats as reserved
    for seat in request.seat_numbers:
        await seats_collection.update_one(
            {"event_id": event_id, "seat_number": seat},
            {"$set": {"status": "reserved"}}
        )
        
        # 3. Retrieve event pricing details
    event = await events_collection.find_one({"id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event_pricing = {
        "VIP": event["vip_price"],
        "Standard": event["standard_price"]
    }

    # 3. Calculate pricing (including promo discount if applicable)
    pricing_details = await calculate_total_price(
        seats=available_seats,
        event_pricing=event_pricing,
        dynamic_pricing_multiplier=request.dynamic_pricing_multiplier,
        promo_code=request.promo_code,
        cancellation_insurance=request.cancellation_insurance
    )

    # 4. Save reservation in MongoDB (a reservation is a Ticket document with status "reserved")
    reservation_id = str(uuid.uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=1)

    reservation_data = {
        "id": reservation_id,
        "user_id": user["id"],
        "event_id": event_id,
        "seat_numbers": request.seat_numbers,
        "pricing_details": pricing_details,
        "expiry": expiry,
        "status": "reserved",
        "cancellation_insurance": request.cancellation_insurance
    }

    await tickets_collection.insert_one(reservation_data)

    # 5. Schedule a background task to expire the reservation if not confirmed in 1 minute
    background_tasks.add_task(expire_reservation, reservation_id)

    return {
        "reservation_id": reservation_id,
        "pricing_details": pricing_details,
        "reservation_expiry": expiry.isoformat()
    }


async def expire_reservation(reservation_id: str):
    """Background task to remove expired reservations."""
    await asyncio.sleep(60)  # Wait for 60 seconds

    # Query the reservation from the DB
    reservation = await tickets_collection.find_one({"id": reservation_id})
    if reservation and reservation["status"] == "reserved":
        # Release seats back to available
        for seat in reservation["seat_numbers"]:
            await seats_collection.update_one(
                {"event_id": reservation["event_id"], "seat_number": seat},
                {"$set": {"status": "available"}}
            )
        # Remove the expired reservation
        await tickets_collection.delete_one({"id": reservation_id})


class ConfirmTicketRequest(BaseModel):
    reservation_id: str
    payment_status: str



@router.post("/confirm")
async def confirm_ticket(request: ConfirmTicketRequest, user=Depends(customer_required)):
    # Retrieve the reservation that belongs to the customer
    reservation = await tickets_collection.find_one({"id": request.reservation_id, "user_id": user["id"]})
    if not reservation:
        raise HTTPException(
            status_code=400,
            detail="Reservation expired or does not exist. Please restart your booking."
        )

    # If payment not completed, release seats and remove the reservation
    if request.payment_status.lower() != "payment done":
        for seat in reservation["seat_numbers"]:
            await seats_collection.update_one(
                {"event_id": reservation["event_id"], "seat_number": seat},
                {"$set": {"status": "available"}}
            )
        await tickets_collection.delete_one({"id": request.reservation_id})
        raise HTTPException(
            status_code=400,
            detail="Payment not completed. Reservation cancelled."
        )

    # Payment successful: mark seats as booked
    for seat in reservation["seat_numbers"]:
        await seats_collection.update_one(
            {"event_id": reservation["event_id"], "seat_number": seat},
            {"$set": {"status": "booked"}}
        )

    # If a promo code was applied, check if it is active and increment its usage
    if (promo_code := reservation["pricing_details"].get("promo_code")):
        promo = await promos_collection.find_one({"code": promo_code})
        if promo and promo.get("active", False):
            await promos_collection.update_one(
                {"code": promo_code},
                {"$inc": {"current_usage": 1}}
            )

    # Update the reservation to a confirmed booking
    update_fields = {
        "status": "booked",
        "reserved_at": datetime.now(timezone.utc)
    }
    await tickets_collection.update_one({"id": request.reservation_id}, {"$set": update_fields})

    ticket_data = await tickets_collection.find_one({"id": request.reservation_id})
    # Convert ObjectId to string before returning
    if ticket_data and "_id" in ticket_data:
        ticket_data["_id"] = str(ticket_data["_id"])
    return {"message": "Ticket booked successfully.", "ticket": jsonable_encoder(ticket_data)}


class CancelRequest(BaseModel):
    ticket_id: str

@router.post("/cancel")
async def cancel_ticket(request: CancelRequest, user=Depends(customer_required)):
    ticket_id = request.ticket_id

    # Retrieve ticket ensuring it belongs to the customer and is confirmed (booked)
    ticket = await tickets_collection.find_one({"id": ticket_id, "user_id": user["id"]})

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    if ticket["status"] != "booked":
        raise HTTPException(status_code=400, detail="Only confirmed tickets can be cancelled.")

    # Release each seat back to available
    for seat in ticket["seat_numbers"]:
        await seats_collection.update_one(
            {"event_id": ticket["event_id"], "seat_number": seat},
            {"$set": {"status": "available"}}
        )

    # Calculate cancellation fee and refund
    cancellation_fee = 0 if ticket.get("cancellation_insurance", False) else ticket["pricing_details"]["total_cost"] * 0.15
    refund = ticket["pricing_details"]["total_cost"] - cancellation_fee

    # Mark the ticket as cancelled
    await tickets_collection.update_one({"id": ticket_id}, {"$set": {"status": "cancelled"}})

    # Decrement promo usage if a promo code was applied
    if "promo_code" in ticket["pricing_details"]:
        await promos_collection.update_one(
            {"code": ticket["pricing_details"]["promo_code"]},
            {"$inc": {"current_usage": -1}}
        )

    # Ensure any reserved record is removed
    await tickets_collection.delete_many({"id": ticket_id, "status": "reserved"})

    return {
        "status": "cancelled",
        "refund_amount": round(refund, 2),
        "cancellation_fee": round(cancellation_fee, 2)
    }

@router.get("/history/{event_id}")
async def booking_history(event_id: str, user=Depends(customer_required)):
    # Retrieve all tickets for the customer for the specified event
    history = await tickets_collection.find(
        {"event_id": event_id, "user_id": user["id"]}
    ).to_list(length=100)

    # Convert ObjectId fields to string before returning
    return [convert_objectid_to_str(ticket) for ticket in history]

@router.get("/event-seats/{event_id}")
async def get_event_seats(event_id: str, user=Depends(get_current_user)):
    # Fetch all seats for the event
    seats = await seats_collection.find(
        {"event_id": event_id}
    ).to_list(length=1000)
    return [{
        "seat_number": seat["seat_number"],
        "seat_type": seat["seat_type"],
        "status": seat["status"]
    } for seat in seats]
