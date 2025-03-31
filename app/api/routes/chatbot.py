# app/api/routes/chatbot.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.rag import generate_response  
from app.api.auth import verify_token_http

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
http_bearer = HTTPBearer()

@router.post("/chat/")
async def chatbot(
    organization_id: str, 
    query: str, 
    db: Session = Depends(get_db), 
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer)
    ):
    
    """
    Handles chatbot interaction.
    - `org_id`: The organization ID to ensure multi-tenancy.
    - `query`: The user's question.
    """

    payload = verify_token_http(credentials)
    if payload is None:
        return {"error": "Payload verification failed", "status_code": 401}


    # Generate response using the RAG pipeline
    response = await generate_response(query, organization_id)

    if not response:
        raise HTTPException(
            status_code=404,
            detail="No relevant information found for this organization.",
        )

    return {"response": response}
