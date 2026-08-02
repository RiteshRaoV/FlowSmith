import os

import psycopg2
from index_enriched import chunk_codebase_professionally
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

# 1. Updated Configuration
REPO_ROOT = "."
IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
ALLOWED_EXTENSIONS = {".py", ".txt", ".yml", ".yaml", ".md"}
ALLOWED_FILENAMES = {"Dockerfile"}

# 2. Find target files (now includes config files)
target_files = []
for root, dirs, files in os.walk(REPO_ROOT):
    dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
    for file in files:
        if any(file.endswith(ext) for ext in ALLOWED_EXTENSIONS) or file in ALLOWED_FILENAMES:
            target_files.append(os.path.join(root, file))

print(f"🔍 Found {len(target_files)} files to vectorize.")

model = SentenceTransformer('all-MiniLM-L6-v2')
conn = psycopg2.connect(
    dbname="postgres", user="postgres", password="postgres", host="localhost", port="5432"
)
register_vector(conn)
cursor = conn.cursor()

# 3. Prevent Duplication! Wipe the table before inserting.
print("🧹 Clearing old vectors from the database...")
cursor.execute("TRUNCATE TABLE codebase_vectors;")
conn.commit()

# 4. Process and Insert
total_chunks_processed = 0
for filepath in target_files:
    chunks = chunk_codebase_professionally(filepath)
    if not chunks: 
        continue

    for chunk in chunks:
        embedding = model.encode(chunk["content"]).tolist()
        cursor.execute(
            """
            INSERT INTO codebase_vectors 
            (file_path, class_name, function_name, chunk_index, content, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (chunk["file_path"], chunk["class_name"], chunk["function_name"],
             chunk["chunk_index"], chunk["content"], embedding)
        )
        total_chunks_processed += 1

conn.commit()
cursor.close()
conn.close()

print(f"✅ Successfully wiped old data and indexed {total_chunks_processed} chunks across {len(target_files)} files!")