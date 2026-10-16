# Kịch Bản Đánh Giá Toàn Diện Trợ Lý AI (AI Evaluation Scenarios & Benchmark)

Tài liệu thiết kế các kịch bản kiểm thử và đánh giá chuyên sâu (Test Scenarios & Benchmark Suite) dành cho bộ động cơ **AgriVoice-AI Harness**. Các kịch bản được xây dựng dựa trên các tình huống phức tạp, mâu thuẫn dữ liệu và đặc thù phát ngôn khẩu ngữ có thực trong nông nghiệp thực địa.

---

## Danh Sách 5 Kịch Bản Đánh Giá Phức Tạp

---

### KỊCH BẢN 1: Khẩu Lệnh Phức Hợp Đa Hành Động & Phân Tách Dòng Tiền (Multi-Action Split Voice)

- **Bối cảnh**: Sau một buổi sáng đi chợ và ra đồng, bác nông dân gửi một tin nhắn thoại dài gộp nhiều việc phát sinh cùng lúc.
- **Khẩu lệnh phát ngôn**:
  > *"Sáng nay vừa mua 10 bao phân hữu cơ Quế Lâm hết 3 triệu rưỡi tiền mặt bên tiệm Năm Lúa, xuất luôn 2 bao bón cho vườn bưởi khu B, tiện thể nhờ anh Ba chiều nay ra sửa lại cái van nước tưới khu A bị nứt gãy chảy tràn lan giùm tôi."*
- **Thách thức AI cần giải quyết**:
  1. Nhận diện cấu trúc phức hợp và **tách thành 4 hành động độc lập** có chung nguồn âm thanh.
  2. Bóc tách số tiền khẩu ngữ *"3 triệu rưỡi"* thành số nguyên `3500000` VND.
  3. Ánh xạ *"vườn bưởi khu B"* để gắn đúng `cycle_id` của vụ bưởi.
  4. Nhận diện công việc giao nhanh cho anh Ba và **tạo dưới dạng một Sự cố (`issues`)** với `severity = 'MEDIUM'` thay vì tạo task định kỳ.
- **Kết quả kỳ vọng**:
  - `Event 1`: `inventory_transactions` (INSERT, RECEIPT 10 bao phân Quế Lâm).
  - `Event 2`: `financial_transactions` (INSERT, EXPENSE 3,500,000 VND tiền mặt).
  - `Event 3`: `inventory_transactions` (INSERT, ISSUE -2 bao phân bón cho Khu B).
  - `Event 4`: `issues` (INSERT, OPEN, tiêu đề: *"Sửa van nước tưới khu A bị nứt gãy"*, giao Anh Ba).

---

### KỊCH BẢN 2: Nhận Con Giống Khởi Tạo Vụ Mùa & Kiểm Tra Chống Trùng Lặp (Seedling Inception & Deduplication)

- **Bối cảnh**: Trang trại nhập gà con về nuôi và người dùng thông báo 2 lần lệch thời gian.
- **Diễn biến hai lượt thoại**:
  - **Lượt 1 (Nhận giống khởi tạo vụ)**:
    > *"Vừa nhận 200 con gà giống Ri lai từ trại giống Ba Vì giao tới Chuồng 1 giá 3 triệu hẹn tháng sau trả, bắt đầu lứa nuôi từ hôm nay."*
    - **Thách thức**: AI kiểm tra `search_production_cycle` thấy Chuồng 1 đang trống $\rightarrow$ Tự động khởi tạo chu kỳ mùa vụ mới `production_cycles`, ghi nhận nợ phải trả `debt_records` 3 triệu cho trại Ba Vì, và tạo phiếu nhập kho 200 con gà giống.
  - **Lượt 2 (Thông báo bổ sung cùng lứa - Kiểm tra trùng lặp)**:
    > *"Thả thêm 50 con gà giống Ri lai vào Chuồng 1 luôn nghen."*
    - **Thách thức**: AI gọi `search_production_cycle(zone_id='ZONE_CHUONG_1', status='ACTIVE')`, phát hiện Chuồng 1 **đang có lứa gà Ri lai vừa tạo**.
    - **Hành vi xử lý thông minh**: AI **tuyệt đối không tạo thêm vụ mùa mới** (tránh nhân đôi lịch trình 90 ngày), mà tự động cộng dồn 50 con giống vào lứa nuôi hiện hữu và thông báo giải thích rõ ràng cho nông dân.

---

