# Task List Phase 1: Endpoint và cấu hình runtime

## Mục tiêu

Phase 1 tạo khung endpoint Pancake Webhook và bổ sung cấu hình runtime cần thiết. Sau phase này, BE có route nhận request Pancake, đọc được cấu hình token an toàn, log request ở mức kiểm soát, và có thể trả response skip/accepted rõ ràng dù chưa tích hợp đầy đủ normalize, database hoặc gửi reply.

## Phạm vi thay đổi

- Router FastAPI cho Pancake webhook.
- Include router vào API v1.
- Config env Pancake.
- Logging an toàn cho webhook.
- Response cơ bản cho request rỗng, invalid JSON, event không hỗ trợ.

## File dự kiến thay đổi

- [app/api/router_v1.py](../../app/api/router_v1.py)
- `app/api/v1/pancake_webhook.py`
- [app/core/config.py](../../app/core/config.py)
- [.env.example](../../.env.example)
- [README.md](../../README.md), nếu cần ghi thêm env/runtime.

## Checklist

### 1. Tạo router Pancake webhook

- [x] Tạo file `app/api/v1/pancake_webhook.py`.
- [x] Tạo FastAPI router với prefix `/pancake` và tag phù hợp.
- [x] Tạo endpoint `POST /webhook`.
- [x] Đảm bảo route public sau khi include là `/api/v1/pancake/webhook`.
- [x] Endpoint đọc raw body trước khi parse JSON để có thể log/debug rút gọn.
- [x] Endpoint xử lý body rỗng bằng response skip rõ reason.
- [x] Endpoint xử lý JSON invalid bằng response skip rõ reason.
- [x] Endpoint xử lý payload không phải object bằng response skip rõ reason.

Kết quả mong muốn:
  BE có endpoint Pancake riêng, nhận request ổn định và không crash với payload xấu.

### 2. Include router vào API v1

- [x] Mở [app/api/router_v1.py](../../app/api/router_v1.py).
- [x] Import router Pancake webhook mới.
- [x] Include router với prefix `/pancake`.
- [x] Đảm bảo không làm đổi prefix/tag của các router hiện có.
- [x] Kiểm tra OpenAPI route không trùng với route Facebook.

Kết quả mong muốn:
  Route Pancake được đăng ký trong app mà không ảnh hưởng các API hiện tại.

### 3. Thêm cấu hình runtime

- [x] Mở [app/core/config.py](../../app/core/config.py).
- [x] Thêm config `pancake_page_access_token`.
- [x] Thêm config timeout gửi Pancake Public API nếu dự kiến dùng chung ở phase 4.
- [x] Thêm config retry count/delay nếu dự kiến dùng ở phase 4.
- [x] Thêm config `pancake_admin_takeover_pause_minutes`, fallback về `fb_admin_takeover_pause_minutes` nếu chưa set.
- [x] Cập nhật [.env.example](../../.env.example) với biến Pancake, không đưa token thật.
- [x] Không commit token thật từ local `.env`.

Kết quả mong muốn:
  Runtime có chỗ đọc config Pancake an toàn, đúng pattern config hiện tại.

### 4. Logging an toàn

- [x] Log request Pancake ở mức đủ debug nhưng giới hạn độ dài payload.
- [x] Không log `page_access_token`.
- [x] Không log query string chứa token nếu Pancake gửi token qua URL.
- [x] Log `client_ip`, `path`, `event_type`, `page_id` nếu parse được.
- [x] Log reason khi skip request.

Kết quả mong muốn:
  Khi Pancake bắt đầu bắn webhook thật, BE có log đủ điều tra nhưng không lộ token.

### 5. Response contract cơ bản

- [x] Response accepted/ignored thống nhất có `status` hoặc `success`.
- [x] Non-`messaging` event trả skip nhưng không xem là server error.
- [x] Payload thiếu field ở phase này chưa cần xử lý sâu, nhưng response phải có reason.
- [x] Exception ngoài ý muốn được log bằng logger, không dùng print.
- [x] Không gọi AI hoặc Pancake Public API trong phase này.

Kết quả mong muốn:
  Endpoint có behavior tối thiểu rõ ràng, sẵn sàng để phase 2 thêm normalize.

### 6. Test endpoint cơ bản

- [x] Test body rỗng trả ignored.
- [x] Test invalid JSON trả ignored.
- [x] Test payload không phải object trả ignored.
- [x] Test non-`messaging` event trả ignored/accepted theo contract đã chọn.
- [x] Test route `/api/v1/pancake/webhook` được đăng ký.
- [x] Test không cần external service.

Kết quả mong muốn:
  Endpoint skeleton được cover và không cần Pancake thật.

## Acceptance criteria

- [x] Có file `app/api/v1/pancake_webhook.py`.
- [x] `POST /api/v1/pancake/webhook` tồn tại.
- [x] Config Pancake nằm trong settings/env example.
- [x] Request xấu không làm server crash.
- [x] Log không lộ token.
- [x] Test endpoint cơ bản pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Nếu sau này cần xác thực webhook riêng, nên mở task riêng khi đã có contract chính thức.
- Không chạy `pre-commit` theo guideline repo.
