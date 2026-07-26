from pydantic import BaseModel, ConfigDict

from app.models.unit import UnitType


class UnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name_ko: str
    unit_type: UnitType
    sort_order: int
