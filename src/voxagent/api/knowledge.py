"""
api/knowledge.py
----------------
Knowledge base management endpoints:
  POST  /knowledge/upload     – upload PDF / TXT / MD, extract, chunk, embed, store
  GET   /knowledge/list       – list documents (Supabase-first, Chroma fallback)
  DELETE /knowledge/{doc_id}  – remove from Chroma *and* Supabase metadata table

Upload size cap: 10 MB.
Embeddings: reuses the singleton loaded in knowledge_base.py (never reinitialised here).
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime

import pypdf
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from langchain_text_splitters import RecursiveCharacterTextSplitter

from knowledge_base import kb
from memory import memory

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# ── constants ────────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 10 MB
ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _extract_text(content: bytes, extension: str) -> str:
    """Extract plain text from raw file bytes."""
    if extension == "pdf":
        reader = pypdf.PdfReader(io.BytesIO(content))
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(parts)
    # txt / md – assume UTF-8 with latin-1 fallback
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


async def _upsert_supabase_metadata(
    doc_id: str, filename: str, uploaded_at: str, chunk_count: int
) -> None:
    """Write document metadata row to Supabase (best-effort; never raises)."""
    if not memory.supabase:
        return
    try:
        await memory.supabase.table("documents").upsert(
            {
                "doc_id": doc_id,
                "filename": filename,
                "uploaded_at": uploaded_at,
                "chunk_count": chunk_count,
            },
            on_conflict="doc_id",
        ).execute()
    except Exception as exc:
        print(f"[KNOWLEDGE] Supabase metadata upsert failed (non-fatal): {exc}")


async def _delete_supabase_metadata(doc_id: str) -> None:
    """Remove document metadata row from Supabase (best-effort; never raises)."""
    if not memory.supabase:
        return
    try:
        await memory.supabase.table("documents").delete().eq("doc_id", doc_id).execute()
    except Exception as exc:
        print(f"[KNOWLEDGE] Supabase metadata delete failed (non-fatal): {exc}")


async def _list_from_supabase() -> list[dict] | None:
    """Return documents from Supabase, or None if unavailable."""
    if not memory.supabase:
        return None
    try:
        res = (
            await memory.supabase
            .table("documents")
            .select("doc_id, filename, uploaded_at, chunk_count")
            .order("uploaded_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        print(f"[KNOWLEDGE] Supabase list failed, falling back to Chroma: {exc}")
        return None


# ── routes ───────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """
    Upload a document to the knowledge base.

    - Accepts PDF, TXT, or MD files up to 10 MB.
    - Extracts text, chunks it (1000 chars / 100 overlap).
    - Embeds using the shared HuggingFace model (all-MiniLM-L6-v2).
    - Stores vectors in ChromaDB; stores metadata in Supabase documents table.
    """
    # ── 1. Validate extension ─────────────────────────────────────────────────
    filename = file.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{extension}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ── 2. Read & size-check ──────────────────────────────────────────────────
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the 10 MB upload limit ({len(content) // 1024 // 1024} MB received).",
        )

    # ── 3. Extract text ────────────────────────────────────────────────────────
    try:
        text = _extract_text(content, extension)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {exc}")

    if not text.strip():
        raise HTTPException(
            status_code=400, detail="Document is empty or contains no extractable text."
        )

    # ── 4. Chunk ───────────────────────────────────────────────────────────────
    chunks = _splitter.split_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="Chunking produced no output.")

    # ── 5. Build metadata per chunk ────────────────────────────────────────────
    doc_id = str(uuid.uuid4())
    uploaded_at = datetime.utcnow().isoformat()
    metadatas = [
        {
            "doc_id": doc_id,
            "filename": filename,
            "uploaded_at": uploaded_at,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    # ── 6. Store vectors in ChromaDB ───────────────────────────────────────────
    await kb.add_texts(chunks, metadatas)
    print(f"[KNOWLEDGE] Stored {len(chunks)} chunks for doc_id={doc_id} file={filename}")

    # ── 7. Persist management metadata in Supabase ─────────────────────────────
    await _upsert_supabase_metadata(doc_id, filename, uploaded_at, len(chunks))

    return {
        "doc_id": doc_id,
        "filename": filename,
        "chunk_count": len(chunks),
        "uploaded_at": uploaded_at,
        "status": "success",
    }


@router.get("/list")
async def list_documents():
    """
    List all uploaded documents.
    Primary source: Supabase documents table.
    Fallback: ChromaDB metadata inspection.
    """
    # Try Supabase first
    docs = await _list_from_supabase()
    if docs is not None:
        return {"documents": docs, "source": "supabase"}

    # Chroma fallback
    docs = await kb.list_documents()
    return {"documents": docs, "source": "chroma"}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """
    Delete a document and all its vector chunks.
    Removes from both ChromaDB and the Supabase documents table.
    """
    # Remove vectors from Chroma
    await kb.delete_document(doc_id)
    print(f"[KNOWLEDGE] Deleted Chroma vectors for doc_id={doc_id}")

    # Remove metadata from Supabase
    await _delete_supabase_metadata(doc_id)

    return {"status": "success", "doc_id": doc_id}
