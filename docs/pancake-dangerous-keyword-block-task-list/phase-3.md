# Task List Phase 3: Logging và bảo mật dữ liệu dangerous keyword block

## Mục tiêu

Phase 3 đảm bảo path dangerous keyword block không làm lộ full text khách hàng, raw payload, token, secret hoặc AI payload trong log/response. Khi bị block, hệ thống chỉ log metadata tối thiểu đủ để trace và vận hành.

Kết quả mong muốn:

- Log block có đủ metadata vận hành.
- Không log full text khách hàng khi match keyword.
- Không log raw payload chứa message bị block.
- Không log token/secret.
- Response webhook khi block không chứa text bị chặn.
- Raw payload logging hiện tại được xử lý an toàn trước rollout.

## Đầu vào đã chốt

- Block result có `matched_keyword` nhưng không có full text.
- Webhook normalized data có `page_id`, `sender_id`, `message_mid`, `pancake_conversation_id`.
- Khi match keyword, flow dừng trước AI và Pancake reply.
- Production có rủi ro nếu raw webhook logging vẫn in payload đầy đủ.

## Ngoài phạm vi Phase 3

- Không thêm audit database.
- Không lưu full blocked text ở nơi khác.
- Không thêm dashboard/metrics.
- Không thay đổi nội dung keyword.
- Không thêm masking framework toàn cục ngoài Pancake webhook nếu chưa cần.

## File chính dự kiến sửa

- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/services/dangerous_keyword_service.py](../../app/services/dangerous_keyword_service.py), nếu cần reason/result bổ sung
- `tests/test_pancake_webhook_dangerous_keyword_block.py`
- Logging helper hiện có nếu cần redaction

## Checklist

### 1. Log event bị chặn

- [x] Log event `PANCAKE_DANGEROUS_KEYWORD_BLOCKED`.
- [x] Log có `page_id`.
- [x] Log có `sender_id`.
- [x] Log có `message_mid`.
- [x] Log có `pancake_conversation_id`.
- [x] Log có `matched_keyword`.
- [x] Log có reason `pancake_dangerous_keyword_blocked`.
- [x] Không log full text khách hàng.

Kết quả mong muốn:
  Có thể trace message bị block mà không lưu nội dung nhạy cảm.

### 2. Redact hoặc tránh raw payload log

- [x] Rà log `PANCAKE_WEBHOOK_RAW_PAYLOAD`.
- [x] Đảm bảo path block không log raw payload chứa text bị chặn.
- [x] Nếu cần log payload, chỉ log metadata đã redact.
- [x] Không log `data.message.message`.
- [x] Không log attachment/raw data không cần thiết.
- [x] Không log AI payload vì AI không được gọi khi block.

Kết quả mong muốn:
  Message nguy hiểm không xuất hiện nguyên văn trong log application.

### 3. Bảo vệ response webhook

- [x] Response block không có `text`.
- [x] Response block không có `normalized_message.text`.
- [x] Response block không có raw payload.
- [x] Response block không có AI request/response.
- [x] Response block không có token/secret.
- [x] Response block chỉ có metadata cần thiết.

Kết quả mong muốn:
  Caller hoặc log response không thấy nội dung khách hàng bị chặn.

### 4. Không lộ secret/token

- [x] Không log Pancake page access token.
- [x] Không log URL Pancake đầy đủ có query token.
- [x] Không log env value.
- [x] Không log API key.
- [x] Không log database URL hoặc credential.
- [x] Không log header/params chứa secret.

Kết quả mong muốn:
  Phase này không làm tăng bề mặt lộ secret trong log.

### 5. Logging khi keyword file lỗi

- [x] Log lỗi load keyword file có reason rõ.
- [x] Log lỗi load keyword file không chứa full text khách hàng.
- [x] Log lỗi load keyword file không dump raw exception data nhạy cảm.
- [x] Return reason nội bộ rõ để test.
- [x] Không gọi AI khi lỗi load keyword file.

Kết quả mong muốn:
  Fail-closed path cũng an toàn dữ liệu.

## Acceptance criteria

- [x] Event block được log bằng metadata tối thiểu.
- [x] Full text khách hàng bị block không xuất hiện trong log.
- [x] Raw payload chứa message bị block không xuất hiện trong log.
- [x] Response webhook khi block không chứa text khách hàng.
- [x] Token/secret không xuất hiện trong log block.
- [x] Logging/security tests pass.

## Ghi chú mở

- Nếu production cần audit nội dung bị chặn, nên thiết kế storage riêng có redaction, retention và quyền truy cập rõ ràng.
- Nếu raw payload logging đang dùng để debug production, cần chuyển sang metadata hoặc bật debug có redaction trước khi rollout.
