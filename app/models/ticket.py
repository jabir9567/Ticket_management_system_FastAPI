# app/models/ticket.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TicketBase(BaseModel):
    event_id: str
    user_id: str
    seats: List[str]
    total_cost: float
    status: str  # "reserved", "booked", "cancelled"
    reserved_at: datetime

class TicketCreate(TicketBase):
    pass

class Ticket(TicketBase):
    id: str

    class Config:
        orm_mode = True

class ReservationRequest(BaseModel):
    seat_numbers: List[str]
    promo_code: Optional[str] = None
    dynamic_pricing_multiplier: Optional[float] = None
    cancellation_insurance: bool = False