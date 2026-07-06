# Task List Phase 2: Lookup token theo page trong Pancake message service

## Mục tiêu

Phase 2 sửa `pancake_message_service` để mọi request Pancake Public API dùng `page_access_token` lookup theo `page_id`. Nếu không có token cho page, service trả lỗi cấu hình và không gọi HTTP client.

Kết quả mong muốn:

- `send_pancake_reply` dùng đúng token theo `page_id`.
- `upload_pancake_content` dùng đúng token theo `page_id`.
- `send_pancake_content_ids` dùng đúng token theo `page_id`.
- Thiếu token theo page thì không gọi Pancake API.
- Không fallback sang `PANCAKE_PAGE_ACCESS_TOKEN`.

## Đầu vào đã chốt

- Phase 1 đã có helper parse mapping.
- Các hàm gửi Pancake hiện đã nhận `page_id`.
- Token phải được lấy từ `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID[page_id]`.
- Missing token là lỗi non-retryable.
- Không log token.

## Ngoài phạm vi Phase 2

- Không đổi payload gửi Pancake.
- Không đổi endpoint URL Pancake.
- Không đổi retry/backoff ngoài việc missing token không retry.
- Không đổi webhook normalize.
- Không đổi upload ảnh/content_id cache.

## File chính dự kiến sửa

- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py)

## Checklist

### 1. Thêm helper lookup token theo page

- [x] Thêm helper `_get_pancake_page_access_token_for_page`.
- [x] Helper nhận `page_id`.
- [x] Normalize `page_id` bằng strip.
- [x] Nếu `page_id` rỗng, trả lỗi `missing_page_id`.
- [x] Parse mapping từ Phase 1.
- [x] Nếu mapping có token cho `page_id`, trả token.
- [x] Nếu mapping không có token, trả lỗi `missing_pancake_page_access_token_for_page`.
- [x] Không fallback sang `settings.pancake_page_access_token`.
- [x] Không log token.

Kết quả mong muốn:
  Có một đường lookup token duy nhất cho mọi Pancake API call.

### 2. Sửa text reply

- [x] `send_pancake_reply` gọi helper bằng `page_id`.
- [x] Nếu thiếu token, return lỗi trước khi build HTTP request.
- [x] Nếu có token, truyền token vào params `page_access_token`.
- [x] Giữ validate `page_id`, `conversation_id`, `message`.
- [x] Giữ retry behavior cho lỗi network/API như hiện tại.
- [x] Missing token không retry.

Kết quả mong muốn:
  Text reply từ page nào dùng token của page đó.

### 3. Sửa upload content

- [x] `upload_pancake_content` gọi helper bằng `page_id`.
- [x] Nếu thiếu token, return lỗi trước khi mở file/upload.
- [x] Nếu có token, upload multipart như hiện tại.
- [x] Giữ parse `content_id`.
- [x] Giữ timeout upload hiện tại.
- [x] Không log token trong upload error.

Kết quả mong muốn:
  Upload ảnh lên Pancake đúng page trước khi gửi `content_ids`.

### 4. Sửa gửi `content_ids`

- [x] `send_pancake_content_ids` gọi helper bằng `page_id`.
- [x] Nếu thiếu token, return lỗi trước khi gọi HTTP.
- [x] Nếu có token, gửi body `content_ids` như hiện tại.
- [x] Giữ validate `content_ids` rỗng.
- [x] Giữ retry behavior cho lỗi network/API như hiện tại.
- [x] Missing token không retry.

Kết quả mong muốn:
  Image message dùng token đúng page.

### 5. Test phase 2

- [x] Test text reply dùng token page A.
- [x] Test text reply dùng token page B.
- [x] Test upload content dùng token page A.
- [x] Test send content ids dùng token page B.
- [x] Test thiếu token theo page không gọi HTTP client.
- [x] Test có `PANCAKE_PAGE_ACCESS_TOKEN` cũ nhưng vẫn không fallback.
- [x] Test missing token trả `non_retryable=True`.
- [x] Test response lỗi không chứa token.

Kết quả mong muốn:
  Service Pancake dùng token theo page ở cả text, upload và media send.

## Acceptance criteria

- [x] Mọi Pancake Public API call lookup token theo `page_id`.
- [x] Không còn đường fallback sang token mặc định.
- [x] Missing token không gọi HTTP.
- [x] Missing token trả reason rõ ràng.
- [x] Test phase này pass.

## Ghi chú mở

- Nếu helper cũ `_get_pancake_page_access_token` vẫn còn để test cũ, cần đảm bảo production path mới không dùng fallback.
- Nếu có caller truyền explicit `page_access_token`, nên cân nhắc bỏ hoặc chỉ dùng trong test nội bộ để tránh bypass mapping.
