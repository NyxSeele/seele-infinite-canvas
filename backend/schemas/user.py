from pydantic import BaseModel


class EnabledModelItem(BaseModel):
    id: str
    name: str
    type: str
    enabled: bool = True


class UserModelsResponse(BaseModel):
    models: list[EnabledModelItem]


class UserEnabledModelsResponse(BaseModel):
    user_id: int
    models: list[EnabledModelItem]
