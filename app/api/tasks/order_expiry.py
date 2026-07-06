from datetime import datetime, timezone

from app.models.posx_order import PosxOrder


async def deactivate_expired_orders():
    now = datetime.now(timezone.utc)

    result = await PosxOrder.find(
        {"active": True, "expired_at": {"$lt": now}}
    ).update_many({"$set": {"active": False, "updated_at": now}})

    if result.modified_count > 0:
        print(f"[Scheduler] Đã vô hiệu hóa {result.modified_count} đơn hàng hết hạn.")
