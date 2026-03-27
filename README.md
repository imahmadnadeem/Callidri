# Callidri

Callidri is a high-performance, production-grade AI Voice Agent platform. It leverages state-of-the-art LLMs, STT, and TTS services to provide natural, low-latency voice interactions.

## 🚀 Features

- **Multi-Model Support**: Groq, Gemini, and Sarvam for low-latency reasoning and speech.
- **Voice Stabilization**: Advanced barge-in handling and conversational state management.
- **RAG Integration**: Document upload and vector search for domain-specific knowledge.
- **Real-time Dashboard**: Monitor active calls, stats, and manage the knowledge base.
- **Telephony Ready**: Webhooks for Twilio and LiveKit integration.

## 🛠️ Tech Stack

- **Backend**: Python, FastAPI, Uvicorn
- **Orchestration**: Pipecat AI, LiveKit
- **Real-time Communication**: WebRTC via LiveKit SDK
- **Database**: ChromaDB (Vector), Redis (State Messaging), Supabase (Persistent data)
- **Frontend**: Vanilla JS, Vanilla CSS, HTML5

## 📦 Project Structure

```text
Callidri/
├── src/
│   ├── voxagent/          # Core Python backend
│   └── dashboard/         # Dashboard frontend
├── scripts/               # Automation and test scripts
├── tests/                 # Unit, integration, and E2E tests
├── docs/                  # Design docs and research handoffs
├── data/                  # Local databases and assets
└── requirements.txt       # Project dependencies
```

## ⚙️ Setup Instructions

### 1. Prerequisites
- Python 3.10+
- Redis server
- Livekit-server (local or cloud)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/imahmadnadeem/Callidri.git
cd Callidri

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in the required API keys.
```bash
cp .env.example .env
```

### 4. Running the Project

**Start the Backend:**
```bash
python src/voxagent/main.py
```

**Start the Dashboard:**
Open `src/dashboard/index.html` in your browser. (Ensure backend is running).

## 🧪 Testing
Run tests using the provided scripts:
```bash
bash scripts/start_test.sh
```

## 📄 License
MIT
