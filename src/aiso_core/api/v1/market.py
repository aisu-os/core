from fastapi import APIRouter, Depends, HTTPException, status

from aiso_core.schemas.app import AppDetailResponse, AppListResponse
from aiso_core.schemas.app_review import ReviewResponse
from aiso_core.utils.pagination import PaginationParams

router = APIRouter()


@router.get("/apps", response_model=AppListResponse)
async def get_apps(pagination: PaginationParams = Depends()):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.get("/apps/{app_id}", response_model=AppDetailResponse)
async def get_app(app_id: str):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.get("/apps/{app_id}/reviews", response_model=list[ReviewResponse])
async def get_app_reviews(app_id: str, pagination: PaginationParams = Depends()):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.get("/categories")
async def get_categories():
    return [
        "utilities",
        "productivity",
        "developer",
        "education",
        "entertainment",
        "social",
        "customization",
        "ai-tools",
    ]


@router.get("/featured", response_model=AppListResponse)
async def get_featured():
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")


@router.get("/search", response_model=AppListResponse)
async def search_apps(q: str, pagination: PaginationParams = Depends()):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="Hali implementatsiya qilinmagan")
