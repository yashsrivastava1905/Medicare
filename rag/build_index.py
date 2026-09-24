# Script to build FAISS index from knowledge_base.py
import os
import pickle
import faiss
from sentence_transformers import SentenceTransformer
from knowledge_base import DOCUMENTS

MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_DIR = os.path.join(os.path.dirname(__file__), "faiss_index")

def build_index():
    os.makedirs(INDEX_DIR, exist_ok=True)

    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    print(f"Encoding {len(DOCUMENTS)} documents...")
    embeddings = model.encode(DOCUMENTS, show_progress_bar=True)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)

    faiss.write_index(index, os.path.join(INDEX_DIR, "index.faiss"))

    with open(os.path.join(INDEX_DIR, "chunks.pkl"), "wb") as f:
        pickle.dump(DOCUMENTS, f)

    print("Index built and saved successfully.")

if __name__ == "__main__":
    build_index()
