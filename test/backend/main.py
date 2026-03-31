from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
import hashlib
import jwt
import datetime

# --- Configuración Inicial ---
app = FastAPI(title="UFROCoin PoC API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = MongoClient("mongodb://localhost:27017/")
db = client["ufrocoin_poc"]
collection = db["test_data"]

SECRET_KEY = "ufrocoin_poc_secret_key"
ALGORITHM = "HS256"

# --- Modelos de Datos ---
class LoginRequest(BaseModel):
    username: str

class TestData(BaseModel):
    message: str

# --- Utilidades ---
def generate_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def create_jwt_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Dependencias ---
def verify_token(authorization: str = Header(...)):
    try:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Formato de token inválido")
        
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

# --- Endpoints de API ---
@app.post("/auth/login")
def login(request: LoginRequest):
    user_hash = generate_hash(request.username)
    token = create_jwt_token({"sub": request.username, "wallet_hash": user_hash})
    
    return {
        "access_token": token,
        "wallet_hash": user_hash
    }

@app.post("/test/db")
def save_to_db(data: TestData, current_user: dict = Depends(verify_token)):
    document = {
        "username": current_user["sub"],
        "wallet_hash": current_user["wallet_hash"],
        "message": data.message,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    
    result = collection.insert_one(document)
    
    return {
        "status": "success",
        "inserted_id": str(result.inserted_id)
    }