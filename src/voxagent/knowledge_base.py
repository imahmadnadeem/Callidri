import os
import asyncio
import time
from abc import ABC, abstractmethod
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from config import CHROMA_DB_DIR, RAG_TIMEOUT, EMBEDDING_MODEL_NAME

_embeddings_instance = None

def get_embeddings():
    """Returns the global embedding model instance, initializing it on first call."""
    global _embeddings_instance
    if _embeddings_instance is None:
        print(f"[KNOWLEDGE_BASE] Initializing embedding model: {EMBEDDING_MODEL_NAME}...")
        _start_time = time.time()
        _embeddings_instance = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        # WARMUP: Run one dummy embedding call immediately
        print("[KNOWLEDGE_BASE] Warming up model with dummy call...")
        _embeddings_instance.embed_query("This is a warm-up query.")
        print(f"[KNOWLEDGE_BASE] Embedding model ready (initialized in {time.time() - _start_time:.2f}s)")
    return _embeddings_instance

class VectorProvider(ABC):
    @abstractmethod
    async def add_texts(self, texts: list[str], metadatas: list[dict] = None):
        pass

    @abstractmethod
    async def delete_texts(self, filter: dict):
        pass

    @abstractmethod
    async def list_metadatas(self) -> list[dict]:
        pass

    @abstractmethod
    async def search(self, query: str, k: int = 3) -> str:
        pass

class ChromaProvider(VectorProvider):
    def __init__(self):
        self.embeddings = get_embeddings()
        self.vector_store = Chroma(
            collection_name="voxagent_knowledge",
            embedding_function=self.embeddings,
            persist_directory=CHROMA_DB_DIR
        )

    async def add_texts(self, texts: list[str], metadatas: list[dict] = None):
        documents = [Document(page_content=t, metadata=m or {}) for t, m in zip(texts, metadatas or [{}]*len(texts))]
        await self.vector_store.aadd_documents(documents)
        print(f"Added {len(documents)} documents to Chroma (async).")

    async def delete_texts(self, filter: dict):
        # In langchain_chroma, delete accepts a list of IDs or a filter
        # But looking at the dir(Chroma) output, delete(self, ids: 'list[str] | None' = None, **kwargs: 'Any')
        # We might need to find IDs first or use the underlying collection
        collection = self.vector_store._collection
        collection.delete(where=filter)
        print(f"Deleted documents matching filter {filter} from Chroma.")

    async def list_metadatas(self) -> list[dict]:
        # Fetch all metadatas from the collection
        results = self.vector_store._collection.get(include=['metadatas'])
        return results['metadatas'] or []

    async def search(self, query: str, k: int = 3) -> str:
        # langchain_chroma supports asimilarity_search
        results = await self.vector_store.asimilarity_search(query, k=k)
        if not results:
            return "No relevant information found in the knowledge base."
        return "\n---\n".join([doc.page_content for doc in results])

class SupabaseProvider(VectorProvider):
    def __init__(self):
        # Stub for cloud migration
        pass

    async def add_texts(self, texts: list[str], metadatas: list[dict] = None):
        raise NotImplementedError("Supabase vector storage is not implemented yet.")

    async def delete_texts(self, filter: dict):
        raise NotImplementedError("Supabase vector deletion not implemented.")

    async def list_metadatas(self) -> list[dict]:
        raise NotImplementedError("Supabase metadata listing not implemented.")

    async def search(self, query: str, k: int = 3) -> str:
        raise NotImplementedError("Supabase vector search is not implemented yet.")

class KnowledgeBase:
    def __init__(self):
        db_type = os.getenv("VECTOR_DB", "chroma").lower()
        if db_type == "chroma":
            self.provider = ChromaProvider()
        elif db_type == "supabase":
            self.provider = SupabaseProvider()
        else:
            print(f"Unknown VECTOR_DB provider: {db_type}. Defaulting to Chroma.")
            self.provider = ChromaProvider()

    async def add_texts(self, texts: list[str], metadatas: list[dict] = None):
        return await self.provider.add_texts(texts, metadatas)

    async def delete_document(self, doc_id: str):
        return await self.provider.delete_texts({"doc_id": doc_id})

    async def list_documents(self) -> list[dict]:
        metadatas = await self.provider.list_metadatas()
        # Deduplicate by doc_id
        seen_ids = set()
        docs = []
        for m in metadatas:
            if m and m.get("doc_id") and m["doc_id"] not in seen_ids:
                docs.append({
                    "doc_id": m["doc_id"],
                    "filename": m.get("filename"),
                    "uploaded_at": m.get("uploaded_at")
                })
                seen_ids.add(m["doc_id"])
        return docs

    async def search(self, query: str, k: int = 3) -> str:
        try:
            return await asyncio.wait_for(
                self.provider.search(query, k),
                timeout=RAG_TIMEOUT
            )
        except asyncio.TimeoutError:
            print(f"[KNOWLEDGE_BASE] ERROR: RAG retrieval timed out after {RAG_TIMEOUT}s")
            raise asyncio.TimeoutError("RAG_TIMEOUT")
        except Exception as e:
            print(f"[KNOWLEDGE_BASE] ERROR: RAG retrieval failed: {e}")
            raise RuntimeError(f"RAG_FAILED: {e}")

kb = KnowledgeBase()

async def _seed_data():
    sample_faqs = [
        "Callindri is a modern Voice AI agent platform.",
        "To book a meeting with our sales team, simply ask the agent to schedule one. The agent has calendar access.",
        "We support English, Spanish, and Hindi out of the box.",
        "Our pricing starts at $99/month for the basic plan which includes 500 minutes."
    ]
    print("Seeding initial KB data...")
    await kb.add_texts(sample_faqs)
    print("Done.")

if __name__ == "__main__":
    asyncio.run(_seed_data())
