from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


# ── Products ──────────────────────────────────────────────────────────────────

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    stock_quantity: int
    category: str
    description: str
    category_fields: dict  # shape varies by category


class ProductListResponse(BaseModel):
    products: list[ProductResponse]


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float


class OrderResponse(BaseModel):
    order_id: int
    customer_id: int
    status: str
    total_amount: float
    created_at: str
    items: list[OrderItemResponse]


class OrderCustomerEmbed(BaseModel):
    id: int
    name: str
    email: str


class OrderSnapshotResponse(BaseModel):
    order_id: int
    customer: OrderCustomerEmbed
    items: list[OrderItemResponse]
    total_amount: float
    status: str
    created_at: str


class OrderHistoryResponse(BaseModel):
    orders: list[OrderSnapshotResponse]


# ── Recommendations ───────────────────────────────────────────────────────────

class RecommendationResponse(BaseModel):
    product_id: int
    name: str
    score: int  # co-purchase strength; higher means more frequently bought together


class RecommendationListResponse(BaseModel):
    recommendations: list[RecommendationResponse]


# ── Recently Viewed ───────────────────────────────────────────────────────────

class RecentlyViewedResponse(BaseModel):
    product_ids: list[int]


# ── Analytics ─────────────────────────────────────────────────────────────────

class CategoryRevenueResponse(BaseModel):
    category: str
    total_revenue: float


class RevenueByCategoryResponse(BaseModel):
    revenue: list[CategoryRevenueResponse]
