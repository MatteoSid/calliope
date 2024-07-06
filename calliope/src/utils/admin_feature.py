import os
from pathlib import Path

import requests
from loguru import logger

TOKEN_PATH = Path("TOKEN.txt")
TOKEN_CHAT_ID_PATH = Path("TOKEN_CHAT_ID.txt")


def markdown_escape(text):
    # special_chars = ["_", "*", "[", "]", "(", ")", "#", "+", "-", ".", "!", "`", "@"]
    special_chars = ["_", "*", "[", "]", "#", "+", "-", ".", "!", "`"]
    for char in special_chars:
        text = text.replace(char, f"\{char}")
    return text


def send_to_admin(message):

    message = markdown_escape(message)

    send_text = (
        "https://api.telegram.org/bot"
        + os.environ.get("TELEGRAM_TOKEN")
        + "/sendMessage?chat_id="
        + os.environ.get("ADMIN_CHAT_ID")
        + "&parse_mode=Markdown&text="
        + message
    )

    response = requests.get(send_text)
    if response.status_code != 200:
        logger.error(f"Error sending message to admin: {response}")

    return response.json()


if __name__ == "__main__":
    test = send_to_admin("Messaggio di prova")
    print(test)
