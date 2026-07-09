from datetime import datetime

import pymongo
from loguru import logger

from calliope.settings import Settings


class MongoStorage:
    """Accesso a MongoDB per utenti, gruppi e statistiche.

    Istanziato una sola volta all'avvio e iniettato negli handler. Se la
    connessione fallisce resta in modalità degradata (``client`` = None) e i
    metodi loggano l'errore senza sollevare.
    """

    def __init__(self, settings: Settings) -> None:
        self.client: pymongo.MongoClient | None = None
        try:
            self.client = pymongo.MongoClient(settings.mongo_uri)
            self.client.server_info()  # Check connection
            self.db = self.client[settings.mongo_db_name]
            self.users_collection = self.db[settings.mongo_users_collection]
            self.groups_collection = self.db[settings.mongo_groups_collection]
            logger.info(f"Connected to MongoDB at {settings.mongo_uri}")
        except Exception:
            self.client = None
            logger.error(f"Failed to connect to MongoDB at {settings.mongo_uri}")

    def update(self, update, duration: int = 0) -> str | None:
        """Registra un uso della chat.

        Args:
            update: l'update Telegram.
            duration: durata in secondi del media (voice/video_note/video),
                passata esplicitamente perché ``message.voice`` non esiste per i
                video note.

        Returns:
            ``"user"`` se è stato registrato un nuovo utente (chat privata),
            ``"group"`` se è stato registrato un nuovo gruppo, altrimenti
            ``None``.
        """
        try:
            if str(update.message.chat.type) == "private":
                created = self.update_single_user(update, duration)
                return "user" if created else None
            elif str(update.message.chat.type) in ["group", "supergroup"]:
                created = self.update_group(update, duration)
                return "group" if created else None
        except Exception as e:
            logger.error(f"Error updating user: {e}")
        return None

    def add_user(self, update) -> bool:
        """Crea il documento utente se assente. Ritorna True se è stato creato."""
        try:
            user = self.users_collection.find_one(
                {"user_id": str(update.message.from_user.id)}
            )
            if not user:
                self.users_collection.insert_one(self.create_new_user(update))
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    def update_single_user(self, update, duration: int = 0) -> bool:
        # update single user if it exists else create a new one
        created = self.add_user(update)

        self.users_collection.update_one(
            filter={"user_id": str(update.message.from_user.id)},
            update={
                "$set": {"last_use": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                "$inc": {
                    "times_used": 1,
                    "total_speech_time": duration,
                },
            },
        )
        return created

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

    def update_group(self, update, duration: int = 0) -> bool:
        """Aggiorna le statistiche del gruppo e del membro che ha usato il bot.

        Ritorna True se il gruppo è stato creato ora (primo uso)."""
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
                        "members_stats.$[elem].total_speech_time": duration,
                    },
                },
                array_filters=[{"elem.user_id": str(update.message.from_user.id)}],
            )
            return True

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
                        "members_stats.$[elem].total_speech_time": duration,
                    },
                },
                array_filters=[{"elem.user_id": str(update.message.from_user.id)}],
            )
            return False

    def get_user_stats(self, update):
        """Ritorna il documento statistiche dell'utente, o ``None`` se assente
        o se Mongo non è raggiungibile."""
        try:
            return self.users_collection.find_one(
                {"user_id": str(update.message.from_user.id)}
            )
        except Exception as e:
            logger.error(f"Error reading user stats: {e}")
            return None

    def get_group_stats(self, update):
        """Ritorna il documento statistiche del gruppo, o ``None`` se assente
        o se Mongo non è raggiungibile."""
        try:
            return self.groups_collection.find_one(
                {"group_id": str(update.message.chat.id)}
            )
        except Exception as e:
            logger.error(f"Error reading group stats: {e}")
            return None

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

    def global_stats(self) -> dict | None:
        """Statistiche globali per il pannello admin.

        Ritorna un dizionario con utenti totali, gruppi totali, trascrizioni
        totali e secondi di parlato processati; ``None`` se Mongo non è
        raggiungibile.
        """
        try:
            total_users = self.users_collection.count_documents({})
            total_groups = self.groups_collection.count_documents({})

            user_agg = list(
                self.users_collection.aggregate(
                    [
                        {
                            "$group": {
                                "_id": None,
                                "transcriptions": {"$sum": "$times_used"},
                                "speech": {"$sum": "$total_speech_time"},
                            }
                        }
                    ]
                )
            )
            group_agg = list(
                self.groups_collection.aggregate(
                    [
                        {
                            "$group": {
                                "_id": None,
                                "transcriptions": {"$sum": "$times_used"},
                            }
                        }
                    ]
                )
            )
            member_agg = list(
                self.groups_collection.aggregate(
                    [
                        {"$unwind": "$members_stats"},
                        {
                            "$group": {
                                "_id": None,
                                "speech": {"$sum": "$members_stats.total_speech_time"},
                            }
                        },
                    ]
                )
            )

            user_tx = user_agg[0]["transcriptions"] if user_agg else 0
            user_speech = user_agg[0]["speech"] if user_agg else 0
            group_tx = group_agg[0]["transcriptions"] if group_agg else 0
            member_speech = member_agg[0]["speech"] if member_agg else 0

            return {
                "total_users": total_users,
                "total_groups": total_groups,
                "total_transcriptions": user_tx + group_tx,
                "total_speech_seconds": user_speech + member_speech,
            }
        except Exception as e:
            logger.error(f"Error computing global stats: {e}")
            return None

    def get_all_chat_ids(self) -> tuple[list[int], list[int]]:
        """Ritorna (user_ids, group_ids) di tutti i destinatari registrati.

        Ritorna liste vuote se Mongo non è raggiungibile.
        """
        try:
            users = [
                int(doc["user_id"])
                for doc in self.users_collection.find({}, {"user_id": 1})
                if doc.get("user_id")
            ]
            groups = [
                int(doc["group_id"])
                for doc in self.groups_collection.find({}, {"group_id": 1})
                if doc.get("group_id")
            ]
            return users, groups
        except Exception as e:
            logger.error(f"Error reading recipients: {e}")
            return [], []
