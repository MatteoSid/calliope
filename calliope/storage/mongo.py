"""Accesso a MongoDB per utenti, gruppi e statistiche.

Operazioni atomiche (upsert con ``$set``/``$inc``/``$setOnInsert``), date come
``datetime`` UTC, indici unici, modalità degradata dichiarata (``available``).
Istanziato una sola volta all'avvio e iniettato negli handler.
"""

from datetime import datetime, timezone

import pymongo
from loguru import logger

from calliope.settings import Settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MongoStorage:
    def __init__(self, settings: Settings) -> None:
        self.available = False
        self.client: pymongo.MongoClient | None = None
        try:
            self.client = pymongo.MongoClient(
                settings.mongo_uri, serverSelectionTimeoutMS=5000
            )
            self.client.admin.command("ping")  # verifica la connessione
            self.db = self.client[settings.mongo_db_name]
            self.users_collection = self.db[settings.mongo_users_collection]
            self.groups_collection = self.db[settings.mongo_groups_collection]
            self._ensure_indexes()
            self.available = True
            logger.info(f"Connected to MongoDB at {settings.mongo_uri}")
        except Exception as e:
            self.client = None
            logger.warning(
                f"MongoDB unavailable ({e}); storage in degraded mode: "
                "il bot trascrive ma non registra statistiche."
            )

    def _ensure_indexes(self) -> None:
        try:
            self.users_collection.create_index("user_id", unique=True)
            self.groups_collection.create_index("group_id", unique=True)
        except Exception as e:
            logger.warning(f"Could not create unique indexes: {e}")

    def close(self) -> None:
        """Chiude il client MongoDB (usato nel graceful shutdown, step 3.5)."""
        if self.client is not None:
            self.client.close()
            logger.info("MongoDB client closed")

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _new_member(update) -> dict:
        """Documento di un utente/membro nuovo (times_used e speech a zero)."""
        user = update.message.from_user
        now = _utcnow()
        return {
            "user_id": str(user.id),
            "username": user.username,
            "first_name": user.first_name,
            "first_use": now,
            "last_use": now,
            "times_used": 0,
            "total_speech_time": 0,
            "language_code": None,
        }

    # -------------------------------------------------------------- write API
    def add_user(self, update) -> bool:
        """Crea il documento utente se assente (nessun incremento).

        Ritorna True se l'utente è stato creato ora (usato per la notifica admin).
        """
        if not self.available:
            return False
        try:
            member = self._new_member(update)
            set_on_insert = {k: v for k, v in member.items() if k != "user_id"}
            result = self.users_collection.update_one(
                {"user_id": member["user_id"]},
                {"$setOnInsert": set_on_insert},
                upsert=True,
            )
            return result.upserted_id is not None
        except Exception as e:
            logger.error(f"add_user failed: {e}")
            return False

    def update(self, update, duration: int = 0) -> str | None:
        """Registra un uso e ritorna "user"/"group" se la chat è nuova."""
        if not self.available:
            return None
        try:
            chat_type = str(update.message.chat.type)
            if chat_type == "private":
                return "user" if self._record_user(update, duration) else None
            if chat_type in ("group", "supergroup"):
                return "group" if self._record_group(update, duration) else None
        except Exception as e:
            logger.error(f"update failed: {e}")
        return None

    def _record_user(self, update, duration: int) -> bool:
        """Upsert atomico dell'utente con incremento. True se creato ora."""
        member = self._new_member(update)
        now = _utcnow()
        result = self.users_collection.update_one(
            {"user_id": member["user_id"]},
            {
                "$set": {
                    "last_use": now,
                    "username": member["username"],
                    "first_name": member["first_name"],
                },
                "$inc": {"times_used": 1, "total_speech_time": duration},
                "$setOnInsert": {"first_use": now, "language_code": None},
            },
            upsert=True,
        )
        return result.upserted_id is not None

    def _record_group(self, update, duration: int) -> bool:
        """Upsert atomico di gruppo + membro. True se il gruppo è creato ora."""
        group_id = str(update.message.chat.id)
        member = self._new_member(update)
        now = _utcnow()

        # 1) gruppo (livello aggregato)
        result = self.groups_collection.update_one(
            {"group_id": group_id},
            {
                "$set": {"group_name": update.message.chat.title, "last_use": now},
                "$inc": {"times_used": 1},
                "$setOnInsert": {
                    "first_use": now,
                    "language_code": None,
                    "members_stats": [],
                },
            },
            upsert=True,
        )
        created = result.upserted_id is not None

        # 2) aggiunge il membro solo se non presente (atomico via filtro)
        self.groups_collection.update_one(
            {"group_id": group_id, "members_stats.user_id": {"$ne": member["user_id"]}},
            {"$push": {"members_stats": member}},
        )

        # 3) incrementa le statistiche del membro
        self.groups_collection.update_one(
            {"group_id": group_id},
            {
                "$set": {
                    "members_stats.$[m].last_use": now,
                    "members_stats.$[m].username": member["username"],
                    "members_stats.$[m].first_name": member["first_name"],
                },
                "$inc": {
                    "members_stats.$[m].times_used": 1,
                    "members_stats.$[m].total_speech_time": duration,
                },
            },
            array_filters=[{"m.user_id": member["user_id"]}],
        )
        return created

    def change_language(self, update, language: str | None) -> None:
        """Imposta la lingua di trascrizione (upsert). Propaga l'errore DB."""
        if not self.available:
            raise RuntimeError("storage unavailable")
        try:
            chat_type = str(update.message.chat.type)
            if chat_type == "private":
                self.users_collection.update_one(
                    {"user_id": str(update.message.from_user.id)},
                    {"$set": {"language_code": language}},
                    upsert=True,
                )
            elif chat_type in ("group", "supergroup"):
                self.groups_collection.update_one(
                    {"group_id": str(update.message.chat.id)},
                    {"$set": {"language_code": language}},
                    upsert=True,
                )
        except Exception as e:
            logger.error(f"Error changing language: {e}")
            raise

    # --------------------------------------------------------------- read API
    def get_language(self, update) -> str | None:
        """Lingua di trascrizione impostata, o None (auto-detect)."""
        if not self.available:
            return None
        try:
            chat_type = str(update.message.chat.type)
            if chat_type == "private":
                document = self.users_collection.find_one(
                    {"user_id": str(update.message.from_user.id)}
                )
            elif chat_type in ("group", "supergroup"):
                document = self.groups_collection.find_one(
                    {"group_id": str(update.message.chat.id)}
                )
            else:
                return None
        except Exception as e:
            logger.error(f"Error reading language: {e}")
            return None
        return document.get("language_code") if document else None

    def get_user_stats(self, update) -> dict | None:
        if not self.available:
            return None
        try:
            return self.users_collection.find_one(
                {"user_id": str(update.message.from_user.id)}
            )
        except Exception as e:
            logger.error(f"Error reading user stats: {e}")
            return None

    def get_group_stats(self, update) -> dict | None:
        if not self.available:
            return None
        try:
            return self.groups_collection.find_one(
                {"group_id": str(update.message.chat.id)}
            )
        except Exception as e:
            logger.error(f"Error reading group stats: {e}")
            return None

    def global_stats(self) -> dict | None:
        """Statistiche globali per il pannello admin."""
        if not self.available:
            return None
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
        """(user_ids, group_ids) di tutti i destinatari registrati."""
        if not self.available:
            return [], []
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
