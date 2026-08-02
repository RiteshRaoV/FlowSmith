import os

import psycopg2
from dotenv import load_dotenv
from google import genai
from pgvector.psycopg2 import register_vector

# Rich UI Components (You were missing these!)
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from sentence_transformers import SentenceTransformer

# Load environment variables
load_dotenv()

# Initialize the UI
console = Console()
console.print(Panel.fit("[bold blue]Starting FlowSmith RAG Engine...[/bold blue]", border_style="blue"))

# 1. Initialize Clients
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
model_name = "gemini-3.5-flash" 

with console.status("[bold green]Loading Embedding Model...", spinner="dots"):
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

with console.status("[bold green]Connecting to PostgreSQL...", spinner="dots"):
    conn = psycopg2.connect(
        dbname="postgres", user="postgres", password="postgres",
        host="localhost", port="5432"
    )
    register_vector(conn)

def reformulate_query(current_query: str, history: list) -> str:
    # Only keep the last 3 turns to save tokens and keep context relevant
    history_text = "\n".join([f"User: {q}\nAI: {a}" for q, a in history[-3:]])
    
    prompt = f"""Rewrite the user's latest question into a standalone search query that contains all necessary context from the conversation history. Do not answer the question, just output the reformulated query string.

HISTORY:
{history_text}

LATEST QUESTION: {current_query}
STANDALONE QUERY:"""
    
    response = client.models.generate_content(
        model=model_name,
        contents=prompt
    )
    return response.text.strip()

def ask_codebase(search_query: str, actual_query: str, history: list):
    # 1. Use the standalone search query for vector math
    query_vector = embedding_model.encode(search_query).tolist()
    
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT content 
        FROM codebase_vectors 
        ORDER BY embedding <=> %s::vector 
        LIMIT 10;
        """,
        (query_vector,)
    )
    results = cursor.fetchall()
    cursor.close()
    
    if not results:
        return None

    retrieved_chunks = [row[0] for row in results]
    context_string = "\n\n---\n\n".join(retrieved_chunks)
    
    # 2. Format the history block
    history_string = "No previous conversation."
    if history:
        history_string = "\n\n".join([f"USER: {q}\nAI: {a}" for q, a in history[-3:]])
    
    # 3. Update the prompt to include both history and the actual question
    prompt = f"""
You are an expert backend software engineer tool. Answer the user's question using the provided code snippets and conversation history.

CRITICAL INSTRUCTIONS FOR TONE AND STYLE:
1. Never open with introductory boilerplate phrases.
2. Lead immediately with substance.
3. Format your response using clean Markdown.
4. STRICTLY PROHIBITED: Do not use LaTeX formatting. Use standard programming operators (like >=, <=) or plain English text.
5. If the answer cannot be found in the context, state simply: "I cannot answer this based on the provided codebase context."

CONVERSATION HISTORY:
{history_string}

CODEBASE CONTEXT:
{context_string}

USER'S CURRENT QUESTION: {actual_query}
"""
    
    response_stream = client.models.generate_content_stream(
        model=model_name,
        contents=prompt
    )
    return response_stream

if __name__ == "__main__":
    console.print("\n[bold green]✅ System Ready. Type 'exit' to quit.[/bold green]\n")
    
    # Initialize the memory list
    chat_history = [] 
    
    while True:
        user_query = Prompt.ask("[bold cyan]Ask FlowSmith[/bold cyan]")
        
        if user_query.lower() in ['exit', 'quit']:
            console.print("[bold yellow]Shutting down...[/bold yellow]")
            break
        
        with console.status("[bold purple]Searching codebase and thinking...", spinner="bouncingBar"):
            
            # 1. Reformulate if we have history!
            search_query = user_query
            if chat_history:
                search_query = reformulate_query(user_query, chat_history)
            
            # 2. Pass all three variables to the codebase function
            response_stream = ask_codebase(search_query, user_query, chat_history)
            
            if response_stream is None:
                console.print("[bold red]No relevant code found in the database.[/bold red]")
                continue
            
            stream_iterator = iter(response_stream)
            try:
                first_chunk = next(stream_iterator)
            except StopIteration:
                first_chunk = None

        console.print("\n")
        full_response = first_chunk.text if (first_chunk and first_chunk.text) else ""
        
        with Live(
            Panel(Markdown(full_response), title="[bold magenta]AI Response[/bold magenta]", border_style="magenta"), 
            console=console, 
            refresh_per_second=12
        ) as live:
            for chunk in stream_iterator:
                if chunk.text:
                    full_response += chunk.text
                    live.update(Panel(Markdown(full_response), title="[bold magenta]AI Response[/bold magenta]", border_style="magenta"))
        
        console.print("\n")
        
        # 3. Save the completed interaction to memory for the next loop
        chat_history.append((user_query, full_response))