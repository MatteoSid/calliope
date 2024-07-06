import json
from datetime import datetime

from loguru import logger
from pydantic import BaseModel

from .admin_feature import send_to_admin

# def add_user(first_name: str, username: str, language_code: str, duration: int) -> dict:
#     logger.info(f"{first_name} (@{username}) used Calliope for the first time")
#     send_to_admin(f"{first_name} (@{username}) used Calliope for the first time")
#     return {
#         "first_name": first_name,
#         "username": username,
#         "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#         "times_used": 1,
#         "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#         "total_speech_time": duration,
#         "language_code": language_code,
#     }


# def update_user(old_data: dict, duration: int) -> dict:
#     old_data["times_used"] += 1
#     old_data["last_use"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     old_data["total_speech_time"] += duration
#     return old_data


def save_user(update) -> None:
    file_path = "stast.json"
    user_id = str(update.message.from_user.id)
    username = update.message.from_user.username
    first_name = update.message.from_user.first_name
    language_code = update.message.from_user.language_code
    try:
        duration = update.message.voice.duration
    except AttributeError:
        try:
            duration = update.message.video_note.duration
        except AttributeError:
            duration = 0

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"single_users": {}, "groups": {}}

    # check if user is in single_users
    if str(update.message.chat.type) == "private":
        if user_id not in data["single_users"]:
            data["single_users"][user_id] = add_user(
                first_name, username, language_code, duration
            )
        else:
            data["single_users"][user_id] = update_user(
                data["single_users"][user_id], duration
            )

            if data["single_users"][user_id]["username"] != username:
                data["single_users"][user_id]["username"] = username

    # check if user is in groups
    elif str(update.message.chat.type) in ["group", "supergroup"]:
        group_id = str(update.message.chat.id)

        # check if the group is in the database
        if group_id not in data["groups"]:
            data["groups"][group_id] = {
                "group_name": update.message.chat.title,
                "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "times_used": 1,
                "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "members_stats": {
                    username: add_user(first_name, username, language_code, duration)
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
                    first_name=first_name,
                    username=username,
                    language_code=language_code,
                    duration=duration,
                )
            else:
                data["groups"][group_id]["members_stats"][username] = update_user(
                    data["groups"][group_id]["members_stats"][username], duration
                )

    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)


class User(BaseModel):
    id: int
    first_name: str
    username: str
    first_use: str
    used_times: int
    last_use: str
    total_speech_time: int
    language_code: str


class Group(BaseModel):
    id: int
    group_name: str
    first_use: str
    times_used: int
    last_use: str
    members: list[User]


class Users:
    def __init__(self):
        self.load_db()

    def add_user(self, update, chat_type) -> dict:

        try:
            user_id = str(update.message.from_user.id)
            first_name = update.message.from_user.first_name
            username = update.message.from_user.username

            logger.info(f"{first_name} (@{username}) used Calliope for the first time")
            # check if the user is in the database

            new_user = {
                "first_name": first_name,
                "username": username,
                "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "times_used": 0,
                "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_speech_time": 0,
                "language_code": update.message.from_user.language_code,
            }

            if chat_type == "single_users":
                if user_id not in self.data["single_users"]:
                    self.data["single_users"][user_id] = new_user

                    send_to_admin(
                        f"{first_name} (@{username}) used Calliope for the first time"
                    )
            elif chat_type == "groups":
                group_id = str(update.message.chat.id)
                if group_id not in self.data[chat_type]:
                    self.data[chat_type][group_id] = {
                        "group_name": update.message.chat.title,
                        "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "times_used": 1,
                        "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "language_code": "it",
                        "members_stats": {user_id: new_user},
                    }

                    send_to_admin(
                        f"{first_name} (@{username}) used Calliope for the first time in the group {update.message.chat.title}"
                    )

                # if self.data["groups"][group_id]["members_stats"][user_id] == new_user:

            self.save_db()
        except Exception as e:
            logger.error(f"Error saving user: {e}")

        # new_user = User(
        #     first_name=first_name,
        #     username=username,
        #     language_code=language_code,
        #     duration=0,
        # )

    def load_db(self, file_path="stast.json"):
        try:
            with open(file_path, "r") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            logger.info(f"File {file_path} not found. Started with empty data.")
            self.data = {"single_users": {}, "groups": {}}
            self.save_db()

    def save_db(self, file_path="stast.json"):
        with open(file_path, "w") as f:
            json.dump(self.data, f, indent=4)

    def update_user(
        self,
        user_id: str,
        duration: int = 0,
        language_code: str = "",
    ):

        if duration > 0:
            try:
                self.data["single_users"][str(user_id)]["times_used"] += 1
                self.data["single_users"][str(user_id)][
                    "last_use"
                ] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.data["single_users"][str(user_id)]["total_speech_time"] += duration

                self.save_db()

            except Exception as e:
                logger.error(f"Error updating user: {e}")

        if language_code:
            self.data["single_users"][str(user_id)]["language_code"] = language_code
            self.save_db()

    def get_user_language(
        self,
        user_id: str,
    ) -> str:
        return self.data["single_users"][str(user_id)]["language_code"]

    def update_group(
        self,
        group_id: str,
        user_id: str = "",
        duration: int = 0,
        language_code: str = "",
    ):
        if duration > 0:
            try:
                self.data["groups"][group_id]["times_used"] += 1
                self.data["groups"][group_id]["last_use"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                self.data["groups"][group_id]["members_stats"][user_id][
                    "times_used"
                ] += 1
                self.data["groups"][group_id]["members_stats"][user_id][
                    "total_speech_time"
                ] += duration
                self.save_db()
            except Exception as e:
                logger.error(f"Error updating group: {e}")
        if language_code != "":
            self.data["groups"][group_id]["language_code"] = language_code
            self.save_db()

    def get_group_language(
        self,
        group_id: str,
    ) -> str:
        return self.data["groups"][group_id]["language_code"]
