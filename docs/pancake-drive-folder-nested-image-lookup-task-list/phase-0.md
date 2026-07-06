# Task List Phase 0: Chốt giải pháp Pancake nested Drive folder lookup

## Mục tiêu

Phase 0 chốt phạm vi và contract tổng thể cho flow tìm ảnh trong Google Drive folder con khi Pancake reply có Drive folder link. Flow này xử lý trường hợp AI trả Drive folder link, Google Drive API trả `200`, nhưng folder hiện tại không có file `image/jpeg` hoặc `image/png` nằm trực tiếp bên trong.

Phase này chỉ chốt giải pháp và ranh giới trách nhiệm. Chưa sửa code, chưa đổi service Google Drive, chưa thêm test.

## Quyết định cần chốt

- Chỉ áp dụng nested folder lookup cho flow Pancake.
- BE vẫn là nơi xử lý Drive file/folder link sau khi AI trả response.
- AI/Brain chỉ trả text và Drive file/folder link public, không trả folder con.
- Root folder được tính là tầng 1.
- BE truy cập tối đa 3 tầng.
- Nếu current folder có ảnh JPG/PNG, BE dùng ảnh ở current folder và dừng traversal.
- Nếu current folder không có ảnh nhưng có folder con, BE chọn ngẫu nhiên 1 folder con để đi tiếp.
- BE không đọc hết tất cả folder con.
- BE không thử sibling folder khác nếu nhánh random không có ảnh.
- Nếu Google Drive API trả nhiều page, BE chỉ dùng page đầu tiên.
- Nếu traversal dừng mà không có ảnh, BE trả folder-level error thay vì coi là success im lặng.
- Không fallback gửi raw Drive folder link cho khách trong phase này.

## Ngoài phạm vi Phase 0

- Chưa implement query lấy cả ảnh và folder con.
- Chưa implement random child folder traversal.
- Chưa thay đổi `DriveFolderImageResult`.
- Chưa thay đổi Pancake webhook.
- Chưa thay đổi cache/download/upload Pancake.
- Chưa thêm test.

## File tài liệu liên quan

- [docs/pancake-drive-folder-nested-image-lookup.md](../pancake-drive-folder-nested-image-lookup.md)
- [docs/pancake-drive-link-image-reply.md](../pancake-drive-link-image-reply.md)
- [docs/pancake-drive-image-color-filter.md](../pancake-drive-image-color-filter.md)
- [docs/pancake-drive-folder-nested-image-lookup-task-list/phase-1.md](phase-1.md)
- [docs/pancake-drive-folder-nested-image-lookup-task-list/phase-2.md](phase-2.md)
- [docs/pancake-drive-folder-nested-image-lookup-task-list/phase-3.md](phase-3.md)
- [docs/pancake-drive-folder-nested-image-lookup-task-list/phase-4.md](phase-4.md)
- [docs/pancake-drive-folder-nested-image-lookup-task-list/phase-5.md](phase-5.md)

## Checklist

### 1. Chốt điều kiện kích hoạt

- [x] Xác nhận chỉ chạy nested lookup khi AI reply có Drive folder link.
- [x] Xác nhận Drive file link trực tiếp không bị ảnh hưởng.
- [x] Xác nhận reply không có Drive link không đổi flow text reply hiện tại.
- [x] Xác nhận raw Drive link vẫn bị tách khỏi bot reply text.
- [x] Xác nhận user message đã lưu không bị rewrite để xóa Drive link.

Kết quả mong muốn:
  Nested lookup chỉ là phần mở rộng của Drive folder image reply trong Pancake.

### 2. Chốt giới hạn traversal

- [x] Xác nhận root folder là tầng 1.
- [x] Xác nhận max depth là 3 tầng.
- [x] Xác nhận không gọi tầng 4.
- [x] Xác nhận mỗi tầng chỉ list current folder.
- [x] Xác nhận nếu current folder có ảnh thì dùng ảnh hiện tại, không đi sâu.
- [x] Xác nhận nhiều folder con thì random 1 folder con.
- [x] Xác nhận không thử sibling folder khác.

Kết quả mong muốn:
  Số request Google Drive API được giới hạn rõ ràng và không nổ theo kích thước cây folder.

### 3. Chốt pagination

- [x] Xác nhận chỉ dùng page đầu tiên của Google Drive API response.
- [x] Xác nhận không gọi tiếp bằng `nextPageToken`.
- [x] Xác nhận nếu có `nextPageToken` thì chỉ log/debug `page_truncated`.

Kết quả mong muốn:
  BE không đọc hết folder quá lớn chỉ để random tuyệt đối.

### 4. Chốt fallback và lỗi

- [x] Xác nhận không fallback gửi raw Drive folder link cho khách.
- [x] Xác nhận nếu current folder không có ảnh và không có folder con thì trả `drive_folder_no_images`.
- [x] Xác nhận nếu tầng 3 không có ảnh nhưng vẫn còn folder con chưa được mở thì trả `drive_folder_no_images_within_depth_limit`.
- [x] Xác nhận folder-level error được ghi vào `pancake_drive_reply.errors`.
- [x] Xác nhận text reply vẫn được gửi nếu text hợp lệ.
- [x] Xác nhận không chạy cache/download/upload nếu nested lookup không tạo được `drive_file_urls`.

Kết quả mong muốn:
  Không còn case `images=[]`, `error=null` khi lookup không tìm thấy ảnh có thể gửi.

## Acceptance criteria

- [x] Team chốt nested lookup chỉ áp dụng cho Pancake.
- [x] Team chốt max depth 3 tầng.
- [x] Team chốt random 1 folder con mỗi tầng.
- [x] Team chốt chỉ lấy page đầu.
- [x] Team chốt folder-level error khi traversal không tìm thấy ảnh.
- [x] Team chốt không fallback gửi raw Drive link cho khách.

## Ghi chú mở

- Nếu sau này cần random công bằng trên toàn bộ cây folder, phải đổi scope vì cần đọc nhiều folder/page hơn.
- Nếu sau này cần fallback gửi raw Drive link, nên chốt riêng vì hiện flow đang tách raw Drive link khỏi text trước khi gửi khách.
