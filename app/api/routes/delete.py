from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.vector_db import delete_document
from app.models.document import Document
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

@router.delete("/delete/{organization_id}/{document_id}")
async def delete_pdf(organization_id: str, document_id: str, db: Session = Depends(get_db)):
    """
    Deletes a PDF by calling `delete_document`, ensuring it belongs to the organization.
    """
    # Verify the document exists and belongs to the organization
    doc = (
        db.query(Document)
        .filter(
            Document.chat_bot_resource_id == document_id,
            Document.organization_id == organization_id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    await delete_document(db, organization_id, document_id)

    # Call the central delete function
    return {
            "message": "PDF deleted successfully.",
            "organization_id": organization_id,
            "document_id": document_id
        }
