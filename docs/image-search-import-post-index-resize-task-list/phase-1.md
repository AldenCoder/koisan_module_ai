# Task List Phase 1: Chốt contract và thứ tự xử lý

## Mục tiêu

Chốt contract cho luồng `POST /api/v1/image-search-import`: ảnh upload vẫn được dùng ở chất lượng index-ready khi upsert Chroma, sau đó mới resize/nén đè ảnh lưu lại cho UI quản lý ảnh.

## Phạm vi

- Chỉ áp dụng cho ảnh import vào image search source.
- Không thay đổi thuật toán Chroma ranking.
- Không thay đổi logic public crop search.
- Không thay đổi `POST /api/v1/image-search/crop-aware`.

## Kết quả mong muốn

- [x] Chốt resize đè ảnh source sau khi upsert Chroma.
- [x] Chốt không tạo thumbnail URL riêng.
- [x] Chốt không đổi request body.
- [x] Chốt không đổi response schema.
- [x] Chốt target thumbnail bắt buộc `<= 100000 bytes`.
- [x] Chốt max side thumbnail khởi điểm `512px`.
- [x] Chốt JPEG quality floor ban đầu `45`, sau đó giảm pixel tiếp nếu cần.
- [x] Chốt không lưu file public lớn hơn `100000 bytes`.

## Ghi chú kỹ thuật

- Không resize xuống thumbnail trước khi gọi `upsert_sources_to_chroma_index_service`.
- Nếu output thumbnail chuyển sang JPEG, metadata phải phản ánh đúng file cuối cùng.
- Nếu tối ưu thumbnail lỗi sau khi upsert Chroma thành công, không được để metadata/response trỏ tới file lớn hơn `100000 bytes`.

## Acceptance Criteria

- Tài liệu mô tả rõ ảnh nào dùng để index và ảnh nào dùng để hiển thị.
- Tài liệu đủ chi tiết để implement mà không cần đoán lại thứ tự xử lý.
