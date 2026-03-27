import time
from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL_NAME

class EmbeddingsManager:
    _instance = None
    _embeddings = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingsManager, cls).__new__(cls)
        return cls._instance

    def get_embeddings(self) -> HuggingFaceEmbeddings:
        if self._embeddings is None:
            print(f"[EMBEDDINGS] Initializing model: {EMBEDDING_MODEL_NAME}...")
            start_time = time.time()
            
            # Initialize the model exactly once
            self._embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL_NAME,
                model_kwargs={'device': 'cpu'},  # Default to CPU for MVP compatibility
                encode_kwargs={'normalize_embeddings': True}
            )
            
            # WARMUP: Run one dummy embedding call to prevent first-inference latency
            print("[EMBEDDINGS] Warming up model with dummy call...")
            self._embeddings.embed_query("This is a warm-up query to initialize the model weights.")
            
            end_time = time.time()
            print(f"[EMBEDDINGS] Initialization and warm-up complete in {end_time - start_time:.2f}s")
            
        return self._embeddings

# Global singleton instance
embeddings_manager = EmbeddingsManager()

def get_embeddings():
    """Helper function to get the global embeddings instance."""
    return embeddings_manager.get_embeddings()
