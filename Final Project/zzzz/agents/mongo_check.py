from pymongo import MongoClient

# Your MongoDB URI
uri = "mongodb+srv://donate-blood:jspmdonate@cluster0.evglf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Connect to MongoDB
client = MongoClient(uri)

# 1️⃣ List all databases
print("📁 Databases:")
print(client.list_database_names())

# Choose a database (example)
for db_name in client.list_database_names():
    print(f"\n📁 Database: {db_name}")
    db = client[db_name]

    for col_name in db.list_collection_names():
        print(f"  📂 Collection: {col_name}")
        col = db[col_name]

        for doc in col.find():
            print("    📄", doc)
