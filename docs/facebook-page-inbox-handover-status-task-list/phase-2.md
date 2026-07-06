# Task List Phase 2: Xây detector handover

## Mục tiêu

Phase 2 xây helper detect handover dựa trên keyword/pattern trong text trả lời của Brain/AI Agent. Detector cần đơn giản, dễ test, hỗ trợ tiếng Việt có dấu và không dấu.

Detector chỉ xác định text trả lời có tín hiệu cần chuyển người phụ trách hay không. Detector không tự update database và không gửi Facebook message.

## Phạm vi thay đổi

- Helper normalize text.
- Danh sách keyword/pattern handover phase đầu.
- Hàm detect trả object debug nội bộ.
- Unit test cho detector.

## File dự kiến thay đổi

Tùy cách đặt code:

- [app/api/v1/facebook_webhook.py](../../app/api/v1/facebook_webhook.py)

Hoặc nếu tách service riêng:

- [app/services/facebook_handover_detection_service.py](../../app/services/facebook_handover_detection_service.py)
- [tests/test_facebook_handover_detection_service.py](../../tests/test_facebook_handover_detection_service.py)

Nếu để helper trong webhook:

- [tests/test_facebook_webhook_forward.py](../../tests/test_facebook_webhook_forward.py)

## Checklist

### 1. Thiết kế output detector

- [x] Tạo object/dict kết quả gồm `detected`, `reason`, `matched_pattern`.
- [x] Khi không match, trả `detected = false`.
- [x] Khi match, trả `reason = "ai_reply_handover_keyword"`.
- [x] Không đưa full text dài vào object debug nếu không cần log.
- [x] Không persist object debug xuống database.

Kết quả mong muốn:
  Caller có đủ thông tin để quyết định update status và log rút gọn.

### 2. Normalize text

- [x] Chuyển input về string an toàn, xử lý `None`.
- [x] Lowercase.
- [x] Trim đầu/cuối.
- [x] Gộp nhiều whitespace thành một whitespace.
- [x] Thay một số dấu câu phổ biến bằng khoảng trắng nếu cần.
- [x] Tạo bản bỏ dấu tiếng Việt bằng `unicodedata.normalize`.
- [x] Đảm bảo ký tự `đ`/`Đ` được map thành `d`.

Kết quả mong muốn:
  Các biến thể có dấu/không dấu và spacing khác nhau đều match ổn định.

### 3. Thêm pattern phase đầu

- [x] Detect `chuyển bộ phận phụ trách`.
- [x] Detect `em chuyển bộ phận phụ trách`.
- [x] Detect `em chuyển sale`.
- [x] Detect `cần bộ phận phụ trách kiểm tra`.
- [x] Detect `em chuyển xử lý`.
- [x] Hỗ trợ bản không dấu của các cụm trên.
- [x] Không dùng fuzzy matching trong phase đầu.

Pattern đề xuất:

```python
HANDOVER_REPLY_PATTERNS = [
    r"\b(?:em\s+)?chuyen\s+bo\s+phan\s+phu\s+trach\b",
    r"\bem\s+chuyen\s+sale\b",
    r"\bcan\s+bo\s+phan\s+phu\s+trach\s+kiem\s+tra\b",
    r"\bem\s+chuyen\s+xu\s+ly\b",
]
```

Kết quả mong muốn:
  Detector bắt đúng các cụm handover đã được chốt trong tài liệu chính.

### 4. Unit test detector

- [x] Test text có dấu match: `Dạ em chuyển sale hỗ trợ anh/chị ạ`.
- [x] Test text không dấu match: `Da em chuyen sale ho tro anh chi a`.
- [x] Test nhiều khoảng trắng vẫn match.
- [x] Test có dấu câu vẫn match.
- [x] Test cụm `chuyển bộ phận phụ trách` không có chữ `em` vẫn match.
- [x] Test text không liên quan không match.
- [x] Test input rỗng/`None` không match.

Kết quả mong muốn:
  Detector có coverage đủ để tránh miss các cụm phase đầu và tránh match text rỗng.

## Acceptance criteria

- [x] Có helper detector rõ ràng, dễ gọi từ webhook.
- [x] Detector match đủ 5 cụm đã chốt.
- [x] Detector hỗ trợ tiếng Việt có dấu và không dấu.
- [x] Detector không tự ghi DB.
- [x] Unit test detector pass.
- [x] `pytest -q` pass.

## Ghi chú mở

- Sau khi chạy thật, có thể mở rộng pattern bằng các câu AI hay dùng trong log.
- Nếu false positive nhiều, nên thu hẹp pattern trước khi nghĩ đến NLP/fuzzy matching.
