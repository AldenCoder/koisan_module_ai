from fastapi import APIRouter

from app.api.v1 import (
    conversations,
    dashboard_reports,
    dataset_cleaning,
    facebook_webhook,
    image_search_import,
    image_search,
    intent_analysis,
    nguoi_dung,
    nguoi_dung_tac_nhan,
    order_notes,
    pancake_webhook,
    products,
    quyen_han,
    response_message,
    tac_nhan,
    tac_nhan_quyen_han,
    workflow_message,
)

api_router = APIRouter()

api_router.include_router(
    conversations.router, prefix="/conversations", tags=["Conversations"]
)
api_router.include_router(
    dashboard_reports.router, prefix="/dashboard", tags=["Dashboard"]
)
api_router.include_router(
    image_search.router, prefix="/image-search", tags=["Image Search"]
)
api_router.include_router(
    image_search_import.router,
    prefix="/image-search-import",
    tags=["Image Search Import"],
)
api_router.include_router(
    products.router, prefix="/products", tags=["Products"]
)
api_router.include_router(
    order_notes.router, prefix="/order-notes", tags=["Order Notes"]
)
api_router.include_router(
    intent_analysis.router, prefix="/intent", tags=["Intent Analysis"]
)
api_router.include_router(
    response_message.router, prefix="/message", tags=["Message Processing"]
)
api_router.include_router(
    workflow_message.router, prefix="/workflow", tags=["Workflow Processing"]
)
api_router.include_router(
    facebook_webhook.router, prefix="/facebook", tags=["Facebook Webhook"]
)
api_router.include_router(
    pancake_webhook.router, prefix="/pancake", tags=["Pancake Webhook"]
)
api_router.include_router(
    dataset_cleaning.router, prefix="/dataset", tags=["Dataset Cleaning"]
)
api_router.include_router(
    nguoi_dung.router, prefix="/nguoi-dung", tags=["Nguoi Dung"]
)
api_router.include_router(
    nguoi_dung_tac_nhan.router,
    prefix="/nguoi-dung-tac-nhan",
    tags=["Nguoi Dung Tac Nhan"],
)
api_router.include_router(
    quyen_han.router, prefix="/quyen-han", tags=["Quyen Han"]
)
api_router.include_router(
    tac_nhan.router, prefix="/tac-nhan", tags=["Tac Nhan"]
)
api_router.include_router(
    tac_nhan_quyen_han.router,
    prefix="/tac-nhan-quyen-han",
    tags=["Tac Nhan Quyen Han"],
)
