# Task List Phase 3: Tích hợp Chroma image search và response business

## Mục tiêu

Phase 3 đưa ảnh crop, giữ format nguồn, vào Chroma image search hiện có và map kết quả về response đơn giản cho Caller BE.

Kết quả mong muốn:

- Ảnh crop được tìm bằng logic crop-aware Chroma hiện tại.
- Chỉ lấy sản phẩm đầu tiên.
- Score đủ ngưỡng trả `found`.
- Score thấp hoặc không có ranking trả `not_found`.
- Lỗi search được trả theo reason ổn định.

## Đầu vào đã chốt

- Gọi `search_chroma_crop_aware_image_service`.
- `top_k=10`.
- `aggregate_k=1`.
- Threshold mặc định `0.9`.
- `sku = ranking[0].product_id`.
- `confidence = ranking[0].score`.

## Ngoài phạm vi Phase 3

- Không đổi thuật toán ranking.
- Không đổi Chroma collection.
- Không tự build index.
- Không trả nhiều SKU.

## File chính dự kiến sửa

- [app/services/public_image_crop_search_service.py](../../app/services/public_image_crop_search_service.py)
- [app/api/v1/image_search.py](../../app/api/v1/image_search.py)
- [tests/test_image_search_api.py](../../tests/test_image_search_api.py)
- [tests/test_public_image_crop_search_service.py](../../tests/test_public_image_crop_search_service.py)

## Tiến độ cập nhật

- Đã gọi `search_chroma_crop_aware_image_service` bằng `UploadFile` từ ảnh crop giữ format nguồn.
- Đã dùng `top_k=10`, `aggregate_k=1`.
- Đã map `ranking[0].product_id` thành `sku` và `ranking[0].score` thành `confidence`.
- Đã trả `found` khi score đạt threshold, `not_found` khi ranking rỗng hoặc score thấp.
- Đã map lỗi Chroma index missing và lỗi search khác về response `error`.
- Đã có test ngưỡng score, empty ranking, index missing và search error.

## Checklist

### 1. Gọi search

- [x] Gọi `search_chroma_crop_aware_image_service` bằng `UploadFile` từ ảnh crop giữ format nguồn.
- [x] Truyền filename nội bộ để debug.
- [x] Dùng `top_k=10`.
- [x] Dùng `aggregate_k=1`.
- [x] Test service search được gọi đúng args.

### 2. Map found/not_found

- [x] Nếu ranking rỗng, trả `not_found`.
- [x] Nếu score dưới threshold, trả `not_found`.
- [x] Nếu score bằng threshold, trả `found`.
- [x] Nếu score trên threshold, trả `found`.
- [x] Round confidence nếu cần.
- [x] Test đủ các ngưỡng.

### 3. Map lỗi search

- [x] Map `IMAGE_SEARCH_INDEX_NOT_FOUND` về `image_search_index_not_found`.
- [x] Map lỗi image search known về response error.
- [x] Map exception không biết về `image_search_failed`.
- [x] Không expose stack trace.
- [x] Log reason để debug.

### 4. Endpoint integration

- [x] Endpoint nhận request JSON.
- [x] Endpoint gọi service public crop search.
- [x] Endpoint trả response đúng schema.
- [x] Endpoint không yêu cầu JWT.
- [x] Endpoint không yêu cầu internal key.

## Acceptance criteria

- [x] Caller BE nhận đúng `found` khi confidence đạt ngưỡng.
- [x] Caller BE nhận đúng `not_found` khi confidence thấp.
- [x] Caller BE nhận đúng `error` khi search/index lỗi.
- [x] Automated test cho endpoint pass.

## Ghi chú mở

- Nếu thực tế cần trả thêm debug như `top_sku` khi low confidence, nên thêm sau khi Caller BE có nhu cầu rõ.
- Threshold nên giữ ở config để chỉnh nhanh sau test thực tế.
