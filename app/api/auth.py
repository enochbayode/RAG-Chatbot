import jwt
import os
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

# JWT Secret Key
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") 

    
def verify_token_http(credentials: HTTPAuthorizationCredentials):
    token = credentials.credentials  # Extract the actual token string
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        if payload.get("id") is None:  # Check if the token contains a valid 'id'
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

