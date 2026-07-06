# Task List Phase 4: Test, logging và rollout

## Mục tiêu

Phase 4 hoàn thiện test, logging và checklist rollout để endpoint có thể dùng ổn định trên Railway.

Kết quả mong muốn:

- Có test API và service đủ các case chính.
- Log đủ thông tin debug nhưng không log raw image bytes.
- `.env.example` cập nhật.
- Có hướng dẫn rollout production.

## Đầu vào đã chốt

- Endpoint không lưu ảnh.
- Chroma index nằm trên volume `data/chroma`.
- `crop-aware` và `public-crop` không yêu cầu token/key.
- Test suite chạy bằng `pytest -q`.

## Ngoài phạm vi Phase 4

- Không tạo dashboard monitoring.
- Không tạo retry queue.
- Không lưu audit ảnh crop.

## File chính dự kiến sửa

- [tests/test_image_search_api.py](../../tests/test_image_search_api.py)
- [tests/test_order_notes_api.py](../../tests/test_order_notes_api.py)
- [tests/test_public_image_crop_search_service.py](../../tests/test_public_image_crop_search_service.py)
- [.env.example](../../.env.example)
- [docs/public-image-crop-search-api.md](../public-image-crop-search-api.md)

## Tiến độ cập nhật

- Đã bỏ test auth cũ cho `crop-aware` và `public-crop`.
- Đã bổ sung test hai endpoint image search gọi được không auth.
- Đã bổ sung test route `order-notes` không có dấu `/` cuối.
- Đã bổ sung test fetch/crop/search service cho các case chính.
- Đã bổ sung logging trong service, không log raw image bytes.
- Targeted tests đã pass với lệnh `python -m pytest tests/test_image_search_api.py tests/test_order_notes_api.py tests/test_public_image_crop_search_service.py -q`.
- Full suite đã pass với lệnh `python -m pytest -q`.

## Checklist

### 1. Test endpoint

- [x] `public-crop` accept request không auth.
- [x] `crop-aware` accept multipart không auth.
- [x] `order-notes` accept route không có dấu `/` cuối.

### 2. Test fetch/crop

- [x] Test URL scheme sai.
- [x] Test HTTP non-2xx.
- [x] Test content type sai.
- [x] Test ảnh quá lớn.
- [x] Test ảnh rỗng.
- [x] Test ảnh decode lỗi.
- [x] Test crop ngoài biên.
- [x] Test crop vùng quá nhỏ.
- [x] Test crop happy path.

### 3. Test search response

- [x] Ranking rỗng trả `not_found`.
- [x] Score dưới `0.9` trả `not_found`.
- [x] Score bằng `0.9` trả `found`.
- [x] Score trên `0.9` trả `found`.
- [x] Index missing trả `image_search_index_not_found`.
- [x] Exception không biết trả `image_search_failed`.

### 4. Logging và security

- [x] Log request nhận được với `conversation_id`.
- [x] Log fetch/search failed với reason.
- [x] Log found/not_found với confidence.
- [x] Không log raw image bytes.
- [x] Không log URL đầy đủ nếu chưa query nhạy cảm.

### 5. Verification

- [x] Chạy test file liên quan.
- [x] Chạy `pytest -q`.
- [x] Kiểm tra `.env.example`.
- [x] Kiểm tra docs link không sai.
- [x] Ghi chú Railway không cần thêm internal key cho flow này.

## Acceptance criteria

- [x] `pytest -q` pass.
- [x] Endpoint có thể gọi không auth trên local.
- [x] Response đúng 3 case `found`, `not_found`, `error`.
- [x] Không có file ảnh phát sinh trong `data` hoặc `storage` sau request.
- [x] Tài liệu production đủ để cấu hình Railway.

## Ghi chú production

- Không cần thêm `BACKEND_INTERNAL_API_KEY` cho flow này.
- Cần bảo đảm volume `data` vẫn chứa Chroma index.
- Nên test bằng ảnh Pancake CDN thật trước khi Caller BE dùng production.
- Nếu lỗi `image_search_index_not_found`, không phải lỗi endpoint crop mà là Chroma index chưa có dữ liệu hoặc volume chưa mount đúng.
