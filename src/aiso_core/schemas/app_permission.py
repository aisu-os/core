from pydantic import BaseModel


class PermissionUpdate(BaseModel):
    granted_permissions: list[str] = []
    denied_permissions: list[str] = []


class PermissionStatus(BaseModel):
    permission: str
    granted: bool


class PermissionStatusResponse(BaseModel):
    app_id: str
    permissions: list[PermissionStatus]