### KỊCH BẢN 3: Trao Đổi Hàng Hóa Trực Tiếp Phi Tiền Tệ Có Bù Tiền Mặt (Barter Exchange with Cash Offset)

- **Bối cảnh**: Mô hình kinh tế tuần hoàn nông thôn, nông dân lấy phụ phẩm đổi lấy giống cây trồng của hàng xóm.
- **Khẩu lệnh phát ngôn**:
  > *"Đem 2 xe phân chuồng hoai mục đổi lấy 50 cây giống cam xoàn của chú Tư, bên mình phải bù thêm 500 ngàn tiền mặt cho chú."*
- **Thách thức AI cần giải quyết**:
  1. Nhận diện cấu trúc giao dịch hàng đổi hàng (Barter trade).
  2. Bóc tách đồng bộ 2 vế:
     - Vế xuất: 2 xe phân chuồng (`give_quantity = 2.0`).
     - Vế nhận: 50 cây cam giống (`receive_quantity = 50.0`).
  3. Xử lý khoản tiền chênh lệch bù trừ $\Delta_{\text{cash}} = 500,000$ VND: Tự động kích hoạt phiếu chi tiền mặt `financial_transactions` mà không làm sai lệch giá trị quy ước của vật tư trong kho.
- **Kết quả kỳ vọng**:
  - Bản ghi `barter_transactions` lưu cặp đối ứng.
  - 1 phiếu xuất kho phân chuồng (`ISSUE`) + 1 phiếu nhập kho cây cam giống (`RECEIPT`).
  - 1 phiếu chi tiền mặt 500,000 VND.

---

### KỊCH BẢN 4: Vòng Đời Vận Hành SOP, Tự Trừ Kho & Nghiệm Thu Đóng Sự Cố (SOP & Issue Lifecycle)

- **Bối cảnh**: Tiến trình làm việc trong ngày của nhân công và chủ vườn.
- **Diễn biến ba lượt thoại**:
  - **Lượt 1 (Hoàn thành task định kỳ kèm vật tư tiêu hao)**:
    > *"Anh Ba đã bón phân lót dưa lưới cữ sáng nay xong rồi, dùng hết 2 bao vôi bột."*
    - AI gọi `complete_running_task(material_category_id=VôiBột, quantity_used=2.0)`.
    - Hệ thống chuyển task sang `DONE` và **tự động sinh phiếu xuất kho trừ 2 bao vôi bột** mà nhân công không cần nói lệnh xuất kho riêng.
  - **Lượt 2 (Cập nhật tiến độ sự cố)**:
    > *"Cập nhật vụ van nước rỉ khu A: nãy anh Ba đã quấn băng keo non chống rỉ tạm thời rồi nghen."*
    - AI gọi `manage_issue(action='IN_PROGRESS', notes='...')`, nối thêm ghi chú vào sự cố.
  - **Lượt 3 (Chủ trang trại nghiệm thu đóng sự cố)**:
    > *"Van nước khu A đã thay phụ kiện mới chạy êm rồi, nghiệm thu đóng sự cố giùm tôi."*
    - AI gọi `manage_issue(action='CLOSED', resolution_notes='...')`, đóng sự cố và ghi nhận mốc `closed_at`.

---

### KỊCH BẢN 5: Tra Cứu Tức Thì Qua Lớp Phủ Ảo Thời Gian Thực (Real-time Virtual Overlay Q&A)

- **Bối cảnh**: Người làm vườn hỏi thăm tình hình trang trại vào giữa ngày trong khi Chủ vườn chưa bấm duyệt các sự kiện buổi sáng.
- **Câu hỏi phát ngôn**:
  > *"Kiểm tra giùm tôi sáng giờ đã xuất những vật tư gì rồi, và khu A có sự cố gì chưa xử lý không?"*
- **Thách thức AI cần giải quyết**:
  1. Xác định đây là câu hỏi tra cứu đọc dữ liệu thuần túy (Read-only Q&A) $\implies$ **Tuyệt đối không tạo bản ghi chờ duyệt trong `pending_events`**.
  2. Kích hoạt công cụ `get_data_with_pending_applied` và `search_issue(zone_id='ZONE_A')`.
  3. Mô phỏng dữ liệu hợp nhất (Committed Data + Pending Events) trên RAM.
  4. Trả lời ngay bằng tiếng Việt tự nhiên, dân dã, thông báo rõ vật tư nào đã chốt sổ và vật tư nào đang chờ chủ duyệt.
