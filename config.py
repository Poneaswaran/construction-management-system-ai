import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "super-secret-default-key")
