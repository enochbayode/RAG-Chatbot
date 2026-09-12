# API's for PDF upload

import os
from dotenv import load_dotenv
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from google.cloud import storage  # Import Google Cloud Storage
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.vector_db import upsert_organization_document, upsert_global_document
from app.models.document import Document
from app.models.organization import AppResource 
from app.api.auth import verify_token_http
import time 

load_dotenv()

# Initialize FastAPI Router
router = APIRouter()

# Initialize Google Cloud Storage Client
storage_client = storage.Client()
BUCKET_NAME = os.getenv(
    "BUCKET_NAME"
)  

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
http_bearer = HTTPBearer()

# Endpoint for uploading organizations resources 
@router.post("/upload/organization/")
async def upload_organization_pdf(
    organization_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer)
):
    """
    Uploads a PDF to Google Cloud Storage under an organization-specific directory.
    
    - `organization_id`: Organization ID.
    - `file`: The PDF file to upload.
    """
    payload = verify_token_http(credentials)
    if payload is None:
        return {"error": "Payload verification failed", "status_code": 401}
    
    try:
        # Ensure filename is unique
        timestamp = int(time.time())
        filename = f"{timestamp}_{file.filename}"
        gcs_path = f"organization/{organization_id}/pdfs/{filename}"

        # Upload file to Google Cloud Storage
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(gcs_path)
        file.file.seek(0)
        blob.upload_from_file(file.file, content_type=file.content_type)
        file_url = blob.public_url

        # Store document metadata in PostgreSQL
        new_doc = Document(
            organization_id=organization_id,
            file_name=file.filename,
            file_url=file_url
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        # Generate embeddings
        await upsert_organization_document(db, organization_id, str(new_doc.chat_bot_resource_id))

        return {
            "message": "Organization PDF uploaded successfully.",
            "document_id": new_doc.chat_bot_resource_id,
            "file_url": file_url,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error uploading organization document: {str(e)}"
        )


# Endpoint for uploading telepractice-pro resources 
@router.post("/upload/global/")
async def upload_global_pdf(
    organization_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Uploads a PDF to Google Cloud Storage under the global directory.
    
    - `file`: The PDF file to upload.
    """
    try:
        # Ensure filename is unique
        timestamp = int(time.time())
        filename = f"{timestamp}_{file.filename}"
        gcs_path = f"global/pdfs/{filename}"

        # Upload file to Google Cloud Storage
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(gcs_path)
        file.file.seek(0)
        blob.upload_from_file(file.file, content_type=file.content_type)
        file_url = blob.public_url

        # Store document metadata in PostgreSQL
        new_doc = AppResource(
            organization_id=organization_id,
            file_name=file.filename,
            file_url=file_url
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        # Generate embeddings
        await upsert_global_document(db, organization_id, str(new_doc.app_resource_id))

        return {
            "message": "Global PDF uploaded successfully.",
            "document_id": new_doc.app_resource_id,
            "file_url": file_url
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error uploading global document: {str(e)}"
        )
