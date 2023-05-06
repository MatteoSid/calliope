import json
from datetime import datetime


def add_user(first_name: str, username: str, language_code: str, duration: int) -> dict:
    return {
        "first_name": first_name,
        "username": username,
        "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "times_used": 1,
        "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_speech_time": duration,
        "language_code": language_code,
    }


def update_user(old_data: dict, duration: int) -> dict:
    old_data["times_used"] += 1
    old_data["last_use"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old_data["total_speech_time"] += duration
    return old_data


def save_user(update) -> None:
    file_path = "stast.json"
    user_id = str(update.message.from_user.id)
    username = update.message.from_user.username
    first_name = update.message.from_user.first_name
    language_code = update.message.from_user.language_code
    try:
        duration = update.message.voice.duration
    except AttributeError:
        duration = update.message.video_note.duration

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"single_users": {}, "groups": {}}

    if str(update.message.chat.type) == "private":
        if user_id not in data["single_users"]:
            data["single_users"][user_id] = add_user(
                first_name, username, language_code, duration
            )
        else:
            data["single_users"][user_id] = update_user(
                data["single_users"][user_id], duration
            )

    elif str(update.message.chat.type) in ["group", "supergroup"]:
        group_id = str(update.message.chat.id)

        if group_id not in data["groups"]:
            data["groups"][group_id] = {
                "group_name": update.message.chat.title,
                "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "times_used": 1,
                "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "members_stats": {
                    username: add_user(first_name, language_code, duration)
                },
            }
        else:
            data["groups"][group_id]["group_name"] = update.message.chat.title
            data["groups"][group_id]["times_used"] += 1
            data["groups"][group_id]["last_use"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if username not in data["groups"][group_id]["members_stats"]:
                data["groups"][group_id]["members_stats"][username] = add_user(
                    first_name, language_code, duration
                )
            else:
                data["groups"][group_id]["members_stats"][username] = update_user(
                    data["groups"][group_id]["members_stats"][username], duration
                )

    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)
