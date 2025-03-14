# API for PDF deletion

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import storage  # Google Cloud Storage
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.vector_db import delete_document  # Function to delete from Pinecone
from app.models.document import Document

import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Initialize Google Cloud Storage Client
storage_client = storage.Client()
BUCKET_NAME = os.getenv(
    "BUCKET_NAME"
)  # Ensure this is set in your environment variables


@router.delete("/delete/{organization_id}/{document_id}")
async def delete_pdf(
    organization_id: str, document_id: str, db: Session = Depends(get_db)
):
    """
    Deletes a PDF file from Google Cloud Storage, removes metadata from PostgreSQL,
    and deletes associated embeddings from Pinecone. Ensures that an organization
    can only delete its own documents.
    """
    # Find the document in PostgreSQL, filtering by org_id
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

    # Extract file path from URL
    file_url = doc.file_url
    if not file_url:
        raise HTTPException(
            status_code=400, detail="No file URL found for this document."
        )

    # Extract path relative to the bucket
    try:
        file_path = file_url.split(f"https://storage.googleapis.com/{BUCKET_NAME}/")[-1]

        # Delete file from Google Cloud Storage
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_path)

        if blob.exists():  # Check if file exists before deleting
            blob.delete()
        else:
            raise HTTPException(status_code=404, detail="File not found in storage.")

        # Delete document metadata from PostgreSQL
        db.delete(doc)
        db.commit()

        # Delete document vector from Pinecone
        delete_document(
            str(document_id), organization_id
        )  # Function to remove embeddings

        return {"message": "PDF deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error deleting document: {str(e)}"
        )
