from fastapi import FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
import jwt


app = FastAPI()

# JWT Secret Key
JWT_SECRET_KEY = "1234888888"  # Use the secret key used for generating the token

    
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

