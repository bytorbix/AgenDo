import os
import time
from typing import Optional, Union

import httpx
from dotenv import load_dotenv

from agno.tools import Toolkit
from agno.utils.log import log_debug, logger
from agno.agent import Agent

load_dotenv()


class TelegramTools(Toolkit):
    base_url = "https://api.telegram.org"

    def __init__(self, agent: Agent,chat_id: Union[str, int], token: Optional[str] = None, **kwargs):
        super().__init__(name="telegram", **kwargs)

        self.token = token or os.getenv("TELEGRAM_TOKEN")
        if not self.token:
            logger.error("TELEGRAM_TOKEN not set. Please set the TELEGRAM_TOKEN environment variable.")
        self.agent = agent
        self.chat_id = chat_id
        self.last_update_id = None

        self.register(self.send_message)

    def _call_post_method(self, method, *args, **kwargs):
        return httpx.post(f"{self.base_url}/bot{self.token}/{method}", *args, **kwargs)

    def _call_get_method(self, method, *args, **kwargs):
        return httpx.get(f"{self.base_url}/bot{self.token}/{method}", *args, **kwargs)

    def get_updates(self):
        params = {"timeout": 25}
        if self.last_update_id:
            params["offset"] = self.last_update_id + 1

        r = self._call_get_method("getUpdates", params=params)
        if r.status_code != 200:
            return []
        return r.json().get("result", [])

    def send_message(self, message) -> str:
        if hasattr(message, "content"):
            message = message.content
        log_debug(f"Sending telegram message: {message}")
        response = self._call_post_method("sendMessage", json={"chat_id": self.chat_id, "text": message})
        try:
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            return f"An error occurred: {e}"

    def listen(self):
        logger.info("[TelegramTools] Listening for messages...")

        while True:
            try:
                updates = self.get_updates()
                for u in updates:
                    self.last_update_id = u["update_id"]
                    msg = u.get("message", {})
                    text = msg.get("text")
                    chat_id = msg.get("chat", {}).get("id")
                    if text and chat_id:
                        self.chat_id = chat_id
                        session_id = f"telegram-{chat_id}"
                        user_id = str(chat_id)  # Using chat_id as user_id
                        response = self.agent.run(
                            text,
                            session_id=session_id,
                            user_id=user_id
                        )
                        self.send_message(response)
            except httpx.ReadTimeout:
                continue
            except Exception as e:
                logger.warning(f"[TelegramTools] Listen error: {e}")
                time.sleep(2)