# Callindri — High-Level System Architecture

This document describes the high-level architecture and data flow of the Callindri VOX Agent platform.

## 🏗️ System Overview

Callindri is an event-driven voice-agent orchestrator designed for real-time human-AI conversation. It is built on top of broad-spectrum communication protocols (WebRTC) and focuses on low-latency response and robust barge-in handling.

### 🧩 Component Breakdown

#### `src/voxagent/` (Core Logic)
- **`main.py`**: The entry-point for the FastAPI server, managing HTTP endpoints for room management, Twilio webhooks, and participant token generation.
- **`agent.py`**: Orchestrates the Pipecat agent loop. It wires together STT, LLM, TTS, and VAD services.
- **`conversation_manager.py`**: Manages the conversational context, history, and integration with the Knowledge Base.
- **`speech_orchestrator.py`**: Handles low-level audio streaming, fragment buffering, and voice stabilization.
- **`knowledge_base.py`**: Manages document ingestion, vector encoding (embeddings), and retrieval-augmented generation (RAG) queries via ChromaDB.
- **`memory.py`**: Persistent and session-level state management via Redis.

#### `src/dashboard/` (Monitor & Control)
- **`index.html`**: A modern, responsive dashboard with zero dependencies.
- **`app.js`**: Frontend logic for real-time monitoring and document management via the Backend API.
- **`styles.css`**: Premium styling with dark-mode support and modern design tokens.

### 📡 Data Flow

1. **Inbound Connection**: User connects via LiveKit or Twilio.
2. **Room Orchestration**: `server.py` creates a room and spawns a background `agent_loop`.
3. **Voice Input**: Audio streams via WebRTC → `STT` (Sarvam/Deepgram) converts to text fragments.
4. **Context Retrieval**: `ConversationManager` queries `KnowledgeBase` (ChromaDB) for relevant context.
5. **LLM Reasoning**: `LLM` (Groq/Gemini) generates response text based on context and history.
6. **Voice Synthesis**: `TTS` (Sarvam/Cartesia) streams audio back to the room.
7. **Barge-in Handling**: `SpeechOrchestrator` detects user interruptions and flushes TTS buffers immediately.

### 💾 Persistence & State
- **Redis**: Stores active session metadata and temporary call records.
- **Supabase**: Persistent storage for long-term analytics and document metadata.
- **ChromaDB**: On-disk vector store for the knowledge base.

## 📁 Directory Structure

```text
Callindri/
├── src/                # All source code
│   ├── voxagent/       # Backend (Python/FastAPI)
│   │   ├── api/        # Endpoint routers
│   │   └── prompts/    # Prompt templates
│   └── dashboard/      # Frontend (HTML/JS/CSS)
├── scripts/            # Automation (start, test, dev)
├── tests/              # Test suite (pyunit, shell)
├── docs/               # Research & Design documentation
└── data/               # Persistence (Chroma, Redis rdb, static assets)
```
