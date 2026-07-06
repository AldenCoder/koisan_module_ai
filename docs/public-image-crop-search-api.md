# API cắt ảnh từ public URL và tìm mã sản phẩm

## Mục tiêu

Tài liệu này mô tả phương án để `BE` nhận một link ảnh public kèm tọa độ crop dạng tỷ lệ `0 -> 1`, cắt vùng ảnh cần tìm, đưa ảnh đã cắt vào luồng image search hiện có, rồi trả về mã sản phẩm nếu độ tin cậy đạt ngưỡng.

Flow này triển khai theo thứ tự:

- Phần 1: bổ sung contract endpoint, schema và route không auth theo yêu cầu mới.
- Phần 2: tải ảnh public, validate ảnh và crop theo tọa độ tỷ lệ.
- Phần 3: đưa ảnh crop vào image search hiện có và map kết quả về response business.
- Phần 4: bổ sung test, logging và checklist rollout.

Lưu ý thiết kế mới: `POST /api/v1/image-search/crop-aware` và `POST /api/v1/image-search/public-crop` đều không yêu cầu JWT token, cũng không yêu cầu `BACKEND_INTERNAL_API_KEY`. Cách này giống hướng route `POST /api/v1/order-notes`, để Caller BE gọi trực tiếp. Do endpoint `public-crop` nhận URL public, lớp bảo vệ quan trọng nhất là validate URL, giới hạn timeout/bytes/content type và crop bounds.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Caller BE`: backend khác gọi sang endpoint này.
- `public image URL`: URL HTTP/HTTPS có thể tải ảnh trực tiếp.
- `crop`: vùng ảnh cần cắt, dùng tọa độ tỷ lệ `0 -> 1`.
- `image_search.py`: router image search hiện tại tại [app/api/v1/image_search.py](../app/api/v1/image_search.py).
- `Chroma image search`: luồng tìm ảnh đang dùng ChromaDB qua [app/services/chroma_crop_aware_index.py](../app/services/chroma_crop_aware_index.py).
- `sku`: mã sản phẩm trả về cho Caller BE, lấy từ `ranking[0].product_id`.
- `confidence`: điểm tin cậy trả về cho Caller BE, lấy từ `ranking[0].score`.

## Luồng tổng thể

Caller BE gửi `conversation_id`, `image_url` và `crop` tới `POST /api/v1/image-search/public-crop`.

`BE` validate payload, tải ảnh từ `image_url`, kiểm tra content type/kích thước, decode ảnh, chuẩn hóa EXIF orientation và crop ảnh theo tọa độ tỷ lệ.

Ảnh crop được đưa vào luồng image search hiện có. Trong cùng process, implementation gọi service bytes mà `image_search.py` đang dùng thay vì tự gọi HTTP ngược về chính backend.

Image search trả ranking sản phẩm. `BE` lấy sản phẩm đầu tiên:

- Nếu `ranking[0].score >= 0.9`, trả `found` với `sku` và `confidence`.
- Nếu không có ranking hoặc điểm thấp hơn `0.9`, trả `not_found`.
- Nếu lỗi fetch/crop/search, trả response lỗi chuẩn để Caller BE dễ parse.

Không cần thêm database. Không lưu ảnh gốc hoặc ảnh crop dài hạn. Ảnh được xử lý trong memory.

## Hiện trạng hệ thống

Image search hiện tại nằm ở:

- [app/api/v1/image_search.py](../app/api/v1/image_search.py)
- [app/api/schemas/image_search.py](../app/api/schemas/image_search.py)
- [app/services/chroma_crop_aware_index.py](../app/services/chroma_crop_aware_index.py)
- [app/services/foreground_common.py](../app/services/foreground_common.py)

Đã có sẵn:

- Endpoint `POST /api/v1/image-search/crop-aware`.
- Endpoint `crop-aware` nhận `multipart/form-data` field `file`.
- Service `search_chroma_crop_aware_image_service` nhận `UploadFile`.
- ChromaDB index dùng config `CHROMA_PERSIST_DIR` và `CHROMA_IMAGE_SEARCH_COLLECTION`.
- Response search hiện có trả `ranking` và `top_images`.

Đã bổ sung trong task này:

- Endpoint `POST /api/v1/image-search/public-crop` nhận `image_url + crop`.
- `crop-aware` và `public-crop` không còn auth token/key.
- Service tải ảnh public có giới hạn timeout/bytes/content type.
- Logic crop theo tọa độ tỷ lệ.
- Response business `found/not_found/error` theo contract Caller BE cần.
- Route `POST /api/v1/order-notes` được khai báo không có dấu `/` cuối.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Cung cấp endpoint cho Caller BE.
- Validate payload và tọa độ crop.
- Tải ảnh public theo timeout và giới hạn dung lượng.
- Reject URL không hợp lệ hoặc ảnh không decode được.
- Crop ảnh theo tọa độ tỷ lệ `0 -> 1`.
- Đưa ảnh crop vào Chroma image search hiện có.
- Lấy kết quả đầu tiên và so sánh với threshold `0.9`.
- Trả response business thống nhất cho Caller BE.
- Log đủ thông tin debug nhưng không log raw image bytes.

### Caller BE

Caller BE chịu trách nhiệm:

- Gọi đúng endpoint không auth theo contract hiện tại.
- Gửi `image_url` public có thể tải được.
- Gửi tọa độ crop đúng quy ước.
- Xử lý `found`, `not_found` và `error` theo response contract.
- Không gửi URL private hoặc URL yêu cầu cookie/session.

### Image search hiện có

Luồng image search hiện có chịu trách nhiệm:

- Nhận bytes ảnh query.
- Extract foreground/crop-aware views.
- Query ChromaDB.
- Aggregate kết quả theo sản phẩm.
- Trả ranking sản phẩm đã sắp xếp theo score giảm dần.

Endpoint mới không thay đổi thuật toán ranking, Chroma collection hoặc logic import ảnh nguồn.

## Phần 1. Contract endpoint

Endpoint mới:

- `POST /api/v1/image-search/public-crop`

Router:

- [app/api/v1/image_search.py](../app/api/v1/image_search.py)

Content type:

- `application/json`

Authentication:

- Không yêu cầu `Authorization` token.
- Không yêu cầu `X-Backend-Internal-Api-Key`.

### Payload request

```json
{
  "conversation_id": "6a293e2adc67c855f764f359",
  "image_url": "https://content.pancake.vn/2-2606/2026/6/15/1df99145a3abfc7209acf3177d1cd7b198fdb6ab.jpg",
  "crop": {
    "x1": 0.28,
    "y1": 0.12,
    "x2": 0.76,
    "y2": 0.92
  }
}
```

Quy ước tọa độ:

- `x1`, `y1`: góc trái trên vùng cần cắt.
- `x2`, `y2`: góc phải dưới vùng cần cắt.
- Tọa độ dạng `0 -> 1`, không phải pixel.
- Gốc tọa độ là góc trái trên ảnh gốc.

### Response contract

Found:

```json
{
  "success": true,
  "status": "found",
  "sku": "S2651729",
  "confidence": 0.94
}
```

Not found hoặc confidence dưới 90%:

```json
{
  "success": true,
  "status": "not_found",
  "reason": "low_confidence"
}
```

Lỗi fetch/crop:

```json
{
  "success": false,
  "status": "error",
  "reason": "invalid_image_url"
}
```

Reason đang dùng:

| Reason | Khi nào dùng |
|---|---|
| `invalid_image_url` | URL sai, fetch lỗi, HTTP non-2xx, content type không phải ảnh, ảnh rỗng hoặc decode lỗi |
| `invalid_crop` | Tọa độ crop sai rule hoặc vùng crop quá nhỏ |
| `image_search_index_not_found` | Chroma collection chưa có dữ liệu |
| `image_search_failed` | Search lỗi ngoài các case đã biết |

## Phần 2. Fetch public image và crop

Rule validate URL:

- Chỉ nhận scheme `http` hoặc `https`.
- URL phải có hostname.
- Không nhận URL rỗng hoặc quá dài.
- Không nhận URL có scheme khác như `file`, `ftp`, `data`.
- Reject hostname/IP private hoặc loopback nếu không có nhu cầu nội bộ.

Service fetch dùng `httpx.AsyncClient` với:

- `follow_redirects=True`
- timeout từ config `PUBLIC_IMAGE_CROP_SEARCH_TIMEOUT_SECONDS`
- max bytes từ config `PUBLIC_IMAGE_CROP_SEARCH_MAX_BYTES`

Rule crop:

- `0 <= x1 < x2 <= 1`.
- `0 <= y1 < y2 <= 1`.
- Không tự clamp tọa độ ngoài biên.
- Vùng crop sau khi đổi sang pixel phải có width/height tối thiểu.
- Ảnh được crop trực tiếp từ ảnh gốc trong memory, giữ format nguồn khi chuyển sang search, không ghi disk.

## Phần 3. Đưa ảnh crop vào image search và map kết quả

Endpoint `public-crop` tạo `UploadFile` từ ảnh crop giữ format nguồn và gọi:

- `search_chroma_crop_aware_image_service(...)`

Thông số:

- `top_k=10`
- `aggregate_k=1`

Rule mapping:

- Nếu `ranking` rỗng: trả `not_found`, reason `low_confidence`.
- Nếu `ranking[0].score < threshold`: trả `not_found`, reason `low_confidence`.
- Nếu `ranking[0].score >= threshold`: trả `found`.

Threshold:

- Config `PUBLIC_IMAGE_CROP_SEARCH_MIN_CONFIDENCE`
- Mặc định `0.9`

## Phần 4. Test, logging và rollout

Log đang dùng:

- `PUBLIC_IMAGE_CROP_SEARCH_REQUEST_RECEIVED`
- `PUBLIC_IMAGE_CROP_SEARCH_PREP_FAILED`
- `PUBLIC_IMAGE_CROP_SEARCH_SEARCH_START`
- `PUBLIC_IMAGE_CROP_SEARCH_SEARCH_FAILED`
- `PUBLIC_IMAGE_CROP_SEARCH_FOUND`
- `PUBLIC_IMAGE_CROP_SEARCH_NOT_FOUND`

Không log:

- URL đầy đủ nếu chưa query nhạy cảm.
- Raw image bytes.

Config cần có:

```env
PUBLIC_IMAGE_CROP_SEARCH_TIMEOUT_SECONDS=15
PUBLIC_IMAGE_CROP_SEARCH_MAX_BYTES=10485760
PUBLIC_IMAGE_CROP_SEARCH_MIN_CONFIDENCE=0.9
```

## Danh sách file thay đổi khi implement

- [app/core/config.py](../app/core/config.py)
- [.env.example](../.env.example)
- [app/api/v1/image_search.py](../app/api/v1/image_search.py)
- [app/api/v1/order_notes.py](../app/api/v1/order_notes.py)
- [app/api/schemas/image_search.py](../app/api/schemas/image_search.py)
- [app/services/public_image_crop_search_service.py](../app/services/public_image_crop_search_service.py)
- [tests/test_image_search_api.py](../tests/test_image_search_api.py)
- [tests/test_order_notes_api.py](../tests/test_order_notes_api.py)
- [tests/test_public_image_crop_search_service.py](../tests/test_public_image_crop_search_service.py)

## Checklist implementation tổng hợp

Trạng thái hiện tại: Phase 1-4 đã được implement ở mức code và automated test. Backend đã có endpoint `POST /api/v1/image-search/public-crop`, service fetch/crop ảnh public trong memory, gọi Chroma image search bằng ảnh crop giữ format nguồn và map response `found/not_found/error`. Endpoint `crop-aware` và `public-crop` hiện không yêu cầu JWT token hoặc internal API key. Targeted tests và full suite `pytest -q` đã pass.

### Phase 1. Contract API

- [x] Thêm config timeout/max bytes/min confidence cho public crop search.
- [x] Thêm schema request `PublicImageCropSearchRequest`.
- [x] Thêm schema crop coordinates.
- [x] Thêm schema response `PublicImageCropSearchResponse`.
- [x] Thêm endpoint `POST /api/v1/image-search/public-crop`.
- [x] Bỏ auth token/key khỏi `crop-aware`.
- [x] Bỏ auth token/key khỏi `public-crop`.
- [x] Đổi route `order-notes` thành path không có dấu `/` cuối.
- [x] Update `.env.example`.

### Phase 2. Fetch ảnh public và crop

- [x] Validate `image_url` chỉ nhận HTTP/HTTPS.
- [x] Reject URL thiếu hostname.
- [x] Reject URL private/loopback nếu không có nhu cầu nội bộ.
- [x] Fetch ảnh bằng `httpx.AsyncClient` với timeout.
- [x] Giới hạn bytes tải về.
- [x] Validate content type ảnh.
- [x] Decode ảnh bằng Pillow.
- [x] Chuẩn hóa EXIF orientation.
- [x] Crop trực tiếp từ ảnh gốc trước khi đưa vào `crop-aware`.
- [x] Validate crop `0 <= x1 < x2 <= 1` và `0 <= y1 < y2 <= 1`.
- [x] Đổi tọa độ tỷ lệ sang pixel đúng rule.
- [x] Reject vùng crop quá nhỏ.
- [x] Giữ format nguồn của ảnh crop trong memory.
- [x] Không lưu ảnh crop vào disk.

### Phase 3. Tích hợp Chroma image search và response business

- [x] Gọi `search_chroma_crop_aware_image_service` với `UploadFile` từ ảnh crop giữ format nguồn.
- [x] Dùng `top_k=10`, `aggregate_k=1`.
- [x] Lấy `ranking[0].product_id` làm `sku`.
- [x] Lấy `ranking[0].score` làm `confidence`.
- [x] Trả `found` khi `confidence >= 0.9`.
- [x] Trả `not_found` khi không có ranking.
- [x] Trả `not_found` khi `confidence < 0.9`.
- [x] Map lỗi index chưa build thành `image_search_index_not_found`.
- [x] Map lỗi fetch/crop thành `invalid_image_url` hoặc `invalid_crop`.
- [x] Không expose exception detail ra response.

### Phase 4. Test, logging và rollout

- [x] Test `crop-aware` gọi được không auth.
- [x] Test `public-crop` gọi được không auth.
- [x] Test `order-notes` route không có dấu `/` cuối.
- [x] Test validate crop ngoài biên.
- [x] Test validate `x1 >= x2` và `y1 >= y2`.
- [x] Test fetch HTTP non-2xx trả `invalid_image_url`.
- [x] Test content type không phải ảnh trả `invalid_image_url`.
- [x] Test ảnh decode lỗi trả `invalid_image_url`.
- [x] Test crop thành công và gọi image search bằng bytes crop.
- [x] Test score `0.9` trả `found`.
- [x] Test score lớn hơn `0.9` trả `found`.
- [x] Test score dưới `0.9` trả `not_found`.
- [x] Test ranking rỗng trả `not_found`.
- [x] Test Chroma index missing trả `image_search_index_not_found`.
- [x] Bỏ logging/key guidance cũ vì endpoint không còn key.
- [x] Chạy `pytest -q`.

Task list chi tiết từng phase:

- [Phase 1. Contract API](public-image-crop-search-api-task-list/phase-1.md)
- [Phase 2. Fetch ảnh public và crop](public-image-crop-search-api-task-list/phase-2.md)
- [Phase 3. Tích hợp Chroma image search và response business](public-image-crop-search-api-task-list/phase-3.md)
- [Phase 4. Test, logging và rollout](public-image-crop-search-api-task-list/phase-4.md)

## Test cần có khi implement

- Endpoint `public-crop` gọi được không auth.
- Endpoint `crop-aware` gọi được không auth.
- Endpoint `order-notes` gọi bằng `/api/v1/order-notes`, không cần slash cuối.
- Schema reject payload thiếu `conversation_id`.
- Schema reject payload thiếu `image_url`.
- Schema reject payload thiếu `crop`.
- Schema reject crop không phải số.
- Schema reject crop ngoài khoảng `0 -> 1`.
- Service reject URL scheme không hợp lệ.
- Service reject URL private/loopback nếu rule này được bật.
- Service reject HTTP non-2xx.
- Service reject content type không phải ảnh.
- Service reject ảnh quá lớn.
- Service reject ảnh rỗng.
- Service reject ảnh decode lỗi.
- Service crop đúng pixel với ảnh mẫu kích thước cố định.
- Service xử lý PNG/WebP có alpha.
- Endpoint trả `found` đúng contract.
- Endpoint trả `not_found` đúng contract.
- Endpoint trả `error` đúng contract.

## Ghi chú production

- Không cần cấu hình `BACKEND_INTERNAL_API_KEY` cho flow này.
- Nếu service chạy nhiều instance, không có vấn đề vì endpoint không lưu state.
- Chroma index vẫn phải tồn tại trong `data/chroma` trên volume hiện tại.
- Endpoint này không thay thế API import ảnh nguồn.
- Nếu Caller BE gửi ảnh Pancake CDN, nên theo dõi lỗi fetch trong vài ngày đầu để biết có cần allowlist domain hoặc xử lý redirect đặc biệt không.
- Nếu tỷ lệ `low_confidence` cao, cần kiểm tra lại crop coordinates từ Caller BE trước khi chỉnh threshold.
- Threshold `0.9` nên để config để dễ điều chỉnh sau khi test thực tế.
