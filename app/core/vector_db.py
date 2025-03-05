# app/core/vector_db.py
from pinecone import Pinecone
from openai import OpenAI
from sqlalchemy.orm import Session
from app.models.document import Document

from google.cloud import storage
import fitz  # PyMuPDF for PDF text extraction

import os
from dotenv import load_dotenv
load_dotenv()

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\Enoch\Documents\telepracticepro-dev-bc536f445eca.json"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # Use an environment variable

# Get API key and index name from environment variables
pinecone_api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX")

# Ensure API key is set
if not pinecone_api_key:
    raise ValueError("PINECONE_API_KEY is not set in environment variables.")

# Initialize Pinecone
pc = Pinecone(api_key=pinecone_api_key)

# Ensure the index exists before using it
if index_name not in [idx.name for idx in pc.list_indexes()]:
    raise ValueError(f"Pinecone index '{index_name}' does not exist. Create it first.")

# Connect to the Pinecone index
index = pc.Index(index_name)

# Function to generate embeddings using OpenAI
def generate_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-ada-002", #OpenAI text embedding model
        input=text
    )
    return response.data[0].embedding  # Corrected response structure

# Function to upsert document embeddings into Pinecone
# def upsert_document(organization_id: str, doc_id: str, text: str):
#     """Inserts or updates a document embedding for a specific organization."""
#     embedding = generate_embedding(text)
#     index.upsert(
#         vectors=[(doc_id, embedding, {"organization_id": organization_id, "text": text})],  # Fixed format
#         namespace=organization_id  # Store vectors under organization's namespace
#     )


# Function to delete a document from Pinecone
def delete_document(organization_id: str, doc_id: str):
    """Deletes a document embedding based on document ID."""
    index.delete(ids=[doc_id], namespace=organization_id)


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text("text")  # Extract text
    return text.strip()

def download_from_gcs(bucket_name, file_path):
    """Download a file from Google Cloud Storage and return its local path."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_path)
    
    local_path = f"/tmp/{file_path.split('/')[-1]}"
    blob.download_to_filename(local_path)
    return local_path

def upsert_document(db: Session, organization_id: str, doc_id: str):
    """Fetch document from PostgreSQL, retrieve file from GCS, extract text, and insert into Pinecone."""
    document = db.query(Document).filter_by(chat_bot_resource_id=doc_id).first()
    if not document:
        raise ValueError(f"Document with ID {doc_id} not found.")

    file_url = document.file_url  
    bucket_name = file_url.split('/')[2]  # Extract bucket name from URL
    file_path = "/".join(file_url.split('/')[3:])  # Extract path in bucket

    # Download the PDF from GCS
    local_pdf_path = download_from_gcs(bucket_name, file_path)

    # Extract text
    text = extract_text_from_pdf(local_pdf_path)

    # Generate embeddings
    embedding = generate_embedding(text)

    # Upsert into Pinecone
    index.upsert(
        vectors=[(
            doc_id, embedding, 
            {"organization_id": organization_id, "text": text})],

        namespace=organization_id
    )