from dotenv import load_dotenv
from google import genai
import os

load_dotenv(".env.local")

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="Hello"
)

print(response.text)