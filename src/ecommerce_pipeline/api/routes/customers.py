from fastapi import APIRouter, Depends, HTTPException

from ecommerce_pipeline.db import get_db_access
from ecommerce_pipeline.db_access import DBAccess
from ecommerce_pipeline.models.responses import (
    OrderHistoryResponse,
    RecentlyViewedResponse,
    MessageResponse,
)

router = APIRouter()


@router.get("/{customer_id}/orders", response_model=OrderHistoryResponse)
def get_order_history(
    customer_id: int,
    db: DBAccess = Depends(get_db_access),
) -> OrderHistoryResponse:
    """Get all orders for a customer, most recent first."""
    try:
        orders = db.get_order_history(customer_id)
        return OrderHistoryResponse(orders=orders)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})


@router.post("/{customer_id}/viewed/{product_id}", response_model=MessageResponse)
def record_product_view(
    customer_id: int,
    product_id: int,
    db: DBAccess = Depends(get_db_access),
) -> MessageResponse:
    """Record that a customer viewed a product."""
    try:
        db.record_product_view(customer_id, product_id)
        return MessageResponse(message="recorded")
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})


@router.get("/{customer_id}/recently-viewed", response_model=RecentlyViewedResponse)
def get_recently_viewed(
    customer_id: int,
    db: DBAccess = Depends(get_db_access),
) -> RecentlyViewedResponse:
    """Get the most recently viewed product IDs for a customer."""
    try:
        product_ids = db.get_recently_viewed(customer_id)
        return RecentlyViewedResponse(product_ids=product_ids)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})
