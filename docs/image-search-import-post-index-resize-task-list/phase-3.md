# Task List Phase 3: Test và rollout

## Mục tiêu

Bổ sung test và checklist rollout cho thay đổi resize ảnh sau import.

## Test cần có

- [x] Test ảnh lớn được resize index-ready theo `CLIP_CROP_AWARE_MAX_SIDE` trước khi upsert.
- [x] Test Chroma upsert nhận đúng path ảnh index-ready.
- [x] Test sau upsert file cuối cùng luôn nhỏ hơn hoặc bằng `100000 bytes`.
- [x] Test metadata sau import phản ánh đúng file cuối cùng.
- [x] Test PNG có alpha được ghép nền trước khi chuyển JPEG.
- [x] Test upsert Chroma lỗi thì rollback metadata và xóa file mới.
- [x] Test tối ưu thumbnail lỗi thì không để lại file public lớn hơn target.

## Rollout checklist

- [ ] Backup hoặc snapshot volume `data` trước khi bật logic mới trên production.
- [ ] Import thử một SKU mới và kiểm tra Chroma search.
- [ ] Kiểm tra ảnh trong màn quản lý tải đúng URL.
- [ ] Kiểm tra dung lượng file trong `data/source_images`.

## Acceptance Criteria

- [x] Targeted tests pass với `tests/test_image_search_source_service.py`.
- [x] Full suite `pytest -q` pass.
- [x] Docs vận hành được cập nhật theo implementation.
