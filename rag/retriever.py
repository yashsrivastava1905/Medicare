# Retrieval logic will go here
import os
import pickle
import faiss
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_DIR = os.path.join(os.path.dirname(__file__), "faiss_index")

_model = None
_index = None
_chunks = None

def _load():
    global _model, _index, _chunks
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    if _index is None:
        _index = faiss.read_index(os.path.join(INDEX_DIR, "index.faiss"))
    if _chunks is None:
        with open(os.path.join(INDEX_DIR, "chunks.pkl"), "rb") as f:
            _chunks = pickle.load(f)

def retrieve(query, top_k=3):
    _load()
    query_embedding = _model.encode([query])
    distances, indices = _index.search(query_embedding, top_k)
    results = [_chunks[i] for i in indices[0] if i < len(_chunks)]
    return results
