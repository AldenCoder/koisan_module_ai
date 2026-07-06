# Hỗ trợ nhiều Pancake page access token

## Mục tiêu

Tài liệu này mô tả phương án để `BE` nhận webhook từ nhiều Pancake page trên cùng một endpoint, sau đó gửi reply/upload media/gửi `content_ids` bằng đúng `page_access_token` của `page_id` phát sinh message.

Điểm thay đổi chính: `BE` không dùng một `PANCAKE_PAGE_ACCESS_TOKEN` chung cho mọi page. Thay vào đó, `BE` đọc mapping `page_id -> page_access_token` từ env, bắt buộc lookup được token theo `page_id` trước khi gọi Pancake Public API. Nếu không có token cho page đó thì trả lỗi cấu hình và không gửi reply, để tránh gửi nhầm bằng token của page/group khác.

Quy ước thuật ngữ:

- `BE` / `Backend`: repo hiện tại `koisan_module_ai`.
- `Pancake`: nền tảng nhận/gửi tin nhắn khách qua Public API.
- `page_id`: ID page/kênh phát sinh webhook Pancake.
- `page_access_token`: token Pancake Public API dùng để gửi reply/upload cho đúng page.
- `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`: env JSON mapping từ `page_id` sang `page_access_token`.
- `pancake_conversation_id`: id hội thoại phía Pancake.
- `content_id`: id nội dung do Pancake trả về sau khi upload file.

## Luồng tổng thể

Khách hàng nhắn tin vào một page đã nối Pancake.

Pancake gửi webhook sang `BE`, payload có `page_id`; nếu field gốc ở root không có thì flow normalize hiện tại có thể lấy từ `data.message.page_id`.

`BE` normalize payload, xác định `normalized["page_id"]` và `normalized["pancake_conversation_id"]`.

`BE` xử lý hội thoại như hiện tại: chống trùng message, lưu user message, gọi AI/rule để tạo reply.

Trước mỗi lần gọi Pancake Public API, `BE` lookup token bằng `page_id`:

```text
page_access_token = PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID[page_id]
```

Nếu lookup thành công, `BE` dùng token đó để:

- Gửi text reply.
- Upload ảnh lên `upload_contents`.
- Gửi image message bằng `content_ids`.

Nếu lookup thất bại, `BE` dừng bước gửi Pancake và trả lỗi cấu hình `missing_pancake_page_access_token_for_page`. Không fallback sang token khác.

## Ranh giới trách nhiệm

### BE hiện tại

BE chịu trách nhiệm:

- Normalize được `page_id` từ webhook Pancake.
- Parse env `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Validate mapping là object JSON có key/value dạng string.
- Lookup token bắt buộc theo `page_id` trước khi gọi Pancake Public API.
- Không gửi reply/upload/send media nếu thiếu token cho `page_id`.
- Không fallback sang `PANCAKE_PAGE_ACCESS_TOKEN`.
- Không log token hoặc URL chứa token.
- Trả lỗi cấu hình rõ ràng nếu thiếu token cho page.

### Pancake

Pancake chịu trách nhiệm:

- Gửi webhook có `page_id` hoặc dữ liệu đủ để BE normalize ra `page_id`.
- Cấp `page_access_token` riêng cho từng page cần gửi reply.
- Chấp nhận Public API request với token đúng page.

### Vận hành / cấu hình

Người vận hành chịu trách nhiệm:

- Thêm đầy đủ mọi `page_id` đang dùng webhook vào `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Không commit token vào repo.
- Không giữ token của page khác làm fallback chung.
- Rotate token nếu token bị lộ.

### Ngoài phạm vi phương án này

- Không tự động lấy token từ Pancake.
- Không thêm UI quản lý token.
- Không lưu token vào database.
- Không cho phép fallback sang token mặc định vì có rủi ro gửi nhầm page/group.
- Không đổi logic normalize webhook ngoài phần đảm bảo có `page_id`.

## Cấu hình env

Không dùng nhiều dòng env cùng tên:

```env
PANCAKE_PAGE_ACCESS_TOKEN=token_page_1
PANCAKE_PAGE_ACCESS_TOKEN=token_page_2
```

Env chỉ giữ một giá trị cho một key; dòng sau có thể override dòng trước.

Config đúng là một JSON object một dòng:

```env
PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID='{"970198996185881":"pancake_token_for_page_970198996185881","tt_6711731671916708866":"pancake_token_for_page_tt_6711731671916708866"}'
```

Ví dụ với 3 page:

```env
PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID='{"970198996185881":"token_page_facebook_main","970198996185882":"token_page_facebook_backup","tt_6711731671916708866":"token_page_tiktok_shop"}'
```

Quy tắc format:

