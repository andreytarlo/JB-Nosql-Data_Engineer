from fastapi import APIRouter, Depends, HTTPException

from ecommerce_pipeline.db import get_db_access
from ecommerce_pipeline.db_access import DBAccess
from ecommerce_pipeline.models.requests import CreateOrderRequest
from ecommerce_pipeline.models.responses import OrderResponse, OrderSnapshotResponse

router = APIRouter()


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(
    body: CreateOrderRequest,
    db: DBAccess = Depends(get_db_access),
) -> OrderResponse:
    """Place an order."""
    try:
        order = db.create_order(
            customer_id=body.customer_id,
            items=body.items,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)})
    return order


@router.get("/{order_id}", response_model=OrderSnapshotResponse)
def get_order(
    order_id: int,
    db: DBAccess = Depends(get_db_access),
) -> OrderSnapshotResponse:
    """Fetch an order by ID."""
    try:
        order = db.get_order(order_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail={"message": str(exc)})
    if order is None:
        raise HTTPException(status_code=404, detail={"message": "order not found"})
    return order
