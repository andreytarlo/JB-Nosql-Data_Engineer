from fastapi import APIRouter, Depends, HTTPException, Query

from ecommerce_pipeline.db import get_db_access
from ecommerce_pipeline.db_access import DBAccess
from ecommerce_pipeline.models.responses import (
    ProductResponse,
    ProductListResponse,
    RecommendationListResponse,
)

router = APIRouter()


@router.get("", response_model=ProductListResponse)
def search_products(
    category: str | None = Query(default=None, description="Filter by category"),
    q: str | None = Query(default=None, description="Case-insensitive name search"),
    db: DBAccess = Depends(get_db_access),
) -> ProductListResponse:
    """Search products by category and/or name."""
    try:
        products = db.search_products(category=category, q=q)
        return ProductListResponse(products=products)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})


@router.get("/{product_id}/recommendations", response_model=RecommendationListResponse)
def get_recommendations(
    product_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    db: DBAccess = Depends(get_db_access),
) -> RecommendationListResponse:
    """Get product recommendations based on co-purchase patterns."""
    try:
        recs = db.get_recommendations(product_id, limit=limit)
        return RecommendationListResponse(recommendations=recs)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    db: DBAccess = Depends(get_db_access),
) -> ProductResponse:
    """Fetch a product by ID."""
    try:
        product = db.get_product(product_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})
    if product is None:
        raise HTTPException(status_code=404, detail={"message": "product not found"})
    return product
