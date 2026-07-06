# Task List Phase 6: Rollout và vận hành

## Mục tiêu

Phase 6 chuẩn bị rollout sau khi code và test đã hoàn tất. Trọng tâm là triển khai BE trước, sau đó mới cập nhật AI Agent để gọi API `order-notes`.

Kết quả mong muốn:

- BE hỗ trợ field/status/API mới trước khi AI gọi.
- AI Agent nhận được `conversation_id` trong context.
- AI Agent gọi đúng payload 2 field.
- Dashboard/sale hiểu `order_pending -> new`.
- Có log để phát hiện AI gửi sai `conversation_id`.

## Trạng thái hiện tại

- [x] Code BE cho field/status/API order note đã hoàn tất.
- [x] Code gửi `conversation_id` sang AI ở message thường đã hoàn tất.
- [x] Test suite local đã pass.
- [ ] Chưa deploy môi trường thật trong phase này.
- [ ] Chưa cập nhật instruction phía AI Agent trong môi trường thật.
- [ ] Chưa smoke test sau deploy.

## Đầu vào đã chốt

- Không cần migration bắt buộc cho conversation cũ.
- Conversation cũ thiếu `order_note` vẫn hợp lệ.
- Endpoint order note là write path chính.
- Không chống duplicate trong phase này.

## Ngoài phạm vi Phase 6

- Không deploy từ tài liệu này.
- Không tạo script migration.
- Không thêm monitoring platform mới.
- Không sửa UI ngoài các cấu hình cần thiết nếu dashboard đã có status update.

## Checklist

### 1. Thứ tự deploy

- [ ] Deploy BE có model/schema `order_note`.
- [ ] Deploy BE có status `order_pending`.
- [ ] Deploy BE có endpoint `POST /api/v1/order-notes`.
- [ ] Deploy BE có context message gửi `conversation_id` sang AI.
- [ ] Kiểm tra healthcheck backend.
- [ ] Sau khi BE sẵn sàng, cập nhật instruction phía AI Agent.

Kết quả mong muốn:
  AI không gọi endpoint khi BE chưa có API.

### 2. Cập nhật instruction phía AI Agent

- [ ] Hướng dẫn AI đọc `conversation_id` từ context note.
- [ ] Hướng dẫn AI khi khách đặt/sửa/thêm đơn thì gọi `POST /api/v1/order-notes`.
- [ ] Hướng dẫn payload chỉ có `conversation_id` và `order_note`.
- [ ] Hướng dẫn không tự bịa `conversation_id`.
- [ ] Hướng dẫn nếu không thấy `conversation_id` thì không gọi API order note.
- [ ] Hướng dẫn `order_note` là tóm tắt dễ đọc cho sale.

Kết quả mong muốn:
  AI gọi API đúng contract và không cố suy luận id.

### 3. Kiểm tra dashboard/sale

- [ ] Dashboard đọc được status `order_pending`.
- [ ] Dashboard hiển thị được `order_note`.
- [ ] Sale có thao tác đổi status về `new`.
- [ ] Sau khi đổi về `new`, dashboard không còn hiển thị note cũ.
- [ ] Sale hiểu note có thể gồm nhiều dòng `1.`, `2.`, `3.`.

Kết quả mong muốn:
  Quy trình vận hành đơn giản: thấy pending, xử lý, đổi về new.

### 4. Theo dõi log

- [ ] Theo dõi `ORDER_NOTE_CONVERSATION_ID_INVALID`.
- [ ] Theo dõi `ORDER_NOTE_CONVERSATION_NOT_FOUND`.
- [ ] Theo dõi tần suất note bị append nhiều lần giống nhau.
- [ ] Kiểm tra log không in toàn bộ dữ liệu nhạy cảm của khách nếu không cần.
- [ ] Nếu lỗi id xảy ra nhiều, kiểm tra context note gửi sang AI.

Kết quả mong muốn:
  Phát hiện sớm lỗi AI lấy sai hoặc thiếu `conversation_id`.

### 5. Smoke test sau deploy

- [ ] Tạo/lấy một conversation test.
- [ ] Gửi message qua webhook để kiểm tra AI payload có `conversation_id`.
- [ ] Gọi thử `POST /api/v1/order-notes` với conversation test.
- [ ] Xác nhận conversation chuyển `order_pending`.
- [ ] Xác nhận `order_note` có dòng `1.`.
- [ ] Gọi thêm lần hai, xác nhận có dòng `2.`.
- [ ] Đổi status về `new`.
- [ ] Xác nhận `order_note = null`.
- [ ] Gọi thử sai `conversation_id`, xác nhận không update gì và có warning log.

Kết quả mong muốn:
  Flow end-to-end chạy đúng trước khi mở rộng cho toàn bộ traffic.

### 6. Rollback notes

- [ ] Nếu AI gọi sai nhiều, tạm tắt instruction gọi API order note ở AI Agent.
- [ ] Nếu endpoint lỗi, BE vẫn có thể tiếp tục reply chat như hiện tại nếu API order note là side effect từ AI.
- [ ] Nếu dashboard chưa hiển thị được `order_pending`, rollback phần instruction AI trước.
- [ ] Không xóa field `order_note` khỏi dữ liệu production nếu đã deploy; chỉ dừng ghi thêm.

Kết quả mong muốn:
  Có đường lùi an toàn nếu behavior mới gây nhiễu vận hành.

## Acceptance criteria

- [ ] BE deploy xong trước khi AI gọi API.
- [ ] AI instruction đã cập nhật đúng payload 2 field.
- [ ] Dashboard thấy được `order_pending`.
- [ ] Sale đổi về `new` thì clear note.
- [ ] Warning log cho sai `conversation_id` hoạt động.
- [ ] Smoke test end-to-end pass.

## Ghi chú mở

- Nếu sau rollout thấy note trùng vì AI retry, mở phase riêng để thêm idempotency key.
- Nếu sale cần lịch sử order note đã xử lý, mở phase riêng để lưu history thay vì giữ trong field text hiện tại.
