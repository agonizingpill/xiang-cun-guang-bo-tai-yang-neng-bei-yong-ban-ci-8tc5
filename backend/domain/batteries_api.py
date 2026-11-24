from fastapi import APIRouter, Depends

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import scan
from domain import batteries_service as service
from domain.batteries_model import batteries
from domain.batteries_schemas import RegisterBattery

router = APIRouter()


@router.get('/batteries')
def list_batteries(user=Depends(actor)):
    with transaction() as conn:
        return scan(conn, batteries)


@router.post('/batteries/register')
def register_battery(data: RegisterBattery, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.register_battery(conn, user, data)
        record(conn, user, 'batteries.register')
        return output
