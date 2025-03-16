# API for PDF upload

# app/api/routes/upload.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from google.cloud import storage  # Import Google Cloud Storage
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.vector_db import upsert_document
from app.models.document import Document

import os
from dotenv import load_dotenv

load_dotenv()

# Initialize FastAPI Router
router = APIRouter()

# Initialize Google Cloud Storage Client
storage_client = storage.Client()
BUCKET_NAME = os.getenv(
    "BUCKET_NAME"
)  # Ensure this is set in your environment variables


@router.post("/upload/")
async def upload_pdf(
    organization_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """
    Uploads a PDF to Google Cloud Storage, stores the file URL in PostgreSQL,
    and indexes embeddings in Pinecone.
    - `org_id`: Organization ID for multi-tenancy.
    - `file`: The PDF file to upload.
    """
    try:
        # Upload file to Google Cloud Storage
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(
            f"{organization_id}/{file.filename}"
        )  # Store PDFs in an org-specific folder
        file.file.seek(0)  # Reset file pointer before upload
        blob.upload_from_file(file.file, content_type=file.content_type)
        file_url = blob.public_url  # Get the public URL of the uploaded file

        # Ensure `organization_id` is clean
        org_id_cleaned = os.path.basename(organization_id)  # Extract just the ID

        # Store document metadata in PostgreSQL (without extracted content)
        new_doc = Document(
            organization_id=org_id_cleaned, file_name=file.filename, file_url=file_url
        )

        db.add(new_doc)
        # print(f"✅ Before Commit: {new_doc.__dict__}")  # Check values before commit

        db.commit()
        db.refresh(new_doc)
        # print(f"✅ After Commit: {new_doc.__dict__}")  # Check values after commit

        # Generate embeddings from the file URL
        await upsert_document(db, org_id_cleaned, str(new_doc.chat_bot_resource_id))

        return {
            "message": "PDF uploaded successfully.",
            "document_id": new_doc.chat_bot_resource_id,
            "file_url": file_url,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error uploading document: {str(e)}"
        )
