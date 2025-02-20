# app/main.py
from fastapi import FastAPI
from app.routes import auth, event_manager, customer

app = FastAPI(title="Event Ticketing System")

# Include routers with appropriate prefixes
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(event_manager.router, prefix="/manager", tags=["Event Manager"])
app.include_router(customer.router, prefix="/customer", tags=["Customer"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
