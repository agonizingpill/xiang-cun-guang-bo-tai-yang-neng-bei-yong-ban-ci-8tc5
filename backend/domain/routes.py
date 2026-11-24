from domain.airslots_api import router as airslots
from domain.batteries_api import router as batteries
from domain.battery_logs_api import router as battery_logs
from domain.reserves_api import router as reserves
from domain.switchcards_api import router as switchcards

routers = (airslots, batteries, battery_logs, reserves, switchcards,)
