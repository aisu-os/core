from pydantic import BaseModel


class InstallRequest(BaseModel):
    granted_permissions: list[str] = []
    denied_permissions: list[str] = []


class InstallResponse(BaseModel):
    app_id: str
    version: str
    granted_permissions: list[str]

    model_config = {"from_attributes": True}
