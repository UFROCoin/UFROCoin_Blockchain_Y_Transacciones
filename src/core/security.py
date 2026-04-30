import os
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

# --- Configuracion de Seguridad ---

security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET", "ufrocoin-secret-cambiar-en-produccion")
ALGORITHM = "HS256"

# --- Validacion de Propiedad ---

def verify_wallet_owner(address: str, auth: HTTPAuthorizationCredentials = Depends(security)):
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de autorización. Usa el botón 'Authorize' en Swagger para ingresar tu JWT o 'test-token'."
        )

    if auth.credentials == "test-token":
        return address

    try:
        payload = jwt.decode(auth.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        
        token_address = payload.get("wallet_address")
        
        if not token_address or token_address != address:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para ver el historial de esta wallet"
            )
            
        return token_address
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado"
        )