# app/core/vector_db.py
from fastapi import HTTPException
from pinecone import Pinecone
import openai
from openai import OpenAI
from sqlalchemy.orm import Session
from app.models.document import Document
from urllib.parse import urlparse
import asyncio

from google.cloud import storage
import fitz  # PyMuPDF for PDF text extraction

import os
import logging
from urllib.parse import unquote
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load environment variables
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
    r"C:\Users\Enoch\Documents\telepracticepro-dev-bc536f445eca.json"
)

# Import GC bucket name
BUCKET_NAME = os.getenv("BUCKET_NAME")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Pinecone
pinecone_api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX")

if not pinecone_api_key:
    raise ValueError("❌ PINECONE_API_KEY is missing in environment variables.")

pc = Pinecone(api_key=pinecone_api_key)

if index_name not in [idx.name for idx in pc.list_indexes()]:
    raise ValueError(
        f"❌ Pinecone index '{index_name}' does not exist. Please create it."
    )

index = pc.Index(index_name)

# Initialize Google Cloud Storage Client
gcs_client = storage.Client()


MAX_RETRIES = 5  # Limit retries to avoid infinite looping

async def generate_embedding(text: str):
    """Generate an embedding using OpenAI, with async retry logic and exponential backoff."""
    retries = 0  # Track retry attempts
    wait_time = 2  # Start with a 2-second wait

    client = openai.AsyncOpenAI()  # Use the new OpenAI async client

    while retries < MAX_RETRIES:
        try:
            response = await client.embeddings.create(  # Updated method
                model="text-embedding-3-small",  # 1536 dimension with cosine metric
                input=text,
            )
            return response.data[0].embedding  # Corrected response format

        except openai.RateLimitError:
            logging.warning(f"⚠️ Rate limit exceeded. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)  # Non-blocking wait
            retries += 1
            wait_time *= 2  # Exponential backoff (2s > 4s > 8s > 16s > 32s)

        except openai.APIError as e:
            if getattr(e, "code", None) == "insufficient_quota":
                logging.error("❌ OpenAI API quota exceeded. Please check billing.")
                raise ValueError("OpenAI quota exceeded. Upgrade your plan.")
            else:
                logging.error(f"❌ OpenAI API error: {e}")
                raise e

    logging.error("❌ Max retries reached. Failed to generate embedding.")
    raise RuntimeError("Max retries reached. OpenAI API not responding.")


async def extract_text_from_pdf(pdf_path: str):
    """Extract text from a PDF file."""
    try:
        text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text("text")
        return text.strip()
    except Exception as e:
        logging.error(f"❌ Error extracting text from PDF: {e}")
        raise e


async def download_from_gcs(bucket_name: str, file_url: str):
    """Download a file from Google Cloud Storage."""
    try:
        # Ensure file_url only contains the object path, not a full URL
        if file_url.startswith("https://storage.googleapis.com"):
            file_url = file_url.split("/", 4)[-1]  # Extract only the object path

        file_path = unquote(file_url)  # Decode URL encoding

        # Extract bucket and object name correctly
        if "/" in file_path:
            bucket_name, file_path = file_path.split("/", 1)  # Separate bucket and path

        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(file_path)

        # Ensure local storage directory exists
        local_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(local_dir, exist_ok=True)

        local_path = os.path.join(local_dir, os.path.basename(file_path))
        blob.download_to_filename(local_path)

        logging.info(f"✅ File downloaded to: {local_path}")
        return local_path
    except Exception as e:
        logging.error(f"❌ Error downloading from GCS: {e}")
        raise e


async def upsert_document(db: Session, organization_id: str, doc_id: str):
    """Fetch document, download PDF, extract text, and insert into Pinecone."""
    try:
        document = db.query(Document).filter_by(chat_bot_resource_id=doc_id).first()
        if not document:
            raise ValueError(f"❌ Document with ID {doc_id} not found.")

        # Extract bucket name and file path
        file_url = document.file_url
        bucket_name = file_url.split("/")[2]
        file_path = "/".join(file_url.split("/")[3:])  # Extract path in bucket
        file_path = unquote(file_path)  # Decode URL

          # Download the PDF
        local_pdf_path = await download_from_gcs(bucket_name, file_path)  # Ensure this is async

        # Extract text from PDF
        text = await extract_text_from_pdf(local_pdf_path)  # Ensure this is async

        # Generate embeddings (Add await here)
        embedding = await generate_embedding(text)

        # Upsert into Pinecone
        index.upsert(
            vectors=[
                (doc_id, embedding, {"organization_id": organization_id, "text": text})
            ],
            namespace=organization_id,
        )

        logging.info(f"✅ Document {doc_id} successfully indexed in Pinecone.")

    except Exception as e:
        logging.error(f"❌ Error in upsert_document: {e}")
        raise e


# Function to delete a document from GC, Pinecone & Postgres

async def delete_document(db: Session, organization_id: str, doc_id: str):
    """Deletes document embedding from Pinecone, file from GCS, and record from PostgreSQL."""
    try:
        # Fetch document from PostgreSQL
        document = db.query(Document).filter_by(chat_bot_resource_id=doc_id).first()
        if not document:
            logging.error(f"❌ Document with ID {doc_id} not found in database.")
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

        # Extract bucket name and file path from document file_url
        file_url = document.file_url
        parsed_url = urlparse(file_url)

        if not parsed_url.netloc or not parsed_url.path:
            raise ValueError(f"Invalid file URL format: {file_url}")

        # Use the actual bucket name
        bucket_name = BUCKET_NAME  
        file_path = unquote(parsed_url.path.lstrip("/"))

        # Ensure file path does NOT include bucket name
        if file_path.startswith(f"{bucket_name}/"):
            file_path = file_path[len(f"{bucket_name}/"):]

        # Initialize GCS client
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_path)

        logging.info(f"🔹 Extracted File Path: {file_path}")

        # Delete the PDF file from Google Cloud Storage
        try:
            blob.delete()
            logging.info(f"✅ Successfully deleted file {file_path} from Google Cloud Storage.")
        except Exception as gcs_error:
            logging.warning(f"⚠️ Error deleting file {file_path}: {gcs_error}")

        # Delete the embedding vector from Pinecone
        try:
            index.delete(ids=[doc_id], namespace=organization_id)
            logging.info(f"✅ Successfully deleted document {doc_id} from Pinecone.")
        except Exception as pinecone_error:
            logging.error(f"⚠️ Pinecone deletion failed: {pinecone_error}")

        # Remove document record from PostgreSQL
        db.delete(document)
        db.commit()
        logging.info(f"✅ Successfully removed document {doc_id} from PostgreSQL.")

        return {"message": "Document deleted successfully", "document_id": doc_id}

    except Exception as e:
        logging.error(f"❌ Error in delete_document: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")
