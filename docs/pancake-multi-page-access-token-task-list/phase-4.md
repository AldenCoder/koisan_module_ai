# Task List Phase 4: Logging, tài liệu cấu hình và rollout an toàn

## Mục tiêu

Phase 4 hoàn thiện tài liệu cấu hình, logging an toàn và checklist rollout production cho multi-page Pancake token. Trọng tâm là giúp vận hành thêm page mới mà không cấu hình nhầm và không làm lộ token.

Kết quả mong muốn:

- Tài liệu chính mô tả env mapping rõ ràng.
- `.env.example` có ví dụ đúng.
- Log lỗi thiếu token đủ thông tin để debug nhưng không chứa token.
- Rollout checklist có bước kiểm tra từng page.
- Có hướng dẫn xóa/không dùng `PANCAKE_PAGE_ACCESS_TOKEN` cũ.

## Đầu vào đã chốt

- Không fallback sang token mặc định.
- Env mapping là `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Missing token là lỗi cấu hình.
- Token không được log.
- Một page mới phải được thêm vào env mapping trước khi bật webhook.

## Ngoài phạm vi Phase 4

- Không implement secret manager.
- Không build UI cấu hình.
- Không thay đổi database.
- Không gọi Pancake thật trong test.

## File chính dự kiến sửa

- [docs/pancake-multi-page-access-token.md](../pancake-multi-page-access-token.md)
- [docs/pancake-multi-page-access-token-task-list/phase-0.md](phase-0.md)
- [docs/pancake-multi-page-access-token-task-list/phase-1.md](phase-1.md)
- [docs/pancake-multi-page-access-token-task-list/phase-2.md](phase-2.md)
- [docs/pancake-multi-page-access-token-task-list/phase-3.md](phase-3.md)
- [docs/pancake-multi-page-access-token-task-list/phase-5.md](phase-5.md)
- [.env.example](../../.env.example)
- Logging assertions trong tests nếu cần.

## Checklist

### 1. Cập nhật tài liệu chính

- [x] Mô tả vấn đề một token global không đủ cho multi-page.
- [x] Mô tả env mapping đúng.
- [x] Có ví dụ env với nhiều page.
- [x] Ghi rõ không fallback sang `PANCAKE_PAGE_ACCESS_TOKEN`.
- [x] Mô tả reason lỗi thiếu token theo page.
- [x] Mô tả logging không token.
- [x] Link đến task list từng phase.

Kết quả mong muốn:
  Dev/vận hành đọc tài liệu là hiểu cách cấu hình và behavior khi thiếu token.

### 2. Cập nhật `.env.example`

- [x] Thêm `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- [x] Dùng placeholder token.
- [x] Dùng page id mẫu rõ ràng.
- [x] Comment rằng JSON phải một dòng.
- [x] Comment rằng `PANCAKE_PAGE_ACCESS_TOKEN` cũ không dùng làm fallback multi-page.
- [x] Không để token thật.

Kết quả mong muốn:
  `.env.example` không dẫn người deploy tới cấu hình sai.

### 3. Logging an toàn

- [x] Log missing token có `page_id`.
- [x] Log missing token có `conversation_id` nếu có.
- [x] Log webhook processed/error có `message_mid` nếu có.
- [x] Không log raw env mapping.
- [x] Không log `page_access_token`.
- [x] Không log URL đầy đủ có query token.
- [x] Không log request params chứa token.

Kết quả mong muốn:
  Có đủ dữ liệu điều tra lỗi nhưng không lộ secret.

### 4. Rollout checklist cần chạy khi deploy production

Các mục dưới đây là runbook vận hành khi deploy thực tế; repo đã có checklist, nhưng chưa đánh dấu là đã deploy production.

- [ ] Liệt kê toàn bộ page đang kết nối Pancake webhook.
- [ ] Lấy token từng page.
- [ ] Tạo JSON mapping một dòng.
- [ ] Validate JSON trước khi deploy.
- [ ] Deploy vào staging nếu có.
- [ ] Gửi test message từng page.
- [ ] Kiểm tra reply đúng page/conversation.
- [ ] Kiểm tra log không có missing token.
- [ ] Kiểm tra log không có token.
- [ ] Deploy production.

Kết quả mong muốn:
  Rollout có trình tự rõ, giảm rủi ro thiếu page/token.

## Acceptance criteria

- [x] Tài liệu chính đầy đủ.
- [x] Task list từng phase đầy đủ.
- [x] `.env.example` có config mapping.
- [x] Logging không lộ token.
- [x] Rollout checklist đủ dùng cho production.

## Ghi chú mở

- Có thể thêm script validate JSON env nếu production thường cấu hình thủ công.
- Nếu dùng platform env không thích quote `'...'`, cần test đúng cú pháp của platform đó.
