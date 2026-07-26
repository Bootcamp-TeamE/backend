from pydantic import BaseModel, ConfigDict


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name_ko: str
    default_unit_code: str
    sort_order: int
