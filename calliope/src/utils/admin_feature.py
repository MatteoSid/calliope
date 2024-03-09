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
    if os.path.exists(TOKEN_PATH):
        bot_token = Path(TOKEN_PATH).read_text()
    else:
        logger.error(f"File {TOKEN_PATH} not found")
        return

    if os.path.exists(TOKEN_CHAT_ID_PATH):
        bot_chatID = Path(TOKEN_CHAT_ID_PATH).read_text()
    else:
        logger.error(f"File {TOKEN_CHAT_ID_PATH} not found")
        return

    message = markdown_escape(message)

    send_text = (
        "https://api.telegram.org/bot"
        + bot_token
        + "/sendMessage?chat_id="
        + bot_chatID
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
