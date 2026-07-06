# Task List Phase 1: Contract API

## Mục tiêu

Phase 1 chốt contract API và route cho flow cắt ảnh public URL. Theo quyết định mới, endpoint image search trong phase này không yêu cầu JWT token và không yêu cầu `BACKEND_INTERNAL_API_KEY`.

Kết quả mong muốn:

- Có schema request/response cho endpoint `public-crop`.
- Endpoint `crop-aware` không yêu cầu token auth.
- Endpoint `public-crop` không yêu cầu token auth hoặc internal key.
- Route `order-notes` dùng path không có dấu `/` cuối.

## Đầu vào đã chốt

- Endpoint mới: `POST /api/v1/image-search/public-crop`.
- Endpoint upload hiện có: `POST /api/v1/image-search/crop-aware`.
- Không có header auth bắt buộc.
- Response business gồm `found`, `not_found`, `error`.
- Confidence threshold mặc định `0.9`.

## Ngoài phạm vi Phase 1

- Chưa fetch ảnh public.
- Chưa crop ảnh.
- Chưa gọi Chroma image search.
- Chưa tối ưu logging production.

## File chính dự kiến sửa

- [app/core/config.py](../../app/core/config.py)
- [.env.example](../../.env.example)
- [app/api/v1/image_search.py](../../app/api/v1/image_search.py)
- [app/api/v1/order_notes.py](../../app/api/v1/order_notes.py)
- [app/api/schemas/image_search.py](../../app/api/schemas/image_search.py)
- [tests/test_image_search_api.py](../../tests/test_image_search_api.py)
- [tests/test_order_notes_api.py](../../tests/test_order_notes_api.py)

## Tiến độ cập nhật

- Đã thêm config public crop search trong [app/core/config.py](../../app/core/config.py).
- Đã cập nhật `.env.example` cho các biến timeout/max bytes/min confidence.
- Đã thêm schema request/response trong [app/api/schemas/image_search.py](../../app/api/schemas/image_search.py).
- Đã bỏ auth token/key khỏi `crop-aware`.
- Đã thêm endpoint `POST /api/v1/image-search/public-crop` không auth.
- Đã đổi `POST /api/v1/order-notes` sang route không có dấu `/` cuối.
- Đã cập nhật test API trong [tests/test_image_search_api.py](../../tests/test_image_search_api.py) và [tests/test_order_notes_api.py](../../tests/test_order_notes_api.py).

## Checklist

### 1. Config

- [x] Thêm `public_image_crop_search_timeout_seconds`.
- [x] Thêm `public_image_crop_search_max_bytes`.
- [x] Thêm `public_image_crop_search_min_confidence`.
- [x] Update `.env.example`.
- [x] Không thêm biến key auth nội bộ cho flow này.

### 2. Schema

- [x] Tạo schema crop có `x1`, `y1`, `x2`, `y2`.
- [x] Tạo schema request có `conversation_id`, `image_url`, `crop`.
- [x] Tạo schema response cho `found`.
- [x] Tạo schema response cho `not_found`.
- [x] Tạo schema response cho `error`.
- [x] Validate field bắt buộc.
- [x] Validate tọa độ là số.

### 3. Auth

- [x] `crop-aware` không yêu cầu JWT token.
- [x] `crop-aware` không yêu cầu `BACKEND_INTERNAL_API_KEY`.
- [x] `public-crop` không yêu cầu JWT token.
- [x] `public-crop` không yêu cầu `BACKEND_INTERNAL_API_KEY`.
- [x] Xóa dependency internal auth không còn dùng.

### 4. Route liên quan

- [x] `POST /api/v1/order-notes` là route canonical.
- [x] Không khai báo route chính với dấu `/` cuối.

## Acceptance criteria

- [x] `POST /api/v1/image-search/public-crop` xuất hiện trong router.
- [x] Endpoint `public-crop` gọi được không auth.
- [x] Endpoint `crop-aware` gọi được không auth.
- [x] `.env.example` có đủ config public crop search và không có `BACKEND_INTERNAL_API_KEY` cho flow này.
- [x] Test API pass.

## Ghi chú mở

- Nếu sau này cần bảo vệ endpoint public bằng secret/network layer, nên thiết kế lại riêng. Bản hiện tại đi theo yêu cầu không auth để Caller BE gọi đơn giản.
- Không dùng query param để truyền key.
