from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
# from langchain.embeddings import HuggingFaceEmbeddings  # Use SentenceTransformers
from app.services.ollama import ollama_bot  # Import Ollama chatbot instance

import os
from dotenv import load_dotenv
load_dotenv()

# Get API key and index name from environment variables
pinecone_api_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX")

# Ensure API key is set
if not pinecone_api_key:
    raise ValueError("PINECONE_API_KEY is not set in environment variables.")

# Initialize Pinecone client
pc = Pinecone(api_key=pinecone_api_key)

# Ensure the index exists before using it
if index_name not in [idx.name for idx in pc.list_indexes()]:
    raise ValueError(f"Pinecone index '{index_name}' does not exist. Create it first.")

# Connect to the Pinecone index
index = pc.Index(index_name)

# using OpenAI for embedding 
Create Vector Store using LangChain's Pinecone wrapper
vector_store = PineconeVectorStore(index, OpenAIEmbeddings(), text_key="text")

# Use Hugging face (SentenceTransformers) for embedding  
#embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Create Vector Store using LangChain's Pinecone wrapper
vector_store = PineconeVectorStore(index, embedding_model, text_key="text")

#-----------------------------

def retrieve_relevant_docs(query: str, organization_id: str):
    """Fetch relevant documents specific to an organization."""
    query_results = vector_store.similarity_search(
        query, 
        k=2,  # Retrieving the top 2 relevant docs
        namespace=organization_id
    )
    return query_results

def generate_response(query: str, organization_id: str):
    """Retrieves relevant docs and generates a chatbot response using Ollama."""
    relevant_docs = retrieve_relevant_docs(query, organization_id)
    
    if not relevant_docs:
        return "No relevant information found."

    # Format context for Ollama
    context = "\n".join([doc.page_content for doc in relevant_docs])
    #prompt = f"Context: {context}\n\nUser Query: {query}"
    
    response = ollama_bot(context, query) #calling as a function
    return response
