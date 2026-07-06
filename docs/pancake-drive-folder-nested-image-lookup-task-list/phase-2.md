# Task List Phase 2: Traversal một nhánh tối đa 3 tầng

## Mục tiêu

Phase 2 implement traversal Drive folder theo một nhánh ngẫu nhiên. Khi current folder không có ảnh nhưng có folder con, BE chọn ngẫu nhiên một folder con để đi tiếp. Traversal dừng khi tìm thấy ảnh, không còn folder con, hoặc chạm giới hạn 3 tầng.

Kết quả mong muốn:

- Root folder có ảnh thì return ảnh ngay.
- Root folder không có ảnh nhưng child folder có ảnh thì return ảnh child.
- Tối đa 3 request Google Drive API cho một root folder link.
- Nếu traversal không tìm thấy ảnh thì trả folder-level error rõ ràng.

## Đầu vào đã chốt

- Root folder là tầng 1.
- Max depth là 3 tầng.
- Mỗi tầng chỉ list current folder.
- Mỗi tầng chỉ dùng page đầu.
- Nếu có nhiều folder con thì random 1 folder con.
- Không thử sibling folder khác.

## Ngoài phạm vi Phase 2

- Không sửa Pancake send message.
- Không cache/download/upload ảnh.
- Không thay đổi color filter.
- Không fallback gửi raw Drive folder link.

## File chính dự kiến sửa

- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)
- `app/services/google_drive_folder_traversal_service.py`, nếu tách helper riêng.
- `tests/test_google_drive_folder_traversal_service.py`, nếu tách helper riêng.

## Checklist

### 1. Implement traversal loop

- [x] Parse `root_folder_id` từ Drive folder URL như hiện tại.
- [x] Khởi tạo `current_folder_id=root_folder_id`.
- [x] Khởi tạo `visited_folder_ids=[]`.
- [x] Khởi tạo `selected_child_folder_ids=[]`.
- [x] Lặp depth từ 1 đến 3.
- [x] Mỗi depth gọi helper fetch first page children.

Kết quả mong muốn:
  Traversal có state rõ ràng để debug và test.

### 2. Dừng khi tìm thấy ảnh

- [x] Nếu current folder có ảnh hợp lệ, return `DriveFolderImageResult.images`.
- [x] Ghi `lookup_depth` là depth tìm thấy ảnh.
- [x] Giữ `visited_folder_ids`.
- [x] Giữ `selected_child_folder_ids`.
- [x] Không đi sâu thêm nếu current folder vừa có ảnh vừa có folder con.

Kết quả mong muốn:
  Hành vi folder có ảnh trực tiếp giữ nhanh và không tăng request.

### 3. Chọn ngẫu nhiên folder con

- [x] Nếu current folder không có ảnh, lấy danh sách child folders hợp lệ.
- [x] Nếu không có child folder, return error `drive_folder_no_images`.
- [x] Nếu đang ở depth 3 và còn child folder, return error `drive_folder_no_images_within_depth_limit`.
- [x] Nếu còn depth, random 1 child folder để đi tiếp.
- [x] Ghi child folder đã chọn vào `selected_child_folder_ids`.
- [x] Không thử child folder khác nếu nhánh random không có ảnh.

Kết quả mong muốn:
  BE chỉ mở một nhánh, số request được giới hạn.

### 4. Metadata result và log

- [x] Thêm hoặc log `lookup_depth`.
- [x] Thêm hoặc log `visited_folder_ids`.
- [x] Thêm hoặc log `selected_child_folder_ids`.
- [x] Thêm hoặc log `page_truncated`.
- [x] Thêm hoặc log `child_folder_count`.
- [x] Đảm bảo metadata optional không làm vỡ caller hiện tại.

Kết quả mong muốn:
  Khi không gửi ảnh, log/result đủ dữ liệu để biết BE đã đi qua nhánh nào.

### 5. Test phase 2

- [x] Test root folder có ảnh trực tiếp chỉ gọi 1 request.
- [x] Test ảnh nằm ở child folder tầng 2 gọi 2 request.
- [x] Test ảnh nằm ở grandchild folder tầng 3 gọi 3 request.
- [x] Test không gọi tầng 4.
- [x] Test nhiều child folders chỉ chọn 1 folder con.
- [x] Test không thử sibling folder khác.
- [x] Test `drive_folder_no_images`.
- [x] Test `drive_folder_no_images_within_depth_limit`.

## Acceptance criteria

- [x] Traversal dừng khi tìm thấy ảnh.
- [x] Traversal không vượt quá 3 tầng.
- [x] Traversal chỉ random 1 folder con mỗi tầng.
- [x] Traversal trả error mới khi không tìm thấy ảnh.
- [x] Unit test phase này pass.

## Ghi chú mở

- Để test random ổn định, nên monkeypatch `random.choice` hoặc inject chooser nội bộ.
- Nếu sau rollout random một nhánh gây miss ảnh quá nhiều, cần phase riêng để scan nhiều nhánh có giới hạn.
