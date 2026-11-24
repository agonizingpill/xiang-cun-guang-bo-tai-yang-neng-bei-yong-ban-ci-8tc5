from core.records import get, update
from domain.airslots_model import airslots


def mark_offline(conn, user, data):
    get(conn, airslots, data.airslot, lock=True)
    return update(conn, airslots, data.airslot, offline=data.offline)
