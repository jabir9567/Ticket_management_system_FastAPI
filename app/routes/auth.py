# app/routes/auth.py
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.user import UserCreate, User, Token
from app.utils.auth_utils import create_access_token
from datetime import timedelta
from app.database import users_collection
from passlib.context import CryptContext
import uuid
from pydantic import BaseModel

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

@router.post("/register", response_model=User)
async def register(user: UserCreate):
    # Check if username or email already exists
    existing_user = await users_collection.find_one({"$or": [{"username": user.username}, {"email": user.email}]})
    
    if existing_user:
        if existing_user["username"] == user.username:
            raise HTTPException(status_code=400, detail="Username already taken.")
        if existing_user["email"] == user.email:
            raise HTTPException(status_code=400, detail="Email already registered.")
    
    # If no user exists with the same username/email, proceed with registration
    user_data = user.model_dump()
    user_data["id"] = str(uuid.uuid4())
    user_data["password"] = get_password_hash(user.password)

    # Validate role
    if user.role not in ["customer", "manager"]:
        raise HTTPException(status_code=400, detail="Invalid role. Role must be 'customer' or 'manager'.")
    
    # Insert into MongoDB
    await users_collection.insert_one(user_data)
    
    return User(**user_data)

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest):
    # Fetch user from DB and verify password
    user = await users_collection.find_one({"username": credentials.username})
    if not user or not pwd_context.verify(credentials.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(data={"sub": credentials.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}