import os
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agent.tools.sdk.telegram import TelegramTools
from dotenv import load_dotenv

load_dotenv()

telegram_token = os.getenv('TELEGRAM_TOKEN')
chat_id = os.getenv('CHAT_ID')


agent = Agent(
    name="telegram",
    model=OpenAIChat(id="gpt-4.1-mini"),
    tools=[TelegramTools(token=telegram_token, chat_id=chat_id)],
    debug_mode=True,
    show_tool_calls=True
)

agent.print_response("Listen to a message from the user and then respond to him")