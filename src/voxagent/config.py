import os
from pathlib import Path
from dotenv import load_dotenv

# Project Root (Callindri/)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

# Package Dirs
SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR  # Legacy compat

# LLM Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Voice & Speech Keys
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")


# LiveKit (WebRTC)
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "http://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")

# State management
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
REDIS_MAX_IDLE = int(os.getenv("REDIS_MAX_IDLE", "5"))
REDIS_RETRY_ATTEMPTS = int(os.getenv("REDIS_RETRY_ATTEMPTS", "3"))
REDIS_KEEPALIVE = os.getenv("REDIS_KEEPALIVE", "True").lower() == "true"
REDIS_TIMEOUT = int(os.getenv("REDIS_TIMEOUT", "5"))

# Vector Database
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", str(ROOT_DIR / "data" / "chroma_db"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", str(SRC_DIR / "prompts" / "system.md"))
LOCAL_KNOWLEDGE_DIR = os.getenv("LOCAL_KNOWLEDGE_DIR", str(ROOT_DIR / "data" / "knowledge"))

# Supabase (Database)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TIMEOUT = int(os.getenv("SUPABASE_TIMEOUT", "10"))

# Timeouts (in seconds)
RAG_TIMEOUT = 5
TOOL_TIMEOUT = 8
LLM_TIMEOUT = 8
