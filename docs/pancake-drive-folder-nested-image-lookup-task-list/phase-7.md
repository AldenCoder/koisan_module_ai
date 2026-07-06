# Task List Phase 7: Color-diverse multi-folder selection

## Mục tiêu

Phase 7 thay rule random một folder con bằng rule chọn ảnh đa màu có kiểm soát cho Pancake nested Drive folder lookup.

Kết quả mong muốn:

- Nếu root folder có nhiều folder con mang màu, `BE` mở các folder màu đó trong giới hạn đã cấu hình thay vì random một folder.
- `BE` gửi ảnh đại diện cho các màu tự detect được từ Drive metadata, không phụ thuộc vào câu AI liệt kê màu.
- Ảnh trong folder màu kế thừa màu folder nếu tên file không có màu.
- Ảnh gửi ra vẫn bị giới hạn bởi `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- Nếu chưa đủ limit sau khi cover màu, `BE` fill random ảnh còn lại.
- Câu hỏi dạng `màu nào` không được tạo `requested_color`.

## Đầu vào đã chốt

- Chỉ áp dụng cho Drive folder link trong flow Pancake.
- Drive file link trực tiếp giữ nguyên behavior hiện tại.
- `Mẫu này có 3 màu: Be, Xanh biển, Tím` là text tư vấn, không phải filter bắt buộc.
- Nguồn quyết định màu chính là tên folder và tên file trong Drive.
- Folder màu ví dụ hợp lệ: `be`, `xanh`, `tím`, `S2650543 BE`, `S2650543 HỒNG`, `S2650543 ĐEN`.
- File color cụ thể hơn folder color. Nếu file có `drive_file_color`, ưu tiên màu file; nếu không, dùng màu folder kế thừa.
- Nếu customer/AI thật sự yêu cầu một màu qua trigger hợp lệ, color filter hiện có vẫn được giữ cho candidate matching trước khi fallback.
- Max depth vẫn clamp tối đa 3.
- Mỗi folder vẫn chỉ đọc page đầu tiên.
- Không crawl toàn bộ cây Drive không màu.

## Ngoài phạm vi Phase 7

- Không dùng computer vision để nhận diện màu trong ảnh.
- Không đọc page thứ hai trở đi.
- Không mở folder không màu hàng loạt.
- Không đổi upload/cache/send ảnh Pancake sau khi đã chọn được `drive_file_id`.
- Không yêu cầu AI trả JSON hoặc field màu có cấu trúc.
- Không đảm bảo cover màu nằm ở page sau hoặc folder không màu chưa được mở.

## File chính dự kiến sửa

- [app/services/pancake_drive_image_color_service.py](../../app/services/pancake_drive_image_color_service.py)
- [app/services/google_drive_image_service.py](../../app/services/google_drive_image_service.py)
- [app/api/v1/pancake_webhook.py](../../app/api/v1/pancake_webhook.py)
- [app/core/config.py](../../app/core/config.py), nếu cần config rollback/cap.
- [.env.example](../../.env.example), nếu thêm config mới.
- [tests/test_pancake_drive_image_color_service.py](../../tests/test_pancake_drive_image_color_service.py)
- [tests/test_google_drive_image_service.py](../../tests/test_google_drive_image_service.py)
- [tests/test_pancake_webhook.py](../../tests/test_pancake_webhook.py)

Nếu selection helper bắt đầu phình to, tách thêm:

- `app/services/pancake_drive_image_selection_service.py`
- `tests/test_pancake_drive_image_selection_service.py`

## Checklist

### 1. Fix parser câu hỏi `màu nào`

- [x] Thêm regression test cho câu `Chị thích màu nào để em check size/còn hàng cho mình ạ?` kèm Drive link.
- [x] Test phải assert `requested_color is None`, `requested_color_phrases == []`, `requested_color_terms == []`.
- [x] Sửa `extract_requested_color_phrases` để nếu raw phrase sau trigger bắt đầu bằng `nào`, `nao`, `gì`, `gi` thì bỏ qua toàn bộ trigger trước khi split bằng `,`, `/`, `và`.
- [x] Giữ behavior hợp lệ: `Mẫu có màu Đỏ đô, Kem ạ` vẫn parse `["Đỏ đô", "Kem"]`.
- [x] Giữ behavior hợp lệ: `Em gửi chị ảnh màu Hồng sen ạ` vẫn parse `["Hồng sen"]`.

Kết quả mong muốn:
  Parser không còn tạo màu giả `conhangchominh` từ câu hỏi chọn màu.

### 2. Chuẩn hóa màu hiệu lực cho image candidate

- [x] Thêm helper trả về color key hiệu lực cho ảnh: `drive_file_color` nếu có, nếu không thì inherited folder color.
- [x] Đảm bảo ảnh trong folder `S2650543 BE` có `drive_file_color="be"` khi file không có token màu.
- [x] Nếu filename có màu khác folder, metadata cuối cùng dùng màu filename.
- [x] Giữ metadata `drive_file_name`, `drive_file_color` để debug/cache.

Kết quả mong muốn:
  Selection layer group được ảnh theo màu dù file đặt tên chung như `lookbook_1.jpg`.

### 3. Scan nhiều folder màu tại root

- [x] Khi root có child folders có `drive_folder_color`, chọn chiến lược `color_diverse`.
- [x] Bỏ random một child folder trong case này.
- [x] Mở lần lượt các folder màu trong giới hạn cap.
- [x] Mỗi folder màu chỉ đọc page đầu tiên.
- [x] Nếu folder màu có ảnh trực tiếp, lấy ảnh ở folder đó và không đi sâu thêm vào folder con không cần thiết.
- [ ] Nếu folder màu không có ảnh nhưng có folder con và còn depth, có thể dùng traversal một nhánh hiện có trong phạm vi folder màu đó.
- [x] Folder màu lookup lỗi hoặc rỗng thì bỏ qua, log lỗi cấp folder màu, không fail toàn bộ root.
- [x] `visited_folder_ids` gồm root và các folder màu đã mở.
- [x] `selected_child_folder_ids` gồm các folder màu có ảnh được đưa vào candidate.

Kết quả mong muốn:
  Root có `be`, `xanh`, `tím` thì `BE` mở cả 3 và có candidate cho cả 3 màu nếu Drive có ảnh.

### 4. Root image fallback và no-color fallback

- [x] Nếu root có folder màu, ảnh root được đưa vào sau ảnh folder màu để folder màu được ưu tiên.
- [x] Ảnh root vẫn được đưa vào pool fill random pass 2.
- [x] Nếu không có folder màu, dùng root images làm candidate chính.
- [x] Nếu root images có màu trong filename, group theo màu filename.
- [x] Nếu root images không có màu, vẫn có thể fill random theo limit.
- [x] Không mở folder con không màu hàng loạt chỉ để fill.

Kết quả mong muốn:
  Folder màu được ưu tiên, nhưng root images vẫn giúp đủ số ảnh khi thiếu candidate.

### 5. Selection pass 1 và pass 2

- [x] Pass 1 group candidate theo màu hiệu lực.
- [x] Pass 1 chọn ngẫu nhiên 1 ảnh mỗi màu, không vượt image limit.
- [x] Nếu số màu nhiều hơn limit, chọn tối đa limit màu theo thứ tự Drive response sau khi bỏ trùng.
- [x] Pass 2 chọn ngẫu nhiên thêm từ ảnh còn lại để đủ image limit.
- [x] Không chọn trùng `drive_file_id`.
- [x] Nếu có 3 ảnh xanh và 4 ảnh đỏ với limit 5, kết quả có 1 xanh + 1 đỏ + 3 ảnh random còn lại.
- [x] Nếu có 3 folder màu và limit 5, kết quả có ít nhất 1 ảnh mỗi folder màu nếu mỗi folder có ảnh.

Kết quả mong muốn:
  Ảnh gửi ra đa dạng màu trước, số slot còn lại dùng để gửi thêm ảnh random.

### 6. Tích hợp Pancake prepare reply

- [x] `PreparedPancakeDriveReply.drive_file_urls` nhận ảnh sau color-diverse selection.
- [x] `selected_drive_file_ids` phản ánh đúng ảnh đã chọn.
- [x] `drive_file_metadata` lưu `drive_file_color` đã inherit từ folder màu.
- [x] `require_color_metadata` vẫn bật khi có color filter hoặc có metadata màu từ Drive.
- [x] Flow gửi text trước, gửi ảnh sau không đổi.
- [x] Nếu lookup folder màu không có ảnh nhưng text hợp lệ, vẫn gửi text.

Kết quả mong muốn:
  Phía Pancake upload/send không cần biết ảnh đến từ nhiều folder màu.

### 7. Config và rollback

- [x] Thêm config strategy nếu cần rollback nhanh, ví dụ `PANCAKE_DRIVE_IMAGE_SELECTION_STRATEGY=color_diverse`.
- [x] Giá trị rollback: `single_branch_random`.
- [x] Thêm cap số folder màu mở mỗi root nếu cần, ví dụ `PANCAKE_DRIVE_COLOR_FOLDER_MAX_COUNT=5`.
- [ ] Thêm concurrency nếu triển khai concurrent, ví dụ `PANCAKE_DRIVE_COLOR_FOLDER_LOOKUP_CONCURRENCY=3`.
- [x] Cập nhật `.env.example` cho config mới.

Kết quả mong muốn:
  Có đường rollback hoặc giới hạn rõ ràng nếu production gặp latency/quota Drive API.

### 8. Logging và metadata debug

- [x] Log số folder màu detect được tại root.
- [x] Log các folder màu đã mở.
- [x] Log folder màu rỗng và trạng thái scan bị truncate.
- [x] Log màu đã cover trong pass 1.
- [x] Log số ảnh fill random ở pass 2.
- [x] Log `color_folder_scan_truncated=true` nếu cap làm bỏ bớt folder màu.
- [x] Không log Google Drive API key.

Kết quả mong muốn:
  Debug được vì sao gửi đủ/thiếu màu mà không cần đọc lại toàn bộ Drive.

### 9. Test parser màu

- [x] Test `màu nào ... size/còn hàng` không tạo requested color.
- [x] Test `Mẫu này có 3 màu: Be, Xanh biển, Tím` không tạo requested color vì trigger bị dừng bởi dấu `:`.
- [x] Test `màu Đỏ đô, Kem` vẫn tạo 2 phrase.
- [x] Test `màu Hồng sen` vẫn tạo dynamic phrase.

Kết quả mong muốn:
  Parser chỉ filter khi text thật sự yêu cầu gửi ảnh theo màu.

### 10. Test Google Drive selection

- [x] Root có folder `be`, `xanh`, `tím`, mỗi folder có ảnh: mở cả 3 folder và trả ít nhất 1 ảnh mỗi màu.
- [x] Root có folder màu và ảnh root: chọn folder màu trước, ảnh root fill sau nếu còn slot.
- [x] Folder màu có ảnh không màu filename: ảnh inherit màu folder.
- [x] File có màu khác folder: file color override folder color.
- [x] Folder màu rỗng không fail toàn bộ lookup.
- [x] Không có folder màu: root images được group theo filename color.
- [x] Limit 5, 3 ảnh xanh + 4 ảnh đỏ: kết quả có 1 xanh + 1 đỏ + 3 ảnh còn lại.
- [x] Số màu nhiều hơn limit: chỉ chọn tối đa limit màu, không vượt limit.
- [x] `nextPageToken` vẫn không gọi page 2.
- [x] Max depth vẫn không vượt 3.

Kết quả mong muốn:
  Nested Drive lookup trả candidate đa màu đúng rule Phase 7.

### 11. Test Pancake integration

- [x] AI reply liệt kê `Mẫu này có 3 màu: Be, Xanh biển, Tím` kèm Drive folder không tạo `requested_color`.
- [x] Với Drive root có 3 folder màu, `drive_file_ids` có ảnh cả 3 màu trong giới hạn `PANCAKE_INBOX_IMAGE_MAX_COUNT`.
- [x] `drive_file_metadata` có `drive_file_color` cho ảnh inherit từ folder.
- [x] `ensure_local_images` nhận đúng list Drive file view URL đã chọn.
- [x] Nếu một folder màu rỗng, vẫn cache/upload các ảnh còn lại.

Kết quả mong muốn:
  User nhận ảnh đa màu khi BE tìm thấy trong Drive, không bị phụ thuộc text màu của AI.

### 12. Verify và rollout

- [x] Chạy test parser màu.
- [x] Chạy test Google Drive nested lookup.
- [x] Chạy test Pancake webhook liên quan.
- [x] Chạy `PYTHONPATH=. ./.venv/bin/pytest -q`.
- [x] Cập nhật tài liệu chính từ proposal sang behavior đã implement nếu tất cả test pass.

Kết quả mong muốn:
  Phase 7 có test regression đầy đủ và tài liệu phản ánh đúng behavior production.

## Acceptance criteria

- [x] Không còn `requested_color=conhangchominh` từ câu hỏi `màu nào`.
- [x] Root có nhiều folder màu thì không random một folder nữa.
- [x] Root có `be`, `xanh`, `tím` thì mở cả 3 folder trong giới hạn và gửi ảnh cả 3 màu nếu đủ ảnh.
- [x] Root có folder màu và ảnh root thì folder màu được dùng trước, ảnh root fill sau.
- [x] Nếu không có folder màu thì root images vẫn được chọn theo rule đa màu từ filename.
- [x] Mỗi màu tìm thấy có tối đa 1 ảnh ở pass 1 trước khi fill random.
- [x] Tổng ảnh không vượt `PANCAKE_INBOX_IMAGE_MAX_COUNT` / `PANCAKE_COMMENT_IMAGE_MAX_COUNT`.
- [x] Folder màu rỗng/lỗi không làm mất text reply hoặc ảnh từ folder màu khác.
- [x] Không đọc page sau và không vượt depth 3.
- [x] Test mới pass và regression test pass.

## Ghi chú mở

- Nên ưu tiên implement bằng helper nhỏ để test selection thuần, tránh nhồi thêm quá nhiều nhánh vào `_lookup_nested_folder_images`.
- Nếu production có quá nhiều folder màu trong một root, cần bật cap để tránh tăng latency Google Drive.
- Nếu cần phân biệt `xanh biển` với `xanh` tốt hơn, nên chuẩn hóa naming folder/file theo phrase cụ thể thay vì chỉ dùng folder `xanh`.
- Phase 7 vẫn không giải quyết ảnh đúng màu nằm ở page 2 hoặc trong folder không màu sâu hơn.
