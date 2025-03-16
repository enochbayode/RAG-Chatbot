import openai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
client = openai.Client(api_key=OPENAI_API_KEY)


def ollama_bot(context: str, query: str) -> str:
    """
    Generates a response using OpenAI's GPT API.

    :param context: Relevant text retrieved from the vector database.
    :param query: User's question.
    :return: AI-generated response.
    """
    prompt = f"Context: {context}\n\nQuery: {query}\n\nAnswer concisely:"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # using 'gpt-4o-mini' (faster & cheaper than 'gpt-4.o')
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,  # Adjust creativity
            max_tokens=200,  # Limit response length
        )
        return response.choices[0].message.content.strip()

    except openai.APIError as e:
        print(f"OpenAI API error: {e}")
        return "I'm sorry, but I couldn't process your request."

    except Exception as e:
        print(f"Unexpected error: {e}")
        return "An unexpected error occurred."
