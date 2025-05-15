
from prompt import prompt
from agno.models.openai import OpenAIChat

# Memory
from agno.storage.agent.sqlite import SqliteAgentStorage
from agno.agent import Agent, AgentMemory


# SDK
from assistant.sdk.todoist import TodoistTools
from assistant.sdk.telegram import TelegramTools

# Tools


todoist_agent = Agent(
    name="Todoist Agent",
    role =prompt["role"],
    instructions=prompt["instructions"],
    description=prompt["description"],
    agent_id="todoist-agent",
    model=OpenAIChat(id="gpt-4.1-mini"),
    memory=AgentMemory(),
    storage=SqliteAgentStorage(table_name="agent_sessions", db_file="brain/memory/agent_storage.db"),
    tools=[TodoistTools()],
    enable_agentic_memory=True,
    enable_user_memories=True,
    add_history_to_messages=True,
    num_history_responses=3,
    markdown=True,
    debug_mode=True,
    show_tool_calls=True,

)

telegram = TelegramTools(agent=todoist_agent, chat_id="0")

if __name__ == "__main__":
    telegram.listen()