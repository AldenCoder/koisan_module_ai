# Task List Phase 0: Chốt giải pháp update status handover

## Mục tiêu

Phase 0 chốt lại phạm vi triển khai: BE vẫn giữ nguyên luồng Facebook Page Inbox hiện tại, vẫn gọi Brain/AI Agent qua `FB_AI_CHAT_URL`, vẫn gửi tin nhắn Facebook cho khách như hiện tại. Phần mới chỉ là detect keyword/pattern handover trong text trả lời của Brain/AI Agent và update conversation hiện tại sang `status = "handover"` khi match.

## Quyết định cần chốt

- BE vẫn gọi `FB_AI_CHAT_URL` bằng payload hiện tại.
- BE vẫn extract text trả lời bằng logic hiện tại trong `facebook_webhook.py`.
- Brain/AI Agent không cần đổi response contract.
- Handover detection chạy ở BE sau khi có text trả lời từ Brain/AI Agent.
- Nếu match handover, BE update conversation hiện tại theo `conversation_id`.
- Field update là `conversations.status`, giá trị mới là `handover`.
- Không dùng các field pause như `bot_paused_at`, `bot_paused_until`, `bot_paused_reason`, `bot_paused_by`.
- Không pause bot; nếu khách hỏi tiếp, BE vẫn xử lý tiếp như hiện tại.
- Khách vẫn nhận được tin nhắn Facebook như hiện tại khi match handover.
- Không thêm queue, outbox, bảng mới hoặc màn hình admin trong phase này.

## Ngoài phạm vi Phase 0

- Chưa sửa enum/schema status.
- Chưa viết detector keyword/pattern.
- Chưa tích hợp update status vào webhook.
- Chưa thêm test.
- Chưa thay đổi behavior gửi Facebook message.

## File tài liệu liên quan

- [docs/facebook-page-inbox-handover-status.md](../facebook-page-inbox-handover-status.md)
- [docs/facebook-page-inbox-handover-status-task-list/phase-1.md](phase-1.md)
- [docs/facebook-page-inbox-handover-status-task-list/phase-2.md](phase-2.md)
- [docs/facebook-page-inbox-handover-status-task-list/phase-3.md](phase-3.md)
- [docs/facebook-page-inbox-handover-status-task-list/phase-4.md](phase-4.md)

## Checklist

### 1. Chốt input detect

- [x] Xác nhận input detect là text trả lời từ Brain/AI Agent, không phải tin nhắn khách.
- [x] Xác nhận detector chạy sau bước BE extract/prepare text trả lời.
- [x] Xác nhận không yêu cầu Brain trả thêm field `handover`.
- [x] Xác nhận không đổi format response từ `FB_AI_CHAT_URL`.

Kết quả mong muốn:
  Team thống nhất BE là nơi tự detect handover dựa trên text AI đã trả.

### 2. Chốt output khi match

- [x] Xác nhận output lưu vào DB là `conversations.status = "handover"`.
- [x] Xác nhận update dựa trên `conversation_id` của conversation hiện tại.
- [x] Xác nhận không tạo field handover mới.
- [x] Xác nhận không dùng các field pause của bot cho task này.

Kết quả mong muốn:
  Dashboard/API conversation có thể dùng field `status` hiện có để lọc case cần handover.

### 3. Chốt behavior với khách hàng

- [x] Xác nhận tin nhắn Facebook vẫn được gửi cho khách như hiện tại.
- [x] Xác nhận lỗi update status không làm fail reply Facebook.
- [x] Xác nhận nếu khách hỏi tiếp, BE vẫn gọi Brain/AI Agent như hiện tại.
- [x] Xác nhận match handover nhiều lần trên cùng conversation không làm lỗi flow.

Kết quả mong muốn:
  Update status là side effect nội bộ, không làm thay đổi trải nghiệm chat hiện tại của khách.

### 4. Chốt cách update

- [x] Ưu tiên reuse service update conversation trong cùng BE process nếu webhook đang chạy cùng process.
- [x] Nếu cần đúng nghĩa call API, dùng `PATCH /api/v1/conversations/{conversation_id}`.
- [x] Payload update là `{"status": "handover"}`.
- [x] Không hard-code token hoặc auth header nội bộ trong source/docs.

Kết quả mong muốn:
  Implementation có một đường update rõ ràng, tránh vừa service call vừa HTTP self-call lẫn lộn.

## Acceptance criteria

- [x] Tài liệu chính mô tả đúng mục tiêu update status handover.
- [x] Team chốt scope chỉ tập trung vào update conversation status.
- [x] Team chốt không pause bot trong scope task này.
- [x] Team chốt status mới là `handover`.
- [x] Team chốt detector chạy trên text trả lời từ Brain/AI Agent.

## Ghi chú mở

- Code hiện tại chưa có `HANDOVER = "handover"` trong enum/schema, nên phase 1 phải bổ sung trước khi update status có thể pass validation.
- Nếu sau này cần báo admin, nên làm task riêng thay vì gộp vào task update status này.
