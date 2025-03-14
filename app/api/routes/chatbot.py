# app/api/routes/chatbot.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services.rag import generate_response  # Use RAG for retrieval + response

router = APIRouter()


@router.post("/chat/")
async def chatbot(organization_id: str, query: str, db: Session = Depends(get_db)):
    """
    Handles chatbot interaction.
    - `org_id`: The organization ID to ensure multi-tenancy.
    - `query`: The user's question.
    """
    # Generate response using the RAG pipeline
    response = generate_response(query, organization_id)

    if not response:
        raise HTTPException(
            status_code=404,
            detail="No relevant information found for this organization.",
        )

    return {"response": response}
