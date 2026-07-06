# Task List Phase 0: Chốt contract version upgrade

## Mục tiêu

Phase 0 chốt tín hiệu version, cách tạo AI session mới theo version và ranh giới dữ liệu history trước khi sửa code.

Phase này chỉ hoàn thiện thiết kế. Chưa thêm config/model, chưa sửa webhook và chưa thêm test.

Kết quả mong muốn:

- Thống nhất contract version trong env và database.
- Thống nhất sequence B1-B4 mới: session mới → init → context → update version.
- Thống nhất history chỉ chứa text.
- Proposal chính có checklist implementation tổng hợp và task-list từng phase.

## Đầu vào đã chốt

- Env version là `AI_CONVERSATION_VERSION`.
- Dùng lại env limit hiện có `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`; không thêm max-message env mới.
- DB field là `conversations.version`.
- `Conversation.version` là `Optional[str]`, default `None`.
- Conversation thiếu version được xem là baseline `1.0`.
- Conversation mới được tạo trực tiếp bằng system version.
- Chỉ chạy upgrade khi DB version thấp hơn system version.
- Không downgrade khi DB version cao hơn env.
- Chỉ customer message đủ điều kiện gọi AI mới kích hoạt upgrade.
- AI session mới được tạo bằng versioned AI user `<sender_id>:v<version>`.
- Version chỉ update sau context/current message AI call thành công.
- Version history chỉ lấy text của role `staff`, `user` và `bot`; handover context vẫn chỉ lấy `staff` và `user`.
- Không log raw history.

## Ngoài phạm vi Phase 0

- Chưa thêm `version` vào model/schema.
- Chưa thêm env.
- Chưa implement version parser/comparator.
- Chưa sửa AI transport để dùng versioned AI user.
- Chưa query/sanitize history.
- Chưa thêm concurrency guard.
- Chưa rollout.

## File tài liệu liên quan

- [Proposal chính](../conversation-ai-version-context-reset.md)
- [Phase 1](phase-1.md)
- [Phase 2](phase-2.md)
- [Phase 3](phase-3.md)
- [Phase 4](phase-4.md)
- [Phase 5](phase-5.md)
- [Phase 6](phase-6.md)

## Checklist

### 1. Chốt version contract

- [x] Dùng `AI_CONVERSATION_VERSION`, ví dụ `1.1`.
- [x] Dùng lại `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES` cho history limit.
- [x] Chốt `Conversation.version` là `Optional[str]`.
- [x] Missing/null/empty DB version được xem là `1.0`.
- [x] So sánh numeric segments, không so sánh string.
- [x] DB version cao hơn env không bị downgrade.
- [x] System version sai format không được kích hoạt upgrade.

Kết quả mong muốn:
  Version comparison không tạo nhầm session khi rollback hoặc cấu hình sai.

### 2. Chốt session/version sequence

- [x] Persist `fb_ai_initialized=false` trước khi chuyển sang AI user mới.
- [x] Build AI user theo format `<sender_id>:v<system_version>`.
- [x] Await init thành công rồi mới gửi context.
- [x] Await context/current message thành công rồi mới update version.
- [x] Không gửi response init ra khách.

Kết quả mong muốn:
  AI session mới nhận instruction trước khi nhận lại lịch sử và customer message.

### 3. Chốt history contract

- [x] Version context lấy role `staff`, `user` và `bot`.
- [x] Bỏ content rỗng và URL-only.
- [x] Mixed text/URL chỉ giữ phần text.
- [x] Limit áp dụng sau sanitize.
- [x] Render các item được chọn theo thứ tự cũ đến mới.
- [x] Current customer message nằm riêng và không bị lặp.

Kết quả mong muốn:
  Context gửi AI chứa 100% text hội thoại hữu ích.

### 4. Chốt phạm vi webhook

- [x] Customer message bình thường mới kích hoạt version check.
- [x] Admin/bot echo/duplicate/blocked/paused message không kích hoạt.
- [x] Facebook và Pancake dùng chung contract/helper, tích hợp theo flow riêng.
- [x] Sender buffer Pancake chỉ chạy một upgrade cho cả batch.

Kết quả mong muốn:
  Version upgrade không chen vào các flow không gửi AI.

## Acceptance criteria

- [x] Proposal có đủ B1-B4.
- [x] Proposal có mục `Checklist implementation tổng hợp` theo từng phase.
- [x] Rule versioned AI user được mô tả rõ.
- [x] Rule text-only được mô tả rõ.
- [x] Rule conversation mới/same/higher version được mô tả rõ.
- [x] Proposal chốt `Conversation.version` là `Optional[str]`.
- [x] Failure và concurrency risk được ghi nhận.
- [ ] Chờ duyệt tài liệu trước khi code.

## Ghi chú mở

- Phase implementation phải xác nhận production có chạy nhiều replica hay không để chọn distributed lock/DB claim.
- Nếu chỉ rollout Pancake trước, vẫn giữ helper version/history độc lập để Facebook tích hợp sau mà không fork logic.
