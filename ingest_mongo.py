import sys
from pathlib import Path
from pymongo import MongoClient
from utils import simple_embedding
from config import MONGO_URI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

client = MongoClient(MONGO_URI)

source_collection = client["gowhats"]["your_collection"]
vector_collection = client["rag_db"]["docs"]

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