import sys
import os

# Mock environment for import test
os.environ["GROQ_API_KEY"] = "mock"
os.environ["SARVAM_API_KEY"] = "mock"
os.environ["DEEPGRAM_API_KEY"] = "mock"
os.environ["LIVEKIT_URL"] = "http://localhost:7880"
os.environ["LIVEKIT_API_KEY"] = "dev"
os.environ["LIVEKIT_API_SECRET"] = "secret"

try:
    from agent import agent_loop
    print("✅ agent.py imports successful")
except Exception as e:
    print(f"❌ agent.py import failed: {e}")
    sys.exit(1)
