from core.queueing import result, submit
from core.records import get, insert, need, scan, update
from domain.airslots_model import airslots
from domain.batteries_model import batteries
from domain.battery_logs_model import battery_logs
from domain.reserves_model import reserves


def forecast_wh(conn, user, data):
    slot = get(conn, airslots, data.airslot)
    battery = get(conn, batteries, slot['battery'])
    need(battery['meter'] == data.meter, '电表与节目档所属电池不一致，不能跨表预测')
    rows = sorted([x for x in scan(conn, battery_logs)
                   if x['meter'] == data.meter and x['verified']], key=lambda x: x['hour'])
    need(len(rows) >= 36 and all(y['hour'] - x['hour'] == 1 for x, y in zip(rows, rows[1:])),
         '要有连续三十六小时审签读数')
    window = {'code': slot['code'], 'hour': slot['hour'], 'shift_hours': battery['shift_hours']}
    return submit(user, {'window': window, 'rows': rows, 'clear': data.clear})


def save_reserve(conn, user, data):
    run = result(user, data.token)
    window = run['input']['window']
    stats = run['result']
    slot = get(conn, airslots, window['code'], lock=True)
    need(slot['hour'] == window['hour'], '节目时间已变')
    battery = get(conn, batteries, slot['battery'], lock=True)
    need(battery['shift_hours'] == window['shift_hours'], '整班时长已调整，请重新测算')
    # 整班 MAE 作为这块电池的公用余量：同一电池各档共享一份。
    update(conn, batteries, battery['code'], margin_wh=stats['mae'])
    return insert(conn, reserves, code=data.code, airslot=window['code'], meter=battery['meter'],
                  prediction_wh=stats['prediction_wh'], plan_wh=stats['plan_wh'],
                  fallback='本地优先' if slot['offline'] else '受控中继',
                  mae=stats['mae'], token=data.token)
