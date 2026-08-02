import os

import psycopg2
from dotenv import load_dotenv  # Add this
from google import genai
from pgvector.psycopg2 import register_vector

# Rich UI Components
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from sentence_transformers import SentenceTransformer

# Load environment variables from the .env file
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

def ask_codebase(query: str):
    # Embed the query
    query_vector = embedding_model.encode(query).tolist()
    
    # Search the database
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
    
    # Handle empty results
    if not results:
        return None

    # Construct the context payload
    retrieved_chunks = [row[0] for row in results]
    context_string = "\n\n---\n\n".join(retrieved_chunks)
    
    prompt = f"""
You are an expert backend software engineer tool. Answer the user's question using the provided code snippets.

CRITICAL INSTRUCTIONS FOR TONE AND STYLE:
1. Never open with introductory boilerplate phrases like "Based on the provided code snippets...", "According to the context...", or "Here is an explanation...".
2. Lead immediately with substance, the direct answer, or the structural breakdown.
3. Format your response using clean Markdown (such as syntax-highlighted code blocks, bold key terms, and scannable bullet points).
4. STRICTLY PROHIBITED: Do not use LaTeX formatting, dollar signs ($), or math equation blocks (like \ge or \le). Instead, use standard programming operators (like >=, <=) or plain English text for comparisons.
5. If the answer cannot be found in the context, state simply: "I cannot answer this based on the provided codebase context."

CONTEXT:
{context_string}

USER QUESTION: {query}
"""
    
    # Return the stream iterator instead of the resolved string
    response_stream = client.models.generate_content_stream(
        model=model_name,
        contents=prompt
    )
    return response_stream

if __name__ == "__main__":
    console.print("\n[bold green]✅ System Ready. Type 'exit' to quit.[/bold green]\n")
    
    while True:
        # Styled user input prompt
        user_query = Prompt.ask("[bold cyan]Ask FlowSmith[/bold cyan]")
        
        if user_query.lower() in ['exit', 'quit']:
            console.print("[bold yellow]Shutting down...[/bold yellow]")
            break
        
        # Show the spinner while querying Postgres AND waiting for the network
        with console.status("[bold purple]Searching codebase and thinking...", spinner="bouncingBar"):
            response_stream = ask_codebase(user_query)
            
            if response_stream is None:
                console.print("[bold red]No relevant code found in the database.[/bold red]")
                continue
            
            # Convert the stream into a manual iterator
            stream_iterator = iter(response_stream)
            
            # Force the program to wait here for the first network byte 
            # before letting the spinner disappear
            try:
                first_chunk = next(stream_iterator)
            except StopIteration:
                first_chunk = None

        console.print("\n")
        
        # Initialize the UI with that first chunk instead of an empty string
        full_response = first_chunk.text if (first_chunk and first_chunk.text) else ""
        
        # Open the Live rendering panel for the rest of the stream
        with Live(
            Panel(Markdown(full_response), title="[bold magenta]AI Response[/bold magenta]", border_style="magenta"), 
            console=console, 
            refresh_per_second=12
        ) as live:
            
            # Stream the remaining chunks seamlessly
            for chunk in stream_iterator:
                if chunk.text:
                    full_response += chunk.text
                    # Instantly update the UI panel with the new text
                    live.update(Panel(Markdown(full_response), title="[bold magenta]AI Response[/bold magenta]", border_style="magenta"))
        
        console.print("\n")