import os
from datetime import datetime
from functools import lru_cache

import pymongo
from loguru import logger

from calliope.src.configs_manager import settings

mongo_host = os.environ.get("MONGO_HOST", "localhost")


@lru_cache()
def calliope_db_init():
    return MongoWriter()


class MongoWriter:
    def __init__(self) -> None:
        self.client = pymongo.MongoClient(
            f"mongodb://{mongo_host}:{settings['mongodb']['port']}",
        )
        self.db = self.client[settings["mongodb"]["db_name"]]

        # create collections
        self.db.create_collection("users_collection", check_exists=False)
        self.db.create_collection("groups_collection", check_exists=False)

        # single users collection
        self.users_collection = self.db[settings["mongodb"]["users_collection"]]

        # groups collection
        self.groups_collection = self.db[settings["mongodb"]["groups_collection"]]

        logger.info(
            f"Connected to MongoDB at {mongo_host}:{settings['mongodb']['port']}"
        )

    def update(self, update):
        try:
            if str(update.message.chat.type) == "private":
                self.update_single_user(update)
            elif str(update.message.chat.type) in ["group", "supergroup"]:
                self.update_group(update)
        except Exception as e:
            logger.error(f"Error saving user: {e}")

    def add_user(self, update):
        user = self.users_collection.find_one(
            {"user_id": str(update.message.from_user.id)}
        )
        if not user:
            new_user = self.create_new_user(update)
            self.users_collection.insert_one(new_user)

    def update_single_user(self, update, time_used=0):
        # check if user already exists
        self.add_user(update)

        self.users_collection.update_one(
            filter={"user_id": str(update.message.from_user.id)},
            update={
                "$set": {"last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                "$inc": {
                    "times_used": 1,
                    "total_speech_time": update.message.voice.duration,
                },
            },
        )

    def create_new_user(self, update):
        new_user = {
            "first_name": update.message.from_user.first_name,
            "username": update.message.from_user.username,
            "user_id": str(update.message.from_user.id),
            "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "times_used": 0,
            "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_speech_time": 0,
            "language_code": update.message.from_user.language_code,
        }

        return new_user

    def update_group(self, update):
        # check if group already exists
        group = self.groups_collection.find_one(
            {"group_id": str(str(update.message.chat.id))}
        )

        # se il gruppo non esiste ne creo uno con l'utente che l'ha usato la prima volta
        if not group:
            new_group = {
                "group_name": update.message.chat.title,
                "group_id": str(update.message.chat.id),
                "first_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "times_used": 0,
                "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "language_code": update.effective_user.language_code,
                "members_stats": [self.create_new_user(update)],
            }
            self.groups_collection.insert_one(new_group)
            logger.info(f"Added new group to database: {update.message.chat.title}")

            self.groups_collection.update_one(
                filter={"group_id": str(update.message.chat.id)},
                update={
                    "$set": {
                        "members_stats.$[elem].last_use": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    },
                    "$inc": {
                        "times_used": 1,
                        "members_stats.$[elem].times_used": 1,
                        "members_stats.$[elem].total_speech_time": update.message.voice.duration,
                    },
                },
                array_filters=[{"elem.user_id": str(update.message.from_user.id)}],
            )

        # se il gruppo esiste aggiorno l'utente che l'ha appena usato e se non c'è lo aggiungo
        else:
            # cerco se l'utente esiste, se non esiste lo aggiungo
            result = self.groups_collection.find_one(
                {
                    "group_id": str(update.message.chat.id),
                    "members_stats": {
                        "$elemMatch": {"user_id": str(update.message.from_user.id)}
                    },
                }
            )
            if not result:
                self.groups_collection.update_one(
                    filter={"group_id": str(update.message.chat.id)},
                    update={
                        "$push": {"members_stats": self.create_new_user(update)},
                    },
                )
                logger.info(f"Added new user to group: {update.message.chat.id}")

            # aggiorno sia l'utente che il gruppo
            self.groups_collection.update_one(
                filter={"group_id": str(update.message.chat.id)},
                update={
                    "$set": {
                        "members_stats.$[elem].last_use": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    "$inc": {
                        "times_used": 1,
                        "members_stats.$[elem].times_used": 1,
                        "members_stats.$[elem].total_speech_time": update.message.voice.duration,
                    },
                },
                array_filters=[{"elem.user_id": str(update.message.from_user.id)}],
            )

    def get_language(self, update):
        if str(update.message.chat.type) == "private":
            language = self.users_collection.find_one(
                {"user_id": str(update.message.from_user.id)}
            )

        elif str(update.message.chat.type) in ["group", "supergroup"]:
            language = self.groups_collection.find_one(
                {"group_id": str(update.message.chat.id)}
            )

        return language["language_code"] or "en"

    def change_language(self, update, language):
        if str(update.message.chat.type) == "private":
            self.users_collection.update_one(
                filter={"user_id": str(update.message.from_user.id)},
                update={"$set": {"language_code": language}},
            )
        elif str(update.message.chat.type) in ["group", "supergroup"]:
            self.groups_collection.update_one(
                filter={"group_id": str(update.message.chat.id)},
                update={"$set": {"language_code": language}},
            )
