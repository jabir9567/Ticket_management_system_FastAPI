from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime

class EventBase(BaseModel):
    event_id: str
    title: str
    description: Optional[str]
    date: datetime
    location: str
    vip_price: float         # New field for VIP ticket price
    standard_price: float  

class Seat(BaseModel):
    seat_number: str
    seat_type: str  # "VIP" or "Standard"
    status: str     # "available", "reserved", "booked"

class EventCreate(EventBase):
    # Updated: now a dict mapping seat number to seat type string
    seats: Dict[str, str]

class Event(EventBase):
    id: str
    # Updated: seats is a mapping from seat number to seat type string
    seats: Dict[str, str]

    class Config:
        orm_mode = True
