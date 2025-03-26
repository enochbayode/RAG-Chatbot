import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.vector_db import delete_organization_document, delete_global_document
from app.models.document import Document
from app.models.organization import AppResource
from dotenv import load_dotenv
from app.api.auth import verify_token_http

load_dotenv()

router = APIRouter()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
http_bearer = HTTPBearer()



@router.delete("/organization/delete/{organization_id}/{document_id}")
async def delete_organization_pdf(
    organization_id: str, 
    document_id: str, 
    db: Session = Depends(get_db), 
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer)
):
    """
    Deletes an organization's PDF document, ensuring it belongs to the organization.
    """

    payload = verify_token_http(credentials)

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
        raise HTTPException(
            status_code=404, detail="Document not found or access denied"
        )

    # Perform document deletion
    await delete_organization_document(db, organization_id, document_id)

    return {
        "message": "Organization PDF deleted successfully.",
        "organization_id": organization_id,
        "document_id": document_id,
    }


@router.delete("/global/delete/{organization_id}/{document_id}")
async def delete_global_pdf(
    organization_id: str,
    document_id: str, 
    db: Session = Depends(get_db)   
):
    """
    Deletes a global PDF document without requiring an organization ID.
    """
    # Verify the document exists in the global storage
    doc = (
        db.query(AppResource)
        .filter(
            AppResource.app_resource_id == document_id,
            AppResource.organization_id == organization_id
            )
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=404, detail="Global document not found"
        )

    # Perform document deletion
    await delete_global_document(db, organization_id, document_id)

    return {
        "message": "Global PDF deleted successfully.",
        "organization_id": organization_id,
        "document_id": document_id
    }
