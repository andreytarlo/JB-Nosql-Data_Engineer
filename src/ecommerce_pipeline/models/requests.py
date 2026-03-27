from pydantic import BaseModel, field_validator


class OrderItemRequest(BaseModel):
    product_id: int
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v


class CreateOrderRequest(BaseModel):
    customer_id: int
    items: list[OrderItemRequest]

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v: list[OrderItemRequest]) -> list[OrderItemRequest]:
        if not v:
            raise ValueError("items must not be empty")
        return v