- Key luôn là `page_id` dạng string.
- Value luôn là `page_access_token` dạng string.
- JSON phải nằm trên một dòng.
- Không có trailing comma.
- Không thêm comment trong JSON.
- Nếu token có ký tự đặc biệt, vẫn để trong chuỗi JSON và bọc toàn bộ env value bằng dấu `'...'`.

`PANCAKE_PAGE_ACCESS_TOKEN` cũ không được dùng làm fallback trong phương án multi-page này. Nếu vẫn còn trong `.env`, code mới không nên dùng nó cho Pancake reply khi đã triển khai mapping bắt buộc.

## Contract lookup token

Input:

| Field | Nguồn | Ghi chú |
|---|---|---|
| `page_id` | `normalized["page_id"]` | Bắt buộc có trước khi gửi Pancake API |
| `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID` | Env | JSON mapping `page_id -> token` |

Output thành công:

```json
{
  "ok": true,
  "page_id": "970198996185881",
  "page_access_token": "***"
}
```

Token thật chỉ dùng nội bộ để gọi API, không trả ra response/log.

Output lỗi khi thiếu token:

```json
{
  "ok": false,
  "reason": "missing_pancake_page_access_token_for_page",
  "page_id": "970198996185881",
  "non_retryable": true
}
```

Output lỗi khi env sai format:

```json
{
  "ok": false,
  "reason": "invalid_pancake_page_access_tokens_by_page_id",
  "non_retryable": true
}
```

## Thay đổi code đề xuất

### `app/core/config.py`

Thêm config mới:

```python
pancake_page_access_tokens_by_page_id: Optional[str] = None
```

Không thêm fallback logic ở config. Config chỉ đọc raw env; service chịu trách nhiệm parse/validate.

### `app/services/pancake_message_service.py`

Thêm helper parse mapping:

```python
def _get_pancake_page_access_tokens_by_page_id() -> dict[str, str]:
    ...
```

Helper này cần:

- Đọc `settings.pancake_page_access_tokens_by_page_id`.
- `json.loads()` raw string.
- Kiểm tra kết quả là dict.
- Strip key/value.
- Bỏ entry key/value rỗng.
- Raise hoặc trả lỗi có reason nếu JSON sai format.
- Không log token.

Sửa helper lấy token:

```python
def _get_pancake_page_access_token_for_page(*, page_id: str) -> str:
    ...
```

Logic bắt buộc:

