import os

from agno.storage.sqlite import SqliteStorage
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agendo.sdk.googlecalendar import GoogleCalendarTools
from agendo.tools.Scheduler import Scheduler
from agendo.config.prompt import AGENT_CONFIG

load_dotenv()

db_file = r"E:\Projects\AgenDo\data\database\agent.db"

# Simplified - disable memory for now to avoid getting stuck
storage = SqliteStorage(table_name="agent_storage", db_file=db_file)

# Initialize Google Calendar tools first
calendar_tools = GoogleCalendarTools(
    credentials_path=r"E:\Projects\AgenDo\agendo\config\credentials\credentials.json",
    token_path=r"E:\Projects\AgenDo\agendo\config\credentials\token.json"
)

# Create the high-level Scheduler tool
scheduler = Scheduler(calendar_tools=calendar_tools)

print("📋 Available Scheduler methods:")
for method_name in dir(scheduler):
    if not method_name.startswith('_') and callable(getattr(scheduler, method_name)):
        print(f"  - {method_name}")

# TEST: Use GoogleCalendarTools directly to see if it works
print("\n📋 Available GoogleCalendarTools methods:")
for method_name in dir(calendar_tools):
    if not method_name.startswith('_') and callable(getattr(calendar_tools, method_name)):
        print(f"  - {method_name}")

agent = Agent(
    name=AGENT_CONFIG["name"],
    model=OpenAIChat(
        id="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY")
    ),
    tools=[scheduler],  # TEMPORARILY USE GOOGLECALENDARTOOLS DIRECTLY
    description=AGENT_CONFIG["description"],
    instructions=AGENT_CONFIG["instructions"],
    session_id="agent_session",
    storage=storage,
    markdown=True,
    show_tool_calls=True,
    add_history_to_messages=True,
    num_history_responses=10,
    # Disabled memory features to prevent getting stuck
    enable_agentic_memory=False,
    enable_user_memories=False,
    debug_mode=True,
    reasoning=False
)

# Debug: Check what tools the agent actually has
print("\n🔧 Agent Tools Debug:")
if hasattr(agent, 'tools') and agent.tools:
    for i, tool in enumerate(agent.tools):
        print(f"Tool {i}: {type(tool).__name__}")
        if hasattr(tool, '__dict__'):
            print(f"  Methods: {[m for m in dir(tool) if not m.startswith('_') and callable(getattr(tool, m))]}")



while True:
    user_input = input("\nYou: ").strip()

    if user_input.lower() in ['quit', 'exit']:
        print("\n👋 Goodbye!")
        print("📝 Your conversation is saved!")
        break

    if user_input:
        agent.print_response(user_input)