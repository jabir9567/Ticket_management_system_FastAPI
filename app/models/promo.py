# app/models/promo.py
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Union

class PromoBase(BaseModel):
    code: str
    discount_type: str  # "percentage" or "fixed"
    discount_value: float
    expiry: datetime
    max_usage: int
    current_usage: int = 0
    active: bool = True
    
    @field_validator('discount_type')
    def validate_discount_type(cls, v):
        if v not in ["percentage", "fixed"]:
            raise ValueError("discount_type must be either 'percentage' or 'fixed'")
        return v
    
class PromoCreate(PromoBase):
    pass

class Promo(PromoBase):
    id: str

    class Config:
        orm_mode = True
