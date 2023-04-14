import json
from datetime import datetime


def save_user(update):
    file_path = "users.json"
    username = update.message.from_user.username
    first_name = update.message.from_user.first_name
    language_code = update.message.from_user.language_code
    # duration = timedelta(seconds=update.message.voice.duration)
    duration = update.message.voice.duration

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"single_users": {}, "groups": {}}

    if str(update.message.chat.type) == "private":
        if username not in data["single_users"]:
            data["single_users"][username] = {
                "first_name": first_name,
                "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "times_used": 1,
                "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "mean_audio_length": duration,
                "total_speech_time": duration,
                "language_code": language_code,
            }
        else:
            data["single_users"][username]["times_used"] += 1
            data["single_users"][username]["last_use"] = str(datetime.now().date())
            data["single_users"][username]["total_speech_time"] += duration
            data["single_users"][username]["mean_audio_length"] = (
                data["single_users"][username]["total_speech_time"]
                / data["single_users"][username]["times_used"]
            )

    elif str(update.message.chat.type) == "group":
        group_name = update.message.chat.title

        if group_name not in data["groups"]:
            data["groups"][group_name] = {
                "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "times_used": 1,
                "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "mean_audio_length": duration,
                "total_speech_time": duration,
                "language_code": language_code,
            }
        else:
            data["groups"][group_name]["times_used"] += 1
            data["groups"][group_name]["last_use"] = str(datetime.now().date())
            data["groups"][group_name]["total_speech_time"] += duration
            data["groups"][group_name]["mean_audio_length"] = (
                data["groups"][group_name]["total_speech_time"]
                / data["groups"][group_name]["times_used"]
            )

    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)