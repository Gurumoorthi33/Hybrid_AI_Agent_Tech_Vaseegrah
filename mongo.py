from pymongo import MongoClient
from config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["gowhats"]

def query_mongo(query):
    query = query.lower()

    collections = db.list_collection_names()

    # ✅ 1. Collection names
    if "collection" in query and "name" in query:
        return [f"Available collections: {', '.join(collections)}"]

    # ✅ 2. Count queries (VERY IMPORTANT)
    if "count" in query:
        results = []
        for col in collections:
            if col in query:
                count = db[col].count_documents({})
                results.append(f"{col} collection has {count} records")
        return results

    # ✅ 3. Direct collection mention
    for col in collections:
        if col in query:
            docs = list(db[col].find().limit(3))
            return [f"Sample data from {col}: {docs}"]

    # ✅ 4. Fallback search
    results = []
    for col in collections:
        for doc in db[col].find().limit(5):
            if query in str(doc).lower():
                results.append(str(doc))

    return results[:3]