1. Normalize `page_id`.
2. Nếu `page_id` rỗng, lỗi `missing_page_id`.
3. Parse mapping `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
4. Nếu mapping có token cho `page_id`, trả token.
5. Nếu không có token, lỗi `missing_pancake_page_access_token_for_page`.
6. Không fallback sang `settings.pancake_page_access_token`.

Các hàm cần dùng helper mới:

- `send_pancake_reply`
- `upload_pancake_content`
- `send_pancake_content_ids`

Các hàm này đã nhận `page_id`, nên contract gọi từ webhook gần như không đổi.

### `app/api/v1/pancake_webhook.py`

Không cần truyền token từ webhook xuống nếu `pancake_message_service` tự lookup bằng `page_id`.

Cần đảm bảo mọi call đã truyền đúng `page_id`:

- Text reply dùng `normalized["page_id"]`.
- Upload ảnh dùng `normalized["page_id"]`.
- Gửi `content_ids` dùng `normalized["page_id"]`.

Nếu Pancake send API trả lỗi thiếu token theo page, webhook vẫn lưu user message, nhưng bot reply/send result phải ghi reason rõ để debug.

### `.env.example`

Thay config single-token bằng mapping hoặc thêm mapping rõ ràng:

```env
PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID='{"970198996185881":"replace_with_page_970198996185881_token","tt_6711731671916708866":"replace_with_page_tt_6711731671916708866_token"}'
```

Nếu giữ `PANCAKE_PAGE_ACCESS_TOKEN` trong `.env.example` để tương thích tài liệu cũ, cần comment rõ:

```env
# Deprecated for multi-page Pancake webhook. Do not use as fallback.
# PANCAKE_PAGE_ACCESS_TOKEN=
```

## Luồng lỗi

### Thiếu token cho page

Ví dụ webhook có `page_id=970198996185881` nhưng env không có key này.

Kết quả mong muốn:

- Không gọi Pancake Public API.
- Không dùng token của page khác.
- Log warning/error có `page_id` và reason.
- Không log token mapping.
- Return/send result có `reason=missing_pancake_page_access_token_for_page`.

### Env JSON sai format

Ví dụ:

```env
PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID='{"page_1":"token_1",}'
```

Kết quả mong muốn:

- Không gọi Pancake Public API.
- Trả reason `invalid_pancake_page_access_tokens_by_page_id`.
- Log lỗi rút gọn, không in raw env vì raw env chứa token.

### Thiếu `page_id`

Nếu webhook không normalize được `page_id`:

- Không lookup token.
- Không gọi Pancake API.
- Trả reason `missing_page_id`.

## Logging

Log được phép có:

- `page_id`
- `conversation_id`
- `message_mid`
- `reason`
- `status_code`

Không log:

- `page_access_token`
- Raw env `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`
- URL đầy đủ có query `page_access_token`
- Headers hoặc params chứa token

## Test cần có

### Config/token lookup

- [x] Parse env JSON hợp lệ thành mapping.
- [x] Strip whitespace ở `page_id` và token.
- [x] Bỏ entry key/value rỗng.
- [x] Env rỗng trả lỗi `missing_pancake_page_access_tokens_by_page_id`.
- [x] Env sai JSON trả lỗi `invalid_pancake_page_access_tokens_by_page_id`.
- [x] Không có token cho `page_id` trả lỗi `missing_pancake_page_access_token_for_page`.
- [x] Có `PANCAKE_PAGE_ACCESS_TOKEN` cũ nhưng thiếu mapping theo page vẫn không fallback.

### Pancake message service

- [x] `send_pancake_reply` dùng đúng token theo `page_id`.
- [x] `upload_pancake_content` dùng đúng token theo `page_id`.
- [x] `send_pancake_content_ids` dùng đúng token theo `page_id`.
- [x] Thiếu token theo page thì không gọi HTTP client.
- [x] Token không xuất hiện trong response lỗi.

### Webhook flow

- [x] Message từ page A dùng token A để gửi text reply.
- [x] Message từ page B dùng token B để gửi text reply.
- [x] Upload ảnh từ page A dùng token A.
- [x] Gửi `content_ids` từ page B dùng token B.
- [x] Page chưa cấu hình token thì lưu user message nhưng không gửi bot reply bằng token khác.

## Rollout

1. Lấy danh sách toàn bộ `page_id` đang gửi webhook vào backend.
2. Lấy `page_access_token` tương ứng từng page từ Pancake.
3. Tạo env `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID` dạng JSON một dòng.
4. Deploy code có lookup token bắt buộc theo `page_id`.
5. Gửi test message từng page.
6. Kiểm tra log không có `missing_pancake_page_access_token_for_page`.
7. Kiểm tra Pancake nhận reply đúng page/conversation.
8. Sau khi ổn định, xóa hoặc không sử dụng `PANCAKE_PAGE_ACCESS_TOKEN` cũ để tránh hiểu nhầm.

## Acceptance criteria

- [x] Có env mapping `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- [x] Backend parse được mapping `page_id -> token`.
- [x] Mỗi Pancake API call dùng token theo đúng `page_id`.
- [x] Không fallback sang token mặc định khi thiếu token theo page.
- [x] Thiếu token theo page trả lỗi rõ ràng và không gọi Pancake API.
- [x] Token không bị log.
- [x] Tests multi-page pass bằng mock.

Task list chi tiết từng phase:

- [Phase 0. Chốt giải pháp nhiều Pancake page access token](pancake-multi-page-access-token-task-list/phase-0.md)
- [Phase 1. Cấu hình env và parse mapping token](pancake-multi-page-access-token-task-list/phase-1.md)
- [Phase 2. Lookup token theo page trong Pancake message service](pancake-multi-page-access-token-task-list/phase-2.md)
- [Phase 3. Tích hợp webhook flow và xử lý lỗi gửi Pancake](pancake-multi-page-access-token-task-list/phase-3.md)
- [Phase 4. Logging, tài liệu cấu hình và rollout an toàn](pancake-multi-page-access-token-task-list/phase-4.md)
- [Phase 5. Test và rollout multi-page Pancake token](pancake-multi-page-access-token-task-list/phase-5.md)

Tiến độ hiện tại:

- [x] Phase 0. Chốt giải pháp nhiều Pancake page access token.
- [x] Phase 1. Cấu hình env và parse mapping token.
- [x] Phase 2. Lookup token theo page trong Pancake message service.
- [x] Phase 3. Tích hợp webhook flow và xử lý lỗi gửi Pancake.
- [x] Phase 4. Logging, tài liệu cấu hình và rollout an toàn.
- [x] Phase 5. Test và rollout multi-page Pancake token.

Ghi chú: phần code, test mock, tài liệu và checklist rollout đã hoàn tất trong repo. Các bước deploy/staging/production thật vẫn phải chạy theo checklist ở Phase 4 và Phase 5 khi triển khai.

## Ghi chú production

- Luôn coi thiếu token theo page là lỗi cấu hình nghiêm trọng.
- Không dùng token page khác để "cứ gửi được trước"; gửi nhầm page/group nguy hiểm hơn không gửi.
- Nên có alert theo reason `missing_pancake_page_access_token_for_page`.
- Khi thêm page mới vào Pancake webhook, phải thêm key mới vào `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID` trong cùng checklist rollout.
- Khi rotate token một page, chỉ thay value của đúng `page_id`, không đổi key.
