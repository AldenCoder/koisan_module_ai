# Task List Phase 3: Query và sanitize text history

## Mục tiêu

Phase 3 xây helper lấy version history từ `staff/user/bot`, loại toàn bộ URL/rỗng và render tối đa số message theo env để chuẩn bị gửi AI. Handover context vẫn giữ contract riêng chỉ lấy `staff/user`.

Kết quả mong muốn:

- Context history chỉ chứa text.
- Limit áp dụng trên item hợp lệ sau sanitize.
- Timeline render cũ đến mới.
- Current customer message không bị lặp.

## Đầu vào đã chốt

- Dùng lại env limit `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`.
- Nguồn là collection `messages` nội bộ.
- Version context chỉ nhận role `staff`, `user` và `bot`.
- Không gọi Facebook/Pancake history API.
- Không OCR hoặc fetch URL.

## Ngoài phạm vi Phase 3

- Không gọi init.
- Không update version.
- Không gửi payload AI thật.
- Không tóm tắt bằng LLM phụ.

## File chính dự kiến sửa

- `app/services/ai_version_context_service.py`
- `app/models/messages.py` nếu cần index/query helper
- `tests/test_ai_version_context_service.py`

## Checklist

### 1. Query history

- [x] Filter đúng `conversation_id`.
- [x] Chỉ lấy `role in [staff, user, bot]` cho version context.
- [x] Exclude current message bằng timestamp/id/message IDs của batch.
- [x] Query mới đến cũ để ưu tiên history gần nhất.
- [x] Fetch theo batch nếu cần để limit sau sanitize.

Kết quả mong muốn:
  Helper không lấy nhầm conversation hoặc lặp current customer message.

### 2. Sanitize text

- [x] Trim whitespace.
- [x] Loại `http://`, `https://`, `www.` URL.
- [x] Link-only content thành empty và bị skip.
- [x] Mixed text/URL giữ phần text.
- [x] Không serialize attachment/meta/raw payload.
- [x] Normalize khoảng trắng sau khi xóa URL.

Kết quả mong muốn:
  100% history context là text có nghĩa.

### 3. Limit và sort

- [x] Limit sau sanitize.
- [x] Lấy tối đa N item hợp lệ mới nhất.
- [x] Render item được chọn theo `created_at` tăng dần.
- [x] Có tie-break ổn định khi timestamp bằng nhau.
- [x] Clamp N trong khoảng `1..50`.

Kết quả mong muốn:
  Context ổn định, đủ gần và không tăng payload không giới hạn.

### 4. Render context

- [x] `staff` map `[Nhân viên]`.
- [x] `user` map `[Khách]`.
- [x] `bot` map `[Bot]`.
- [x] Current message nằm ở section riêng và là latest customer content sạch, không phải handover-wrapped content.
- [x] History rỗng trả current content gốc.
- [x] Không log transcript.

Kết quả mong muốn:
  Payload builder cấp cao nhận được context đã render sẵn.

## Acceptance criteria

- [x] Empty/link-only item bị loại.
- [x] Mixed content không còn URL.
- [x] Limit sau sanitize được test.
- [x] Timeline và role label đúng.
- [x] Current message không lặp.
- [x] Raw history không xuất hiện trong log.

## Ghi chú mở

- Regex URL cần test punctuation và nhiều URL trong một content.
- Nếu text quá dài dù chỉ có ít message, cân nhắc thêm max chars/token ở task sau; phase đầu giữ đúng yêu cầu max messages.
