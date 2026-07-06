# Task List Phase 1: Config, model và version comparison

## Mục tiêu

Phase 1 bổ sung config version/limit, field `Conversation.version` và helper parse/compare version tương thích dữ liệu cũ.

Kết quả mong muốn:

- Backend đọc được system version và history limit.
- Conversation cũ thiếu version vẫn load được.
- Conversation mới được insert bằng system version.
- Version comparison có kết quả rõ `older`, `same`, `newer`, `invalid`.

## Đầu vào đã chốt

- Env `AI_CONVERSATION_VERSION`, target hiện tại `1.1`.
- Dùng lại env `PANCAKE_HANDOVER_CONTEXT_MAX_MESSAGES`, default `30`, clamp `1..50`.
- DB field tên `version`.
- Model/schema response dùng `Optional[str]`, default `None`.
- Missing/null/empty DB version dùng baseline `1.0`.
- Không downgrade version.

## Ngoài phạm vi Phase 1

- Không gọi init.
- Không query history.
- Không sửa orchestration webhook.
- Không rollout version `1.1` production.

## File chính dự kiến sửa

- `app/core/config.py`
- `.env.example`
- `app/models/conversations.py`
- `app/api/schemas/conversation.py`
- `app/services/conversation_service.py`
- `app/api/v1/facebook_webhook.py`
- `app/api/v1/pancake_webhook.py`
- `app/services/ai_version_context_service.py` nếu tách helper

## Checklist

### 1. Thêm config

- [x] Thêm `ai_conversation_version: str = "1.1"`.
- [x] Dùng lại `pancake_handover_context_max_messages: int = 30` hiện có.
- [x] Không thêm max-message env mới.
- [x] Document `AI_CONVERSATION_VERSION` và việc reuse limit trong `.env.example`/README nếu phù hợp.
- [x] Không log toàn bộ settings hoặc secrets.

Kết quả mong muốn:
  Deploy code với target `1.1`; conversation cũ thiếu/null/empty version được xem là `1.0` và chỉ upgrade khi có customer message mới.

### 2. Thêm model/schema

- [x] Thêm `version: Optional[str] = None` vào `Conversation`.
- [x] Dữ liệu thiếu field load không lỗi.
- [x] Expose `version: Optional[str]` read-only trong response list/detail.
- [x] Không thêm version vào public create/update request.
- [x] Dùng serializer `getattr(..., None)` cho document cũ.

Kết quả mong muốn:
  Backend và dashboard đọc được version nhưng client không tự ý ghi.

### 3. Parse và compare version

- [x] Chấp nhận `major.minor` và `major.minor.patch`.
- [x] So sánh tuple số đã pad.
- [x] Test `1.10 > 1.9`.
- [x] Missing/null/empty DB version normalize thành `1.0`.
- [x] DB/system version sai format trả reason rõ.
- [x] Higher DB version trả `newer`, không coi là upgrade.

Kết quả mong muốn:
  Không có so sánh lexicographic hoặc downgrade ngoài ý muốn.

### 4. Conversation mới

- [x] Tất cả create path Facebook set system version khi insert.
- [x] Tất cả create path Pancake set system version khi insert.
- [x] CRUD create service có rule rõ cho system-owned version.
- [x] Conversation tạo từ admin echo cũng nhận system version.
- [x] Existing conversation không bị update version chỉ vì được load.

Kết quả mong muốn:
  Chỉ conversation cũ thật sự mới chạy version upgrade.

## Acceptance criteria

- [x] Config đọc đúng env/default.
- [x] Model tương thích document cũ.
- [x] Version compare có unit test đầy đủ.
- [x] Conversation mới nhận system version.
- [x] API response đọc được version.
- [x] Model và response schema chấp nhận `version=None`.

## Ghi chú mở

- Không chạy backfill bắt buộc; runtime migration giữ rollout theo nhu cầu thực tế.
- Nếu dashboard export cần version để theo dõi, thêm cột ở phase rollout hoặc task phụ.
