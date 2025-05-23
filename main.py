
import os

from agno.storage.sqlite import SqliteStorage
from dotenv import load_dotenv
from agno.agent import Agent, AgentMemory
from agno.models.openai import OpenAIChat
from agno.memory.db.sqlite import SqliteMemoryDb
from agent.tools.sdk.googlecalendar import GoogleCalendarTools
from config.prompt import AGENT_CONFIG
from agno.memory.v2.db.sqlite import SqliteMemoryDb
from agno.memory.v2.memory import Memory

# Load environment variables
load_dotenv()

db_file = "database/agent.db"

memory = Memory(
    # Use any model for creating memories
    model=OpenAIChat(id="gpt-4.1"),
    db=SqliteMemoryDb(table_name="agent_sessions", db_file=db_file),
)

storage = SqliteStorage(table_name="agent_sessions", db_file=db_file)


agent = Agent(
    name=AGENT_CONFIG["name"],
    model=OpenAIChat(
        id="gpt-4.1-mini",
        api_key=os.getenv("OPENAI_API_KEY")
    ),
    tools=[GoogleCalendarTools(user_id="main_user")],
    description=AGENT_CONFIG["description"],
    instructions=AGENT_CONFIG["instructions"],
    session_id="agent_session",
    memory=memory,
    storage=storage,
    markdown=True,
    show_tool_calls=True,
    add_history_to_messages=True,
    num_history_responses=10,
    enable_agentic_memory=True,
    enable_user_memories=True,
    user_id="main_user",
    debug_mode=True,
    reasoning=False
)

print("🤖 AgenDo Calendar Assistant is ready!")
print("💬 Start chatting (type 'quit' to exit):")
print("-" * 50)

# Simple chat loop - Agno handles memory loading automatically
while True:
    user_input = input("\nYou: ").strip()

    if user_input.lower() in ['quit', 'exit']:
        print("\n👋 Goodbye!")
        print("📝 Your conversation is saved in memory!")
        break

    if user_input:
        agent.print_response(user_input)