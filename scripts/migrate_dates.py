"""One-shot: converte le date-stringa esistenti in ``datetime`` UTC.

Le versioni precedenti salvavano ``first_use``/``last_use`` come stringhe
``"%Y-%m-%d %H:%M:%S"``. Lo storage riscritto (step 2.1) usa ``datetime``.
Questo script è idempotente: salta i valori già convertiti.

Uso (da host, Mongo sulla porta mappata):
    CALLIOPE_ENV_FILE=.env.dev uv run python scripts/migrate_dates.py
"""

from datetime import datetime, timezone

import pymongo

from calliope.settings import settings

FMT = "%Y-%m-%d %H:%M:%S"
DATE_FIELDS = ("first_use", "last_use")


def _parse(value):
    if isinstance(value, str):
        try:
            return datetime.strptime(value, FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            return value
    return value


def _date_updates(doc: dict) -> dict:
    return {
        field: _parse(doc[field])
        for field in DATE_FIELDS
        if isinstance(doc.get(field), str)
    }


def main() -> None:
    client = pymongo.MongoClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]
    users = db[settings.mongo_users_collection]
    groups = db[settings.mongo_groups_collection]

    migrated_users = 0
    for doc in users.find({}):
        updates = _date_updates(doc)
        if updates:
            users.update_one({"_id": doc["_id"]}, {"$set": updates})
            migrated_users += 1

    migrated_groups = 0
    for doc in groups.find({}):
        updates = _date_updates(doc)
        members = doc.get("members_stats", [])
        members_changed = False
        for member in members:
            member_updates = _date_updates(member)
            if member_updates:
                member.update(member_updates)
                members_changed = True
        if members_changed:
            updates["members_stats"] = members
        if updates:
            groups.update_one({"_id": doc["_id"]}, {"$set": updates})
            migrated_groups += 1

    print(f"Migration complete: {migrated_users} users, {migrated_groups} groups")


if __name__ == "__main__":
    main()
