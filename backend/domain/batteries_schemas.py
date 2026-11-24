from typing import Annotated

from pydantic import BaseModel, ConfigDict, FiniteFloat, StringConstraints


class RegisterBattery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    meter: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    shift_hours: int
    capacity_wh: FiniteFloat
