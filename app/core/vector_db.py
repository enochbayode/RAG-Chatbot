# app/core/vector_db.py
from fastapi import HTTPException
from pinecone import Pinecone
import openai
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.organization import AppResource
from urllib.parse import urlparse
import asyncio
import tiktoken  # Tokenizer for OpenAI models

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


# Import GC bucket name
BUCKET_NAME = os.getenv("BUCKET_NAME")

# Initialize OpenAI client
client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

#-------------------Functions-------------------------------------------------

MAX_RETRIES = 5  # Limit retries to avoid infinite looping
WORD_LIMIT_ORG = 5000  # Max words for organization embedding
TOKEN_LIMIT = 8192  # Approx max tokens OpenAI can handle

def chunk_text(text: str, word_limit: int = None):
    """Chunks text while preserving sentence context."""
    words = text.split()
    if word_limit and len(words) > word_limit:
        words = words[:word_limit]  # Trim words if exceeding limit
    
    tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")
    tokens = tokenizer.encode(" ".join(words))
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for token in tokens:
        current_chunk.append(token)
        current_tokens += 1
        if current_tokens >= TOKEN_LIMIT:
            chunks.append(tokenizer.decode(current_chunk))
            current_chunk = []
            current_tokens = 0
    
    if current_chunk:
        chunks.append(tokenizer.decode(current_chunk))
    
    return chunks

