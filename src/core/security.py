import os
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET", "ufrocoin-secret-cambiar-en-produccion")
ALGORITHM = "HS256"

def verify_wallet_owner(address: str, auth: HTTPAuthorizationCredentials = Security(security)):
    """
    Dependencia para validar que el token JWT pertenece al dueño de la wallet solicitada.
    """
    try:
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        
        token_address = payload.get("wallet_address")
        
        if not token_address or token_address != address:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para acceder al historial de esta wallet"
            )
            
        return token_address
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado"
        )