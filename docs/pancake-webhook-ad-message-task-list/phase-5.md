# Task List Phase 5: Logging, test và rollout

## Mục tiêu

Phase 5 hoàn thiện logging, test coverage và rollout checklist cho flow Pancake auto consult từ ad card và page comment reply notice.

Kết quả mong muốn:

- Unit test cover actor classification, source hydrate, product code extraction, prompt, idempotency, AI call và send reply.
- Log đủ để debug fail ở trigger, Pancake API, parse description, parse mã, AI hoặc send.
- Rollout có feature flag và checklist quan sát production.

## Đầu vào đã chốt

- Phase 1-4 đã implement.
- Test không gọi Pancake, AI hoặc Google Drive thật.
- Feature flag mặc định an toàn cho production lần đầu.

## Ngoài phạm vi Phase 5

- Không load test production.
- Không tạo dashboard monitoring mới.
- Không migrate dữ liệu conversation cũ bắt buộc.

## File chính dự kiến sửa

- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)
- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py)
- `tests/test_pancake_auto_consult_service.py`, nếu tách helper riêng.
- [app/core/config.py](../../app/core/config.py), nếu thêm feature flag.

## Checklist

### 1. Logging

- [x] Log `PANCAKE_AUTO_CONSULT_TRIGGER_DETECTED`.
- [x] Log `PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_START`.
- [x] Log `PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_OK`.
- [x] Log `PANCAKE_AUTO_CONSULT_CONTEXT_FETCH_FAILED`.
- [x] Log `PANCAKE_AUTO_CONSULT_PRODUCT_CODE_EXTRACTED`.
- [x] Log `PANCAKE_AUTO_CONSULT_DUPLICATE_SKIPPED`.
- [x] Log `PANCAKE_AUTO_CONSULT_AI_START`.
- [x] Log `PANCAKE_AUTO_CONSULT_AI_OK`.
- [x] Log `PANCAKE_AUTO_CONSULT_AI_FAILED`.
- [x] Log `PANCAKE_AUTO_CONSULT_SEND_OK`.
- [x] Log `PANCAKE_AUTO_CONSULT_SEND_FAILED`.
- [x] Log `PANCAKE_AUTO_CONSULT_SUPPRESSED_BY_ADMIN_PAUSE`.
- [x] Include `page_id`, `pancake_conversation_id`, `customer_id`, `trigger_type`, `trigger_message_mid`, `product_codes`, `reason`.
- [x] Không log `page_access_token`.
- [x] Không log raw full description nếu dài.

Kết quả mong muốn:
  Có thể đọc log và biết flow fail ở bước nào.

### 2. Unit test actor và parser

- [x] Test `_is_pancake_ad_card_message` true với `message_mid=ad-...`.
- [x] Test `_is_pancake_page_comment_reply_notice` true với đủ tổ hợp dấu hiệu.
- [x] Test comment notice false nếu thiếu `comment_id`.
- [x] Test comment notice false nếu sender không phải page.
- [x] Test comment notice false nếu có `admin_name` hoặc `uid`.
- [x] Test comment notice false nếu có attachment template.
- [x] Test `POS`/`Botcake` không classify thành human admin.
- [x] Test Public API vẫn là page echo/automation.

### 3. Unit test hydrate source

- [x] Test GET conversation messages dùng đúng token theo page.
- [x] Test thiếu token return `missing_pancake_page_access_token_for_page`.
- [x] Test ad card happy path extract description/ad_id/post_id.
- [x] Test ad card thiếu ad message.
- [x] Test ad card thiếu ad_click.
- [x] Test comment notice happy path extract `comment_id` và description.
- [x] Test comment notice thiếu context.
- [x] Test comment notice thiếu description.

### 4. Unit test product codes và prompt

- [x] Test parse một mã `S7671263`.
- [x] Test parse nhiều mã `S7671263`, `S7672889`.
- [x] Test dedupe mã trùng.
- [x] Test không parse chuỗi toàn số.
- [x] Test không có mã return `pancake_product_code_missing`.
- [x] Test prompt một mã `tư vấn mẫu S7671263 và gửi ảnh lookbook`.
- [x] Test prompt nhiều mã `tư vấn mẫu S7671263, S7672889 và gửi ảnh lookbook`.

### 5. Unit test end-to-end webhook branch

- [x] Test ad card happy path gọi AI với `user=customer_id`.
- [x] Test page comment reply notice happy path gọi AI với `user=customer_id`.
- [x] Test raw page `sender_id` không được dùng làm AI user.
- [x] Test duplicate trigger không gọi AI lần hai.
- [x] Test paused conversation không gọi AI/send.
- [x] Test AI success gửi `send_pancake_reply` đúng `page_id`, `pancake_conversation_id`, `action=reply_inbox`.
- [x] Test bot message lưu `meta.source=pancake_auto_consult`.
- [x] Test không lưu token vào `Message.meta`.

### 6. Rollout

- [x] Thêm `PANCAKE_AUTO_CONSULT_ENABLED`.
- [x] Thêm `PANCAKE_AUTO_CONSULT_PRODUCT_CODE_REGEX` nếu cần override.
- [x] Mặc định feature flag an toàn cho production lần đầu.
- [x] Chạy `pytest -q`.
- [ ] Kiểm tra log trên một page test trước khi bật rộng.
- [ ] Theo dõi duplicate/skipped/error reason sau deploy.
- [ ] Theo dõi tỉ lệ `pancake_product_code_missing`.
- [ ] Theo dõi tỉ lệ `pancake_comment_post_context_missing`.

## Acceptance criteria

- [x] Toàn bộ test mới pass.
- [x] Regression test hiện tại pass.
- [x] Không có external service dependency trong test.
- [x] Có feature flag để tắt nhanh.
- [x] Log không chứa token.
- [x] Rollout checklist đủ rõ.

## Ghi chú mở

- Sau khi deploy, nên review log production vài ngày để quyết định có cần mở rộng regex mã sản phẩm hoặc fallback description cho comment context không.
