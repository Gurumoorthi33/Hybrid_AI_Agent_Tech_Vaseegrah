import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import MONGO_VECTOR_COLLECTION
from config.mongo_client import get_mongo_connection
from utils import simple_embedding

conn = get_mongo_connection()
if not conn.ok:
    raise RuntimeError(f"MongoDB unavailable: {conn.error}")

source_collection = conn.db["your_collection"]
vector_collection = conn.db[MONGO_VECTOR_COLLECTION]

def ingest_mongo():
    for doc in source_collection.find():
        text = str(doc)

        vector_collection.insert_one({
            "text": text,
            "embedding": simple_embedding(text).tolist(),
            "source": "mongodb"
        })

if __name__ == "__main__":
    ingest_mongo()
    print("MongoDB data ingested ✅")
