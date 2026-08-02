import re

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

# 1. The Python Parser
python_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.PYTHON, chunk_size=1500, chunk_overlap=100
)

# 2. The Generic Parser (For YAML, Dockerfile, txt, md)
generic_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, chunk_overlap=100
)

def chunk_codebase_professionally(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    enriched_chunks = []
    print(f"Processing {filepath}...")

    # Route to the correct splitter based on file type
    if filepath.endswith(".py"):
        raw_chunks = python_splitter.create_documents([content])
        
        for index, chunk in enumerate(raw_chunks):
            text = chunk.page_content
            current_class, current_function = "Global Scope", "Global Scope"
            
            if class_match := re.search(r"class\s+(\w+)", text):
                current_class = class_match.group(1)
            if func_match := re.search(r"def\s+(\w+)", text):
                current_function = func_match.group(1)

            enriched_text = f"# File: {filepath}\n# Scope: Class {current_class} -> Function {current_function}\n{text}"
            
            enriched_chunks.append({
                "file_path": filepath, "class_name": current_class,
                "function_name": current_function, "chunk_index": index,
                "content": enriched_text
            })
            
    else:
        # For YAML, Dockerfiles, and Requirements
        raw_chunks = generic_splitter.create_documents([content])
        
        for index, chunk in enumerate(raw_chunks):
            enriched_text = f"# Configuration File: {filepath}\n\n{chunk.page_content}"
            
            enriched_chunks.append({
                "file_path": filepath, 
                "class_name": "Config", 
                "function_name": "Config", 
                "chunk_index": index,
                "content": enriched_text
            })

    return enriched_chunks