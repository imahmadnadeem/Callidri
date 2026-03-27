# Callindri — Project History & Changelog

## 🏗️ Version 0.1.0 — Initial Prototype (In Progress)

### ✨ Features Implemented
- **Pipecat Voice Loop**: Basic agent loop with STT, LLM, and TTS integration.
- **Multi-Model Logic**: Orchestration between Sarvam, Groq, and Gemini.
- **Knowledge Base (RAG)**: Ingestion of PDF, TXT, and MD files into ChromaDB.
- **LiveKit Integration**: Real-time room management and participant tokens.
- **Interactive Dashboard**: Modern dark-mode UI for monitoring and KB management.
- **Barge-in Support**: Basic interruption detection and buffer flushing.

### 🔄 Refactoring & Optimization (Current Phase)
- **Project Reorganization**: Standardized `src/`, `tests/`, `docs/`, and `scripts/` directories.
- **Environment Management**: Moved all secrets to `.env` and provided `.env.example`.
- **Path Robustness**: Refactored `config.py` to use relative path resolution.
- **Clutter Cleanup**: Removed 20+ temporary test scripts and redundant files.
- **Package Hygiene**: Added `__init__.py` and standardized imports.

### 🧪 Implementation & Testing Summary
- **LiveKit Testing**: Verified room join/leave and audio streaming.
- **STT/TTS Latency**: Validated Sarvam and Deepgram response times.
- **Document Ingestion**: Tested PDF and TXT file encoding and retrieval.
- **Dashboard API**: Verified endpoints for stats, calls, and knowledge list.

### 🚩 Known Issues & Risks
- **Redis State Persistence**: `dump.rdb` is currently local; consider Upstash for production.
- **ChromaDB Scaling**: Local SQLite-based Chroma might slow down with 100+ large documents.
- **Twilio 2FA**: Recovery codes should be handled via a secure vault instead of local files.

### 🚀 Suggested Next Steps
- **Conversational State Machine**: Move from linear logic to a formal state machine (Idle → Listening → Thinking → Speaking).
- **Advanced Barge-in**: Implement server-side VAD with better grain-sized fragmentation.
- **Analytics Pipeline**: Add detailed call transcript logging to Supabase.
- **Production CI/CD**: Dockerize the backend and set up automated testing.