async def generate_embedding_request(text: str):
    """Helper function to request embedding from OpenAI with retries."""

    retries = 0  # Track retry attempts
    wait_time = 2  # Start with a 2-second wait

    while retries < MAX_RETRIES:
        try:
            response = await client.embeddings.create(
                model="text-embedding-3-small", # 1536 dimension with cosine metric
                input=text,
            )
            return response.data[0].embedding
        
        except openai.RateLimitError:
            logging.warning(f"⚠️ Rate limit exceeded. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            retries += 1
            wait_time *= 2 # Exponential backoff (2s > 4s > 8s > 16s > 32s)

        except openai.APIError as e:
            if getattr(e, "code", None) == "insufficient_quota":
                logging.error("❌ OpenAI API quota exceeded. Check billing.")
                raise ValueError("OpenAI quota exceeded. Upgrade your plan.")
            else:
                logging.error(f"❌ OpenAI API error: {e}")
                raise e
            
    logging.error("❌ Max retries reached. Failed to generate embedding.")
    raise RuntimeError("Max retries reached. OpenAI API not responding.")

async def generate_organization_embedding(text: str):
    """Generates an embedding for an organization's document, enforcing a word limit."""
    word_count = len(text.split())

    if word_count > WORD_LIMIT_ORG:
        raise ValueError(f"❌ Document exceeds {WORD_LIMIT_ORG} words. Reduce size and try again.")

    chunks = chunk_text(text, word_limit=WORD_LIMIT_ORG)
    embeddings = await asyncio.gather(*[generate_embedding_request(chunk) for chunk in chunks])

    # Flatten the list of lists
    flattened_embedding = [value for sublist in embeddings for value in sublist]

    return flattened_embedding  # Now returns a flat list



async def generate_global_embedding(text: str):
    """Generates an embedding for a global document with no word limit."""
    chunks = chunk_text(text)
    embeddings = await asyncio.gather(*[generate_embedding_request(chunk) for chunk in chunks])
    
    # Flatten the list of lists
    flattened_embedding = [value for sublist in embeddings for value in sublist]

    return flattened_embedding  # Now returns a flat list


async def extract_text_from_pdf(pdf_path: str):
    """Extract text from a PDF file without enforcing a word limit."""
    try:
        text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text("text")

        return text.strip()  # Return extracted text
    except Exception as e:
        logging.error(f"❌ Error extracting text from PDF: {e}")
        raise e

async def download_from_gcs(bucket_name: str, file_url: str, is_organization: bool = False):
    """Download a file from Google Cloud Storage for either global or organization-specific documents."""
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
        print ("gcs bucket: ", bucket)
        print ("gcs blob :", blob)


        # Define separate download directories for global and organization documents
        base_dir = os.path.join(os.getcwd(), "downloads")
        download_dir = os.path.join(base_dir, "organizations") if is_organization else os.path.join(base_dir, "global")

        # Ensure the storage directory exists
        os.makedirs(download_dir, exist_ok=True)

        local_path = os.path.join(download_dir, os.path.basename(file_path))
        blob.download_to_filename(local_path)

        logging.info(f"✅ File downloaded to: {local_path}")
        return local_path
    except Exception as e:
        logging.error(f"❌ Error downloading from GCS: {e}")
        raise e



# Upsert document to Postgres, GC & Pinecone
#---------------------------------------------------------------------------

async def upsert_organization_document(db: Session, organization_id: str, doc_id: str):
    """Fetch and index a business-specific document."""
    try:
        document = db.query(Document).filter_by(chat_bot_resource_id=doc_id).first()
        if not document:
            raise ValueError(f"❌ Document with ID {doc_id} not found.")

        # Extract bucket name and file path
        file_url = document.file_url
        bucket_name = file_url.split("/")[2]
        file_path = unquote("/".join(file_url.split("/")[3:]))  # Decode URL

        # Remove "telepracticepro-dev/" from file path
        normalized_path = file_path.replace("telepracticepro-dev/", "", 1)

        # Ensure document is in the correct business directory
        expected_prefix = f"organization/{organization_id}/pdfs/"
        if not normalized_path.startswith(expected_prefix):
            raise ValueError(f"❌ File {file_path} is not in the correct business folder.")

        # Download, extract text, and generate embeddings
        local_pdf_path = await download_from_gcs(bucket_name, file_path)
        text = await extract_text_from_pdf(local_pdf_path)
        embedding = await generate_organization_embedding(text)

        # Upsert into Pinecone with business namespace
        index.upsert(
            vectors=[(doc_id, embedding, {"organization_id": organization_id, "text": text})],
            namespace=organization_id,
        )

        logging.info(f"✅ Business document {doc_id} successfully indexed.")

    except Exception as e:
        logging.error(f"❌ Error in upsert_business_document: {e}")
        raise e


async def upsert_global_document(db: Session, organization_id, doc_id: str):
    """Fetch and index a global document."""
    try:
        document = db.query(AppResource).filter_by(app_resource_id=doc_id).first()
        if not document:
            raise ValueError(f"❌ Document with ID {doc_id} not found.")

        # Extract bucket name and file path
        file_url = document.file_url

        # bucket_name = file_url.split("/")[2]
        bucket_name = BUCKET_NAME
        file_path = unquote("/".join(file_url.split("/")[3:]))  # Decode URL

        # Remove "telepracticepro-dev/" from file path
        normalized_path = file_path.replace("telepracticepro-dev/", "", 1)
        
        expected_prefix = f"{organization_id}/pdfs/"      #
        if not normalized_path.startswith(expected_prefix):
            raise ValueError(f"❌ File {file_path} is not in the correct global folder.")

        # Download, extract text, and generate embeddings
        local_pdf_path = await download_from_gcs(bucket_name, file_path)

        # Extract text from PDF
        text = await extract_text_from_pdf(local_pdf_path)

        # Generate embedding
        embedding = await generate_global_embedding(text)

        # Upsert into Pinecone with global namespace
        index.upsert(
            vectors=[(doc_id, embedding, {"organization_id": organization_id, "text": text})],
            namespace=organization_id,
        )

        logging.info(f"✅ Global document {doc_id} successfully indexed.")

    except Exception as e:
        logging.error(f"❌ Error in upsert_global_document: {e}")
        raise e



# Function to delete a document from GC, Pinecone & Postgres
#---------------------------------------------------------------------
async def delete_organization_document(db: Session, organization_id: str, doc_id: str):
    """Deletes a business-specific document from Pinecone, GCS, and PostgreSQL."""
    try:
        # Fetch document from database
        document = db.query(Document).filter_by(chat_bot_resource_id=doc_id).first()
        if not document:
            logging.error(f"❌ Document {doc_id} not found in database.")
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

        # Extract bucket name and file path
        file_url = document.file_url
        parsed_url = urlparse(file_url)

        if not parsed_url.netloc or not parsed_url.path:
            raise ValueError(f"Invalid file URL format: {file_url}")

        file_path = unquote(parsed_url.path.lstrip("/"))
        if file_path.startswith(f"{BUCKET_NAME}/"):
            file_path = file_path[len(f"{BUCKET_NAME}/") :]

        # Delete from GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_path)
        blob.delete()
        logging.info(f"✅ Deleted file {file_path} from GCS.")

        # Delete from Pinecone
        index.delete(ids=[doc_id], namespace=organization_id)
        logging.info(f"✅ Deleted document {doc_id} from Pinecone.")

        # Delete from PostgreSQL
        db.delete(document)
        db.commit()
        logging.info(f"✅ Deleted document {doc_id} from PostgreSQL.")

        return {"message": "Business document deleted successfully", "document_id": doc_id}

    except Exception as e:
        logging.error(f"❌ Error in delete_business_document: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")


async def delete_global_document(db: Session, organization_id, doc_id: str):
    """Deletes a global document from Pinecone, GCS, and PostgreSQL."""
    try:
        # Fetch document from database
        document = db.query(AppResource).filter_by(app_resource_id=doc_id).first()
        if not document:
            logging.error(f"❌ Document {doc_id} not found in database.")
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

        # Extract bucket name and file path
        file_url = document.file_url
        parsed_url = urlparse(file_url)
        if not parsed_url.netloc or not parsed_url.path:
            raise ValueError(f"Invalid file URL format: {file_url}")

        file_path = unquote(parsed_url.path.lstrip("/"))
        if file_path.startswith(f"{BUCKET_NAME}/"):
            file_path = file_path[len(f"{BUCKET_NAME}/") :]

        # Delete from GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_path)
        blob.delete()
        logging.info(f"✅ Deleted file {file_path} from GCS.")

        # Delete from Pinecone (Global Namespace)
        index.delete(ids=[doc_id], namespace=organization_id)
        logging.info(f"✅ Deleted document {doc_id} from Pinecone.")

        # Delete from PostgreSQL
        db.delete(document)
        db.commit()
        logging.info(f"✅ Deleted document {doc_id} from PostgreSQL.")

        return {"message": "Global document deleted successfully", "document_id": doc_id}

    except Exception as e:
        logging.error(f"❌ Error in delete_global_document: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")
