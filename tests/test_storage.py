"""Test dello storage con MongoDB in-memory (mongomock).

Copre gli upsert idempotenti, gli incrementi con la durata (C2), la lingua sui
casi limite (C7) e le aggregazioni globali.
"""


def test_add_user_idempotent(storage, make_update):
    upd = make_update(user_id=1)
    assert storage.add_user(upd) is True  # creato ora
    assert storage.add_user(upd) is False  # già presente, nessun doppione
    assert storage.users_collection.count_documents({"user_id": "1"}) == 1


def test_update_private_increments_with_duration(storage, make_update):
    upd = make_update(user_id=7)
    # C2: la durata (es. video note) viene sommata correttamente.
    assert storage.update(upd, duration=40) == "user"  # chat nuova
    assert storage.update(upd, duration=25) is None  # non più nuova
    doc = storage.users_collection.find_one({"user_id": "7"})
    assert doc["times_used"] == 2
    assert doc["total_speech_time"] == 65


def test_get_language_defaults_and_roundtrip(storage, make_update):
    upd = make_update(user_id=3)
    # C7: nessun documento → None, nessuna eccezione.
    assert storage.get_language(upd) is None
    storage.change_language(update=upd, language="es")
    assert storage.get_language(upd) == "es"
    storage.change_language(update=upd, language=None)  # torna ad auto
    assert storage.get_language(upd) is None


def test_group_update_creates_group_and_member(storage, make_update):
    # Nota: mongomock non implementa gli array filters usati per l'incremento
    # per-membro (step 3 di _record_group), quindi update() logga l'errore e
    # ritorna None; l'upsert del gruppo e il push del membro (che non usano array
    # filters) restano verificabili. L'incremento per-membro è coperto dal test
    # d'integrazione su MongoDB reale (step 2.1).
    upd = make_update(user_id=10, chat_type="group", chat_id=-500, chat_title="Team")
    storage.update(upd, duration=15)
    doc = storage.get_group_stats(upd)
    assert doc is not None
    assert doc["group_name"] == "Team"
    members = {m["user_id"]: m for m in doc.get("members_stats", [])}
    assert "10" in members


def test_global_stats_aggregation(storage, make_update):
    storage.update(make_update(user_id=1), duration=30)
    storage.update(make_update(user_id=2), duration=20)
    stats = storage.global_stats()
    assert stats["total_users"] == 2
    assert stats["total_transcriptions"] == 2
    assert stats["total_speech_seconds"] == 50


def test_get_all_chat_ids(storage, make_update):
    storage.update(make_update(user_id=1), duration=1)
    storage.update(
        make_update(user_id=2, chat_type="group", chat_id=-99, chat_title="G"),
        duration=1,
    )
    users, groups = storage.get_all_chat_ids()
    assert 1 in users
    assert -99 in groups


def test_degraded_mode_is_safe(make_settings, monkeypatch):
    # Se il ping fallisce, lo storage resta in modalità degradata dichiarata.
    import calliope.storage.mongo as mongo_mod

    class _BoomClient:
        def __init__(self, *a, **kw):
            pass

        @property
        def admin(self):
            raise RuntimeError("no mongo")

    monkeypatch.setattr(mongo_mod.pymongo, "MongoClient", _BoomClient)
    store = mongo_mod.MongoStorage(make_settings())
    assert store.available is False
    # i metodi ritornano default sicuri, senza sollevare
    assert store.add_user(_no_update()) is False
    assert store.global_stats() is None
    assert store.get_all_chat_ids() == ([], [])


def _no_update():
    from types import SimpleNamespace

    return SimpleNamespace()
