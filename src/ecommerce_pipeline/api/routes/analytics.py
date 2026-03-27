from fastapi import APIRouter, Depends, HTTPException

from ecommerce_pipeline.db import get_db_access
from ecommerce_pipeline.db_access import DBAccess
from ecommerce_pipeline.models.responses import RevenueByCategoryResponse

router = APIRouter()


@router.get("/revenue-by-category", response_model=RevenueByCategoryResponse)
def revenue_by_category(
    db: DBAccess = Depends(get_db_access),
) -> RevenueByCategoryResponse:
    """Get total revenue per product category, sorted highest first."""
    try:
        revenue = db.revenue_by_category()
        return RevenueByCategoryResponse(revenue=revenue)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})
