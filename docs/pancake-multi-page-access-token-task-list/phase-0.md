# Task List Phase 0: Chốt giải pháp nhiều Pancake page access token

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho việc hỗ trợ nhiều Pancake `page_access_token` trên cùng webhook endpoint. Backend phải dùng đúng token theo `page_id` của message đang xử lý và tuyệt đối không fallback sang token mặc định khi thiếu token theo page.

Phase này chỉ chốt giải pháp, ranh giới trách nhiệm và contract cấu hình. Chưa sửa code, chưa thay đổi `.env.example`, chưa gọi Pancake Public API.

## Quyết định cần chốt

- Một webhook endpoint có thể nhận message từ nhiều Pancake page.
- `page_id` là khóa duy nhất để chọn `page_access_token`.
- Token được cấu hình bằng env JSON `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Không dùng nhiều dòng env cùng tên `PANCAKE_PAGE_ACCESS_TOKEN`.
- Không fallback sang `PANCAKE_PAGE_ACCESS_TOKEN` khi thiếu token cho `page_id`.
- Thiếu token theo page là lỗi cấu hình nghiêm trọng.
- Khi thiếu token theo page, backend không gọi Pancake Public API.
- Token không được log, không được trả ra API response, không được commit.
- Flow Facebook hiện tại không bị ảnh hưởng.
- Flow Pancake duplicate/admin pause/text reply/media reply giữ nguyên, chỉ đổi cách lấy token.

## Ngoài phạm vi Phase 0

- Chưa parse JSON env.
- Chưa sửa `pancake_message_service`.
- Chưa sửa `.env.example`.
- Chưa thêm test.
- Chưa thêm UI hoặc database để quản lý token.
- Chưa tự động lấy token từ Pancake.

## File tài liệu liên quan

- [docs/pancake-multi-page-access-token.md](../pancake-multi-page-access-token.md)
- [docs/pancake-multi-page-access-token-task-list/phase-1.md](phase-1.md)
- [docs/pancake-multi-page-access-token-task-list/phase-2.md](phase-2.md)
- [docs/pancake-multi-page-access-token-task-list/phase-3.md](phase-3.md)
- [docs/pancake-multi-page-access-token-task-list/phase-4.md](phase-4.md)
- [docs/pancake-multi-page-access-token-task-list/phase-5.md](phase-5.md)

## Checklist

### 1. Chốt contract multi-page token

- [x] Xác nhận `page_id` là key lookup token.
- [x] Xác nhận mỗi page cần một token riêng trong mapping.
- [x] Xác nhận một backend có thể nhận webhook từ nhiều page.
- [x] Xác nhận mọi Pancake Public API call phải có `page_id`.
- [x] Xác nhận service gửi Pancake tự lookup token theo `page_id`.
- [x] Xác nhận không truyền token từ AI/rule hoặc request body.

Kết quả mong muốn:
  Team thống nhất một contract token theo page, không còn phụ thuộc một token global.

### 2. Chốt rule không fallback

- [x] Xác nhận không fallback sang `PANCAKE_PAGE_ACCESS_TOKEN`.
- [x] Xác nhận không dùng token của page khác nếu thiếu token.
- [x] Xác nhận thiếu token theo page là lỗi `missing_pancake_page_access_token_for_page`.
- [x] Xác nhận lỗi thiếu token là `non_retryable`.
- [x] Xác nhận khi thiếu token thì không gọi HTTP client Pancake.
- [x] Xác nhận lỗi này cần log/alert để vận hành bổ sung env.

Kết quả mong muốn:
  Backend không có đường gửi nhầm page/group vì cấu hình thiếu.

### 3. Chốt format env

- [x] Xác nhận env mới là `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- [x] Xác nhận env là JSON object một dòng.
- [x] Xác nhận key là `page_id` string.
- [x] Xác nhận value là `page_access_token` string.
- [x] Xác nhận JSON không có trailing comma.
- [x] Xác nhận không commit token thật vào repo.

Kết quả mong muốn:
  Cách cấu hình production rõ ràng và không gây nhầm với nhiều dòng env cùng tên.

### 4. Chốt phạm vi ảnh hưởng

- [x] Xác nhận chỉ đổi Pancake message service/token lookup.
- [x] Xác nhận không đổi normalize payload trừ khi thiếu `page_id`.
- [x] Xác nhận không đổi logic AI reply.
- [x] Xác nhận không đổi logic upload/reuse `content_id` ngoài việc dùng token đúng page.
- [x] Xác nhận không đổi database schema.
- [x] Xác nhận không đổi Facebook webhook.

Kết quả mong muốn:
  Scope implementation nhỏ, đúng trọng tâm, dễ review.

## Acceptance criteria

- [x] Team chốt dùng mapping `page_id -> page_access_token`.
- [x] Team chốt không fallback sang token mặc định.
- [x] Team chốt reason lỗi khi thiếu token theo page.
- [x] Team chốt env format JSON một dòng.
- [x] Team chốt danh sách phase implementation/test.

## Ghi chú mở

- Nếu sau này muốn quản lý token trong database hoặc secret manager, vẫn giữ contract lookup theo `page_id`.
- Nếu có page mới, checklist vận hành phải thêm token vào mapping trước khi bật webhook page đó.
