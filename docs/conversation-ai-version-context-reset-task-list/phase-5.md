# Task List Phase 5: Concurrency, logging và fallback

## Mục tiêu

Phase 5 làm version upgrade an toàn khi có nhiều message đồng thời, lỗi AI/DB hoặc cấu hình version không hợp lệ.

Kết quả mong muốn:

- Một conversation chỉ có một upgrade sequence cho mỗi target version.
- Lỗi từng bước có reason rõ và không update version nhầm.
- Log đủ debug nhưng không chứa raw history.

## Đầu vào đã chốt

- Phase 4 đã tích hợp B1-B4.
- Version chỉ update sau B3 success.
- Retry phase đầu có semantics at-least-once.
- Production topology phải được xác nhận.

## Ngoài phạm vi Phase 5

- Không xây dashboard monitoring mới.
- Không thay transport retry hiện tại nếu không cần.
- Không thêm LLM summarizer.
- Không tự downgrade version.

## File chính dự kiến sửa

- `app/services/ai_version_context_service.py`
- `app/api/v1/facebook_webhook.py`
- `app/api/v1/pancake_webhook.py`
- Các test tương ứng

## Checklist

### 1. Concurrency guard

- [x] Lock/claim theo `conversation.id`.
- [x] Reload conversation sau khi nhận lock.
- [x] Compare version lại trước khi build versioned AI user.
- [x] Request chờ thấy version mới thì đi normal flow.
- [x] Test hai message khác `message_mid` đến đồng thời.
- [ ] Xác nhận giải pháp hoạt động với số replica production.

Kết quả mong muốn:
  Không có hai init/context sequence xen kẽ trên cùng target session.

### 2. Failure theo step

- [x] Persist init state failure dừng trước init.
- [x] Build AI user failure dừng trước init.
- [x] Init failure dừng trước context.
- [x] History query failure fallback history rỗng.
- [x] B3 failure giữ version cũ.
- [x] Version save failure không báo completed.

Kết quả mong muốn:
  Không có trạng thái version mới giả khi AI chưa nhận context.

### 3. Version edge cases

- [x] Missing DB version dùng baseline.
- [x] Invalid DB version warning, không upgrade tự động.
- [x] Invalid env error, không tạo session versioned mới.
- [x] Higher DB version warning, không downgrade.
- [x] Rollback env được test.

Kết quả mong muốn:
  Sai config hoặc rollback không tạo hàng loạt session sai version.

### 4. Logging

- [x] Log check/start/session_selected/init/context/completed/failed.
- [x] Log old/target version và step.
- [x] Log history count, không log content.
- [x] Không log full AI payload/token.
- [x] Có duration tổng và từng step nếu hữu ích.

Kết quả mong muốn:
  Vận hành biết migration kẹt ở đâu mà không lộ dữ liệu khách.

### 5. Audit metadata

- [x] Chỉ lưu from/to/count/context_sent nếu cần.
- [x] Không lưu raw transcript lần hai.
- [x] Metadata failure reason không chứa AI response nhạy cảm.
- [x] Audit write failure không làm sai version state.

Kết quả mong muốn:
  Có dấu vết kiểm tra mà không phình DB hoặc nhân bản PII.

## Acceptance criteria

- [x] Race test chỉ có một upgrade sequence trong cùng process.
- [x] Tất cả failure branch giữ version đúng.
- [x] Rollback không downgrade.
- [x] Log không có raw history.
- [x] Retry behavior được mô tả và test.

## Ghi chú mở

- Hiện đã implement in-memory lock theo `conversation.id + target_version`, đủ cho một process. Multi-replica vẫn cần xác nhận production topology hoặc nâng lên Mongo lease/atomic claim.
- Nếu cần exactly-once thay vì at-least-once, mở rộng schema migration state ở task riêng hoặc ngay phase này sau khi xác nhận topology.
