from sqlalchemy import select

from core.records import get, insert, need, scan, update
from domain.airslots_model import airslots
from domain.batteries_model import batteries
from domain.reserves_model import reserves
from domain.switchcards_model import switchcards

# 浮点余量：并发判断时避免舍入误差误判超额。
QUOTA_EPS = 1e-6
ISSUED = '值守签发'
WITHDRAWN = '已撤卡'
HANDOVER_PREFIX = '已闭台 '


def _active_cards(conn):
    """占额卡片：已签发与已交接（已撤卡释放额度，不再占额）。"""
    rows = conn.execute(select(switchcards).where(switchcards.c.state != WITHDRAWN)).mappings()
    return [dict(row) for row in rows]


def issue_switch(conn, user, data):
    plan = get(conn, reserves, data.reserve, lock=True)
    slot = get(conn, airslots, plan['airslot'], lock=True)
    battery = get(conn, batteries, slot['battery'], lock=True)
    need(data.source in ('本地时钟', '台外校时'), '时钟源不在电台名录')
    need(not slot['offline'] or data.source == '本地时钟', '版权离线期间只能接本地时钟')
    # 发卡额要覆盖该档预测（点预测；公用余量在电池总额度里统一预留）。
    need(data.approved_wh + QUOTA_EPS >= plan['prediction_wh'],
         f"锁定电量须覆盖该档预测 {plan['prediction_wh']} Wh")
    locked = sum(card['approved_wh'] for card in _active_cards(conn)
                 if _card_battery(conn, card) == battery['code'])
    available = battery['capacity_wh'] - battery['margin_wh'] - locked
    need(data.approved_wh <= available + QUOTA_EPS,
         f"并发发卡超额：扣公用余量 {battery['margin_wh']} Wh 后仅剩 {round(available, 3)} Wh")
    return insert(conn, switchcards, **data.model_dump(), state=ISSUED)


def _card_battery(conn, card):
    reserve = get(conn, reserves, card['reserve'])
    slot = get(conn, airslots, reserve['airslot'])
    return slot['battery']


def withdraw(conn, user, data):
    """撤卡：已签发卡片释放额度；重试幂等，不重复退电量。"""
    card = get(conn, switchcards, data.card, lock=True)
    if card['state'] == WITHDRAWN:
        return {'code': card['code'], 'state': WITHDRAWN, 'refunded_wh': 0, 'idempotent': True}
    # 撤卡和交接撞车时认先办成的：已交接的仍占额，撤卡被拒。
    need(not card['state'].startswith(HANDOVER_PREFIX), '卡片已完成闭台交接，不能撤卡')
    update(conn, switchcards, data.card, state=WITHDRAWN)
    return {'code': card['code'], 'state': WITHDRAWN,
            'refunded_wh': card['approved_wh'], 'idempotent': False}


def handover(conn, user, data):
    item = get(conn, switchcards, data.card, lock=True)
    need(item['state'] == ISSUED, '此备播卡已交接或已撤卡')
    need(data.note.startswith('WR-'), '缺少值守纸本回执编号')
    return update(conn, switchcards, data.card, state=HANDOVER_PREFIX + data.note)


def board(conn):
    """备播看板：各电池已锁电量、公用余量、还能分多少，以及各档明细。"""
    cards = {row['code']: row for row in scan(conn, switchcards)}
    reserve_rows = {row['code']: row for row in scan(conn, reserves)}
    slot_rows = {row['code']: row for row in scan(conn, airslots)}
    output = []
    for battery in scan(conn, batteries):
        slots = [slot for slot in slot_rows.values() if slot['battery'] == battery['code']]
        slot_views = []
        locked_total = 0.0
        for slot in sorted(slots, key=lambda x: (x['hour'], x['code'])):
            slot_cards = [card for card in cards.values()
                          if reserve_rows.get(card['reserve'], {}).get('airslot') == slot['code']]
            active = [card for card in slot_cards if card['state'] != WITHDRAWN]
            locked = sum(card['approved_wh'] for card in active)
            locked_total += locked
            latest_reserve = next((reserve_rows[card['reserve']] for card in reversed(slot_cards)
                                   if card['reserve'] in reserve_rows), None)
            slot_views.append({
                'airslot': slot['code'],
                'title': slot['title'],
                'hour': slot['hour'],
                'prediction_wh': latest_reserve['prediction_wh'] if latest_reserve else None,
                'locked_wh': round(locked, 3),
                'card_states': [card['state'] for card in slot_cards],
            })
        available = battery['capacity_wh'] - battery['margin_wh'] - locked_total
        output.append({
            'battery': battery['code'],
            'meter': battery['meter'],
            'shift_hours': battery['shift_hours'],
            'capacity_wh': battery['capacity_wh'],
            'margin_wh': battery['margin_wh'],
            'locked_wh': round(locked_total, 3),
            'allocatable_wh': round(available, 3),
            'slots': slot_views,
        })
    return output
