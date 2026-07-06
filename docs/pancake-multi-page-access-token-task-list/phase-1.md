# Task List Phase 1: Cấu hình env và parse mapping token

## Mục tiêu

Phase 1 thêm cấu hình `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID` và helper parse mapping `page_id -> page_access_token` an toàn. Mapping phải validate chặt chẽ, không log raw env vì raw env chứa token, và không fallback sang token mặc định.

Kết quả mong muốn:

- Backend đọc được env `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Backend parse được JSON object một dòng thành `dict[str, str]`.
- Backend phát hiện env thiếu hoặc sai format bằng reason rõ ràng.
- Backend không log token trong bất kỳ lỗi parse nào.
- `.env.example` có ví dụ cấu hình đúng.

## Đầu vào đã chốt

- Env mới là `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- Env có dạng JSON object một dòng.
- Key là `page_id` dạng string.
- Value là `page_access_token` dạng string.
- Không fallback sang `PANCAKE_PAGE_ACCESS_TOKEN`.
- Không commit token thật.

## Ngoài phạm vi Phase 1

- Không gọi Pancake Public API.
- Không sửa flow webhook.
- Không sửa logic upload/reply.
- Không thêm database hoặc UI quản lý token.
- Không tự động lấy token từ Pancake.

## File chính dự kiến sửa

- [app/core/config.py](../../app/core/config.py)
- [app/services/pancake_message_service.py](../../app/services/pancake_message_service.py)
- [.env.example](../../.env.example)
- [tests/test_pancake_message_service.py](../../tests/test_pancake_message_service.py)

## Checklist

### 1. Thêm config mới

- [x] Thêm field `pancake_page_access_tokens_by_page_id`.
- [x] Kiểu field có thể là `Optional[str]` để parse JSON thủ công.
- [x] Không remove ngay `pancake_page_access_token` nếu còn test/flow cũ phụ thuộc.
- [x] Không dùng `pancake_page_access_token` làm fallback trong helper mới.
- [x] Đảm bảo config đọc được từ `.env`.

Kết quả mong muốn:
  Settings có raw env mapping để service parse.

### 2. Parse JSON mapping

- [x] Thêm helper parse raw env thành dict.
- [x] Nếu raw env rỗng, trả lỗi `missing_pancake_page_access_tokens_by_page_id`.
- [x] Nếu JSON invalid, trả lỗi `invalid_pancake_page_access_tokens_by_page_id`.
- [x] Nếu JSON parse ra không phải object, trả lỗi `invalid_pancake_page_access_tokens_by_page_id`.
- [x] Strip whitespace ở key `page_id`.
- [x] Strip whitespace ở token.
- [x] Bỏ entry có key hoặc token rỗng.
- [x] Không log raw env.
- [x] Không log token value.

Kết quả mong muốn:
  Mapping token được parse an toàn và lỗi cấu hình dễ debug.

### 3. Chuẩn hóa env example

- [x] Thêm ví dụ `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- [x] Ví dụ dùng JSON một dòng.
- [x] Ví dụ có ít nhất hai `page_id`.
- [x] Dùng token placeholder, không dùng token thật.
- [x] Nếu giữ `PANCAKE_PAGE_ACCESS_TOKEN`, comment rõ không dùng làm fallback multi-page.
- [x] Không để nhiều dòng `PANCAKE_PAGE_ACCESS_TOKEN`.

Kết quả mong muốn:
  Người deploy copy được format env đúng và ít khả năng cấu hình nhầm.

### 4. Test phase 1

- [x] Test parse JSON mapping hợp lệ.
- [x] Test parse mapping có whitespace.
- [x] Test bỏ entry key rỗng.
- [x] Test bỏ entry token rỗng.
- [x] Test env rỗng trả reason rõ ràng.
- [x] Test JSON sai format trả reason rõ ràng.
- [x] Test JSON array/string không được chấp nhận.
- [x] Test token không xuất hiện trong error response/log fixture nếu có.

Kết quả mong muốn:
  Config parser được cover bằng unit test, không cần gọi network.

## Acceptance criteria

- [x] Có config `PANCAKE_PAGE_ACCESS_TOKENS_BY_PAGE_ID`.
- [x] Parse được mapping hợp lệ.
- [x] Reject được env rỗng/sai format.
- [x] Không log token.
- [x] `.env.example` có ví dụ đúng.
- [x] Test phase này pass.

## Ghi chú mở

- Có thể cache kết quả parse trong process nếu muốn, nhưng cần cân nhắc test monkeypatch settings.
- Nếu muốn hỗ trợ secret manager sau này, helper parse có thể được thay bằng provider khác mà vẫn trả dict theo contract.
