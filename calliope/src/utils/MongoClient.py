from datetime import datetime
from functools import lru_cache

import pymongo
from loguru import logger

from calliope.settings import settings


@lru_cache()
def calliope_db_init():
    return MongoWriter()


class MongoWriter:
    def __init__(self) -> None:
        try:
            self.client = pymongo.MongoClient(settings.mongo_uri)
            self.client.server_info()  # Check connection
            self.db = self.client[settings.mongo_db_name]

            # single users collection
            self.users_collection = self.db[settings.mongo_users_collection]

            # groups collection
            self.groups_collection = self.db[settings.mongo_groups_collection]

            logger.info(f"Connected to MongoDB at {settings.mongo_uri}")
        except:
            self.client = None
            logger.error(f"Failed to connect to MongoDB at {settings.mongo_uri}")

    def update(self, update):
        try:
            if str(update.message.chat.type) == "private":
                self.update_single_user(update)
            elif str(update.message.chat.type) in ["group", "supergroup"]:
                self.update_group(update)
        except Exception as e:
            logger.error(f"Error updating user: {e}")

    def add_user(self, update):
        try:
            user = self.users_collection.find_one(
                {"user_id": str(update.message.from_user.id)}
            )
            if not user:
                new_user = self.create_new_user(update)
                self.users_collection.insert_one(new_user)
        except Exception as e:
            logger.error(f"Error adding user: {e}")

    def update_single_user(self, update, time_used=0):
        # update single user if it exists else create a new one
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
            # Lingua di trascrizione: None = auto-detect finché l'utente non
            # sceglie esplicitamente con /lang. La lingua del client Telegram
            # non viene forzata sulla trascrizione.
            "language_code": None,
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
                # None = auto-detect finché non si usa /lang nel gruppo.
                "language_code": None,
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

    def get_language(self, update) -> str | None:
        """Restituisce la lingua di trascrizione impostata per la chat.

        Ritorna il codice lingua salvato oppure ``None`` (nessuna scelta
        esplicita → auto-detect). Non solleva eccezioni se il documento non
        esiste o il tipo di chat non è gestito.
        """
        try:
            if str(update.message.chat.type) == "private":
                document = self.users_collection.find_one(
                    {"user_id": str(update.message.from_user.id)}
                )
            elif str(update.message.chat.type) in ["group", "supergroup"]:
                document = self.groups_collection.find_one(
                    {"group_id": str(update.message.chat.id)}
                )
            else:
                return None
        except Exception as e:
            logger.error(f"Error reading language: {e}")
            return None

        if not document:
            return None
        return document.get("language_code")

    def change_language(self, update, language):
        try:
            if str(update.message.chat.type) == "private":
                self.users_collection.update_one(
                    filter={"user_id": str(update.message.from_user.id)},
                    update={"$set": {"language_code": language}},
                    upsert=True,
                )
            elif str(update.message.chat.type) in ["group", "supergroup"]:
                self.groups_collection.update_one(
                    filter={"group_id": str(update.message.chat.id)},
                    update={"$set": {"language_code": language}},
                    upsert=True,
                )
        except Exception as e:
            logger.error(f"Error changing language: {e}")
            raise
