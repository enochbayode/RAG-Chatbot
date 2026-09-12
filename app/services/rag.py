import os
import asyncio
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from app.services.ollama import ollama_bot  # Import Ollama chatbot instance

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

# Use OpenAI for async embedding
vector_store = PineconeVectorStore(index, OpenAIEmbeddings(), text_key="text")

# -----------------------------------------------------------------------------------
async def retrieve_relevant_docs(query: str, organization_id: str):
    """Asynchronously fetch relevant documents from both the organization and global knowledge base."""
    try:
        # Generate query embedding
        query_embedding = await OpenAIEmbeddings().aembed_query(query)

        # Perform organization-specific search
        query_results_org = index.query(vector=query_embedding, top_k=2, namespace=organization_id, include_metadata=True)

        # Perform global search from telepractice-pro resources
        query_results_global = index.query(vector=query_embedding, top_k=2, namespace="global", include_metadata=True)
        
        # Combine results
        combined_results = query_results_org.get("matches", []) + query_results_global.get("matches", [])

        # Extract relevant document contents
        relevant_docs = [match["metadata"]["text"] for match in combined_results if "metadata" in match and "text" in match["metadata"]]

        return relevant_docs

    except Exception as e:
        print(f"Error retrieving documents: {e}")
        return []

async def generate_response(query: str, organization_id: str):
    """Asynchronously retrieves relevant docs and generates a chatbot response using OpenAI."""
    relevant_docs = await retrieve_relevant_docs(query, organization_id)

    if not relevant_docs:
        return "No relevant information found for this organization."

    # Instruction for response generation
    instruction = (
        "Your name is Telebot."
        "If the user's question is about a specific organization, answer based on their documents."
        "If it's about TelepracticePro, answer based on the platform's knowledge base."
        "If both, combine relevant details."
        "Ensure you keep your answers clear and concise."
    )

    # Format context for GPT
    context = f"{instruction}\n\nRelevant Documents:\n" + "\n".join(relevant_docs)

    response = await ollama_bot(context, query)  # Call Ollama chatbot asynchronously
    return response

