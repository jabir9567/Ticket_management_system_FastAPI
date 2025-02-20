# app/database.py
from motor.motor_asyncio import AsyncIOMotorClient
from decouple import config

MONGO_DETAILS = config("MONGO_URI", default="mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_DETAILS)
database = client.event_ticketing

# Define your collections
users_collection = database.get_collection("users")
events_collection = database.get_collection("events")
tickets_collection = database.get_collection("tickets")
promos_collection = database.get_collection("promos")
seats_collection = database.get_collection("seats")
