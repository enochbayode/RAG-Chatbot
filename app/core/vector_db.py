# app/core/vector_db.py
from pinecone import Pinecone
from openai import OpenAI
from sqlalchemy.orm import Session
from app.models.document import Document
import time

from google.cloud import storage
import fitz  # PyMuPDF for PDF text extraction

import os
import logging
from urllib.parse import unquote
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\Enoch\Documents\telepracticepro-dev-bc536f445eca.json"

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Pinecone
pinecone_api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX")

if not pinecone_api_key:
    raise ValueError("❌ PINECONE_API_KEY is missing in environment variables.")

pc = Pinecone(api_key=pinecone_api_key)

if index_name not in [idx.name for idx in pc.list_indexes()]:
    raise ValueError(f"❌ Pinecone index '{index_name}' does not exist. Please create it.")

index = pc.Index(index_name)

# Initialize Google Cloud Storage Client
gcs_client = storage.Client()

# ----------- FUNCTIONS -----------

# from sentence_transformers import SentenceTransformer

# # Load Sentence-Transformers model instead of OpenAI
# embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# Function to generate embeddings with either OpenAI or Hugging face
# def generate_embedding(text: str, use_openai: bool = False):
#     """Generate an embedding using either OpenAI or Hugging Face's Sentence-Transformers."""
#     if use_openai:
#         try:
#             response = openai.embeddings.create(
#                 model="text-embedding-ada-002",
#                 input=text
#             )
#             return response.data[0].embedding
        
#         except openai.RateLimitError:
#             logging.warning("⚠️ Rate limit exceeded, retrying in 10 seconds...")
#             time.sleep(10)
#             return generate_embedding(text, use_openai=True)  # Recursive retry

#         except openai.APIError as e:
#             if e.code == "insufficient_quota":
#                 logging.error("❌ OpenAI API quota exceeded. Please check billing.")
#                 raise ValueError("OpenAI quota exceeded. Upgrade your plan.")
#             else:
#                 logging.error(f"❌ OpenAI API error: {e}")
#                 raise e
#     else:
#         # Generate embedding using Hugging Face SentenceTransformers
#         return embedding_model.encode(text).tolist()  # Convert to list for compatibility

def generate_embedding(text: str):
    """Generate an embedding using OpenAI, with retry logic for quota errors."""
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",  # 1536 dimension with cosine metric
            input=text
        )
        return response.data[0].embedding
    except openai.RateLimitError:
        logging.warning("⚠️ Rate limit exceeded, retrying in 10 seconds...")
        time.sleep(10)  # Wait and retry
        return generate_embedding(text)  # Recursive retry
    
    except openai.APIError as e:
        if e.code == "insufficient_quota":
            logging.error("❌ OpenAI API quota exceeded. Please check billing.")
            raise ValueError("OpenAI quota exceeded. Upgrade your plan.")
        else:
            logging.error(f"❌ OpenAI API error: {e}")
            raise e



def extract_text_from_pdf(pdf_path: str):
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


def download_from_gcs(bucket_name: str, file_url: str):
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



def upsert_document(db: Session, organization_id: str, doc_id: str):
    """Fetch document, download PDF, extract text, and insert into Pinecone."""
    try:
        document = db.query(Document).filter_by(chat_bot_resource_id=doc_id).first()
        if not document:
            raise ValueError(f"❌ Document with ID {doc_id} not found.")

        # Extract bucket name and file path
        file_url = document.file_url
        bucket_name = file_url.split('/')[2]
        file_path = "/".join(file_url.split('/')[3:])  # Extract path in bucket
        file_path = unquote(file_path)  # Decode URL

        # Download the PDF
        local_pdf_path = download_from_gcs(bucket_name, file_path)

        # Extract text from PDF
        text = extract_text_from_pdf(local_pdf_path)

        # Generate embeddings
        embedding = generate_embedding(text)

        # Upsert into Pinecone
        index.upsert(
            vectors=[(doc_id, embedding, {"organization_id": organization_id, "text": text})],
            namespace=organization_id
        )

        logging.info(f"✅ Document {doc_id} successfully indexed in Pinecone.")

    except Exception as e:
        logging.error(f"❌ Error in upsert_document: {e}")
        raise e



# Function to delete a document from Pinecone
def delete_document(organization_id: str, doc_id: str):
    """Deletes a document embedding based on document ID."""
    index.delete(ids=[doc_id], namespace=organization_id)