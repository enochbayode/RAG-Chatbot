# Interface for calling Ollama2:7B

# app/services/ollama.py

from openai import OpenAI
import os

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

def ollama_bot(context: str, query: str):
    """
    Generates a response using the Ollama model.
    - `context`: Relevant text retrieved from vector database.
    - `query`: The user's question.
    """
    client = OpenAI(base_url="http://localhost:11434")  # Assuming Ollama is running locally

    response = client.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful chatbot that answers based on the provided context."},
            {"role": "user", "content": f"Context: {context}\n\nQuery: {query}"}
        ]
    )

    return response["choices"][0]["message"]["content"]
