# app/services/ollama.py

import openai
import os
from dotenv import load_dotenv

# Load API key from .env file (optional but recommended)
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")  # getting the Opeanai API key from .env file

def ollama_bot(context: str, query: str):
    """
    Uses OpenAI's GPT API to generate responses.
    - `context`: Relevant text retrieved from vector database.
    - `query`: User's question.
    """
    prompt = f"Context: {context}\n\nQuery: {query}\n\nAnswer concisely:"
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # cheaper & faster
        messages=[{"role": "system", "content": "You are a helpful assistant."},
                  {"role": "user", "content": prompt}],
        temperature=0.5,  # Adjust creativity (0 = strict, 1 = very creative)
        max_tokens=200  # Control response length
    )

    return response["choices"][0]["message"]["content"].strip()


