from sqlalchemy import select

from core.records import insert, need, scan, update
from domain.airslots_model import airslots
from domain.batteries_model import batteries


def register_battery(conn, user, data):
    need(1 <= data.shift_hours <= 6, '整班时长须在 1 到 6 小时之间')
    need(data.capacity_wh > 0, '电池容量必须为正')
    clash = conn.execute(select(batteries).where(batteries.c.meter == data.meter)).mappings().first()
    need(clash is None or clash['code'] == data.code, '该电表已登记另一块电池')
    existing = conn.execute(select(batteries).where(batteries.c.code == data.code)).mappings().first()
    if existing is None:
        return insert(conn, batteries, code=data.code, meter=data.meter,
                      shift_hours=data.shift_hours, capacity_wh=data.capacity_wh, margin_wh=0.0)
    need(not any(x['battery'] == data.code for x in scan(conn, airslots)),
         '电池已挂载节目档，整班时长不可再改')
    return update(conn, batteries, data.code, meter=data.meter, shift_hours=data.shift_hours,
                  capacity_wh=data.capacity_wh)


def slots_of(conn, battery_code):
    return [dict(row) for row in conn.execute(
        select(airslots).where(airslots.c.battery == battery_code)
        .order_by(airslots.c.hour, airslots.c.code)).mappings()]
