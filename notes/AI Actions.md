# Đặc Tả Các Hành Động AI & Cơ Chế Xử Lý Ngữ Nghĩa (AI Actions & Semantic Resolution Engine)

Tài liệu đặc tả toàn diện bộ hành động trí tuệ nhân tạo (AI Actions Specification) cho hệ thống **AgriVoice-AI**. Tài liệu hướng dẫn cách mô hình ngôn ngữ lớn (LLM / Gemini) lắng nghe, giải mã khẩu lệnh giọng nói dân dã của nhà nông, tự động bù đắp dữ liệu thiếu sót (Fuzzy Data Enrichment), sinh các sự kiện chờ duyệt có cấu trúc vào vùng đệm `pending_events` và phản hồi xác nhận thân thiện qua Telegram.

---

## 1. Nguyên Tắc Xử Lý Ngôn Ngữ Nông Nghiệp Cốt Lõi (Core NLP Principles)

```
[Khẩu lệnh Voice thô của Nông dân]
                 │
                 ▼
     [1. Bóc băng nguyên văn (Transcript)]
                 │
                 ▼
     [2. Phân loại Ý định (Intent Classification)]
                 │
                 ▼
     [3. Bóc tách Thực thể & Rà soát Từ điển (Entity Extraction & Dictionary Grounding)]
         - Tra cứu convenient_names trong dictionary (vật tư, giống, kho)
         - Bù đắp giá trị mặc định / Suy đoán an toàn (warehouse nullable)
                 │
                 ▼
     [4. Đóng gói Event In-Flight (Staging Payload)]
         - target_table, action_type, payload_json, summary_text
                 │
                 ▼
     [5. Phản hồi xác nhận & Nhắc thông tin còn thiếu qua Telegram]
```

1. **Nguyên tắc "Khoan dung & Làm giàu" (Tolerance & Enrichment)**:
   - Nông dân nói thiếu thông tin (quên giá, không nói kho, nói đơn vị dân dã) là trạng thái bình thường. AI **không bao giờ từ chối xử lý** hoặc đòi hỏi người dùng phải đọc lại câu lệnh chuẩn như lập trình viên.
   - AI tự động làm giàu thông tin: quy đổi đơn vị qua `category_unit_conversions`, để trống vị trí kho (`warehouse_id = NULL`) để chống crash, gán cờ `is_price_estimated = 1` nếu tự suy đoán giá.
2. **Quy tắc phân loại công việc thực địa**:
   - **Công việc định kỳ lặp lại theo quy trình mẫu (SOP)**: Do hệ thống tự động sinh trong bảng `running_tasks` khi bắt đầu vụ mùa.
   - **Công việc đột xuất, giao việc nhanh (Ad-hoc Tasks)**: **Được khởi tạo dưới dạng một Sự cố / Hạng mục sự vụ (`issues`)** để theo dõi và xử lý dứt điểm, không trộn lẫn vào lịch trình định kỳ của `running_tasks`.
3. **Kích hoạt Vụ mùa tự động hai kênh (Dual-Trigger Production Cycle)**:
   - *Kênh 1: Khẩu lệnh trực tiếp* (*"Bắt đầu vụ dưa lưới Tết...", "Thả lứa gà 200 con..."*).
   - *Kênh 2: Kích hoạt theo sự kiện nhận giống* (Khi ghi nhận nhập kho con giống hoặc cây giống, AI tự động nhận diện và đề xuất/khởi tạo chu kỳ mùa vụ mới gắn với khu vực tiếp nhận).
4. **Vòng đời cập nhật sự cố đa bước**:
   - Hỗ trợ đầy đủ các thao tác: Báo cáo sự cố mới $\rightarrow$ Bổ sung ghi chú/tiến độ hiện trường (`notes`) $\rightarrow$ Chủ vườn nghiệm thu và đóng sự cố (`closed_at`, `resolution_notes`).
5. **Khẩu lệnh Đa hành động (Multi-Action Voice Ingestion)**:
   - Một câu nói có thể chứa nhiều ý định độc lập (ví dụ: vừa xuất kho phân, vừa báo máy bơm hỏng). AI có trách nhiệm tách thành nhiều bản ghi `pending_events` độc lập có cùng nguồn gốc âm thanh.
6. **Phân tách rạch ròi: Hành động ghi (Staged Action) vs Hành động đọc (Read-only Query)**:
   - Các hành động làm thay đổi dữ liệu trang trại $\implies$ Luôn tạo sự kiện chờ duyệt (`status = 'PENDING'`).
   - Các câu hỏi tra cứu, thống kê $\implies$ Gọi trực tiếp công cụ `search_*` kết hợp Lớp phủ ảo `get_data_with_pending_applied` và trả lời tức thì.

---

## 2. Danh Mục Các Hành Động AI Chi Tiết (Comprehensive Action Catalog)

---

### ACTION 1: Nhập Kho Vật Tư / Nông Sản (`RECORD_INVENTORY_RECEIPT`)

#### 1. Quy tắc nhận diện ngữ nghĩa (4 yếu tố xác nhận nhập kho)
Một phát ngôn được kết luận là **Nhập kho** khi thỏa mãn:
1. **Đối tượng**: Vật tư nông nghiệp (phân, giống, thuốc, thức ăn) hoặc nông sản.
2. **Nguồn gốc ban đầu**: Từ bên ngoài trang trại (đại lý, nhà cung cấp, đối tác).
3. **Điểm đến**: Thuộc phạm vi kiểm soát của trang trại (kho, chòi, vườn, hoặc trạng thái sở hữu của trang trại).
4. **Hành vi**: Làm tăng lượng vật tư trong trang trại (`quantity_change > 0`).
- **Từ khóa khẩu ngữ**: *"vừa mua"*, *"nhập về"*, *"chở về ... bao"*, *"tiệm giao tới"*, *"lấy về ... chai"*, *"đại lý giao qua"*.
- **Ví dụ thực tế**:
  - *"Vừa mua 20 bao phân gà của đại lý Năm Lúa hết 4 triệu tiền mặt."*
  - *"Đại lý mới chở qua 5 can thuốc diệt cỏ."*

#### 2. Cơ chế suy diễn & Làm giàu dữ liệu
- **Đối tượng hàng hóa**:
  - Đối chiếu tên đọc với trường `convenient_names` trong bảng `dictionary`.
  - Nếu mặt hàng chưa từng tồn tại: AI tạo thêm một event phụ đi kèm để thêm mục mới vào `dictionary` với `root_path` phù hợp (ví dụ: `/vat-tu/phan-bon/`).
- **Đơn vị tính**:
  - Nếu đọc đơn vị địa phương (*bao, can, thùng, chai*): AI tra cứu `category_unit_conversions` để lấy `factor_to_base` quy đổi về đơn vị chuẩn kg, lít.
- **Vị trí kho (Nullable chống crash)**:
  - Nếu nông dân không nói cất ở kho nào $\implies$ Gán `warehouse_id = NULL`. Hệ thống vẫn lưu thành công an toàn, không bị crash.
  - Nếu có nói (*"để ngoài chòi khu A"*), AI map với điểm lưu trữ trong `dictionary`.
- **Kích hoạt tự động vụ mùa mới (Automatic Cycle Inception)**:
  - Nếu vật tư nhập về là **con giống hoặc cây giống** (ví dụ: *200 con gà giống Ri lai, 50 cây cam giống*), AI tự động nhận diện và sinh thêm đề xuất khởi tạo vụ mùa mới (`START_PRODUCTION_CYCLE`) gắn với khu vực dự kiến thả/trồng.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "inventory_transactions",
  "action_type": "INSERT",
  "payload_json": {
    "item_name": "Phân gà hoai mục",
    "category_id": 14,
    "warehouse_id": null,
    "transaction_type": "RECEIPT",
    "quantity_change": 20.0,
    "unit_id": 3,
    "unit_price_vnd": 200000,
    "supplier_id": 2,
    "status": "POSTED"
  },
  "summary_text": "Nhập 20 bao phân gà (Đại lý Năm Lúa)"
}
```

---

### ACTION 2: Xuất Kho Bón Cây / Bán Hàng / Xuất Dùng (`RECORD_INVENTORY_ISSUE`)

#### 1. Quy tắc nhận diện ngữ nghĩa (4 yếu tố xác nhận xuất kho)
Một phát ngôn được kết luận là **Xuất kho** khi thỏa mãn:
1. **Đối tượng**: Vật tư đang có sẵn trong trang trại.
2. **Nơi ban đầu**: Thuộc phạm vi kiểm soát của trang trại (trong kho, trong chòi, trong vườn).
3. **Nơi sau đó**: Đã đem ra bón, phun xịt ngoài ruộng, hoặc giao bán cho thương lái.
4. **Hành vi**: Làm giảm lượng vật chất sở hữu trong trang trại (`quantity_change < 0`).
- **Từ khóa khẩu ngữ**: *"nãy bón"*, *"lấy ra ... bao"*, *"xịt hết ... bình"*, *"xuất cho khu A"*, *"bán ... tấn"*, *"cắt đem giao"*.
- **Ví dụ thực tế**:
  - *"Sáng nay lấy 5 bao NPK bón cho vườn bưởi khu B."*
  - *"Nãy bán 3 tấn ngô hạt cho thương lái chú Ba."*

#### 2. Cơ chế suy diễn & Dung sai tồn âm
- **Liên kết Vụ mùa (`cycle_id`)**:
  - Nếu nông dân nói bón cho vườn nào/khu nào (*"vườn bưởi khu B"*), AI tự động tìm chu kỳ canh tác đang hoạt động tại khu B để gắn `cycle_id`, phục vụ tự động hạch toán chi phí vật tư cho vụ mùa đó.
- **Tồn kho âm an toàn (Negative Stock Tolerance)**:
  - Nếu trong kho chưa có log nhập hoặc số dư không đủ 5 bao, hệ thống vẫn chấp nhận ghi nhận xuất kho bình thường, tự động đưa lô về trạng thái cảnh báo `NEGATIVE_ALERT` mà không chặn đứng công việc ngoài đồng.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "inventory_transactions",
  "action_type": "INSERT",
  "payload_json": {
    "item_name": "Phân NPK 20-20-15",
    "category_id": 8,
    "warehouse_id": null,
    "cycle_id": 4,
    "transaction_type": "ISSUE",
    "quantity_change": -5.0,
    "unit_id": 1,
    "status": "POSTED"
  },
  "summary_text": "Xuất 5 bao NPK bón Vườn Bưởi Khu B"
}
```

---

### ACTION 3: Báo Cáo Hoàn Thành Công Việc Định Kỳ & Tự Trừ Kho (`COMPLETE_TASK`)

#### 1. Quy tắc nhận diện
- Phát ngôn báo cáo một công việc định kỳ trong lịch trình **đã làm xong**, có thể kèm hoặc không kèm lượng vật tư đã tiêu thụ.
- **Từ khóa nhận diện**: *"làm xong rồi"*, *"đã tưới xong cữ sáng"*, *"xịt thuốc xong khu A"*, *"đã bón ... bao"*, *"hoàn thành việc tỉa cành"*.
- **Ví dụ thực tế**: *"Anh Ba vừa bón phân lót xong cho nhà màng dưa lưới, dùng hết 2 bao vôi bột."*

#### 2. Cơ chế liên kết Kho tự động (Dual Action Resolution)
- AI nhận diện đây là hành động cập nhật tiến độ công việc và **tự động trừ kho vật tư**:
  1. Tìm kiếm trong bảng `running_tasks` phiên công việc đang `TODO` hoặc `IN_PROGRESS` của nhân công hoặc khu vực tương ứng.
  2. Điền thông tin `material_category_id = Vôi bột`, `quantity_used = 2.0`, `material_unit = 'bao'`.
  3. Khi Chủ vườn duyệt, DBService tự động hoàn tất task và sinh ngay phiếu xuất kho `inventory_transactions` tương ứng mà nhân công không cần phải nói thêm một câu lệnh xuất kho riêng biệt.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "running_tasks",
  "action_type": "UPDATE",
  "payload_json": {
    "where": { "running_task_id": 12 },
    "data": {
      "status": "DONE",
      "report_complete_at": "2026-10-15 10:30:00",
      "material_category_id": 15,
      "quantity_used": 2.0,
      "material_unit": "bao",
      "completion_notes": "Đã bón đều quanh luống nhà màng"
    }
  },
  "summary_text": "Hoàn thành: Bón lót dưa lưới (Tiêu hao 2 bao vôi bột)"
}
```

---

### ACTION 4: Giao Việc Nhanh Ngoài Thực Địa / Ad-hoc Task $\rightarrow$ Tạo Issue (`ASSIGN_ADHOC_TASK`)

#### 1. Quy tắc nhận diện
- Khẩu lệnh giao việc tức thời, công việc phát sinh đột xuất trong ngày, không nằm trong lịch trình định kỳ lặp lại của quy trình mẫu.
- **Quy tắc kiến trúc**: Mọi công việc đột xuất, sự vụ một lần đều được **khởi tạo dưới dạng một Issue/Hạng mục cần xử lý (`issues`)** để theo dõi và nghiệm thu dứt điểm, không trộn lẫn vào bảng `running_tasks` (vốn chỉ dành cho lịch trình tự động của SOP).
- **Từ khóa nhận diện**: *"ngày mai nhờ anh..."*, *"giao việc"*, *"nhắc anh Ba ra sửa..."*, *"chiều nay đi phát cỏ"*, *"lên lịch dọn mương"*, *"nhờ kiểm tra giùm cọc rào"*.
- **Ví dụ thực tế**: *"Chiều nay anh Ba ra gia cố lại hàng rào khu nuôi gà giùm tôi, khoảng 1 tiếng."*

#### 2. Cơ chế suy diễn
- Tạo một bản ghi mới vào bảng `issues` với:
  - `title`: Tóm tắt công việc cần làm (*"Gia cố hàng rào khu nuôi gà"*).
  - `zone_id`: Khu vực thực hiện (*"ZONE_CHUONG_GA"*).
  - `reporter_id` / `reported_by`: Người giao việc hoặc chỉ định người làm.
  - `severity`: `LOW` hoặc `MEDIUM` (tùy tính chất khẩn cấp).
  - `status`: `OPEN`.
  - `description`: Chi tiết yêu cầu kỹ thuật và thời lượng ước tính.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "issues",
  "action_type": "INSERT",
  "payload_json": {
    "zone_id": "ZONE_CHUONG_GA",
    "title": "Gia cố hàng rào khu nuôi gà",
    "description": "Gia cố cọc lưới tránh gà xổng ra ngoài, ước tính 60 phút",
    "severity": "LOW",
    "status": "OPEN",
    "reported_by": "Chủ vườn (Giao cho Anh Ba)"
  },
  "summary_text": "Giao việc ad-hoc (Issue): Gia cố hàng rào chuồng gà (Giao Anh Ba)"
}
```

---

### ACTION 5: Báo Cáo Sự Cố, Sâu Bệnh, Hư Hỏng Thiết Bị (`REPORT_ISSUE`)

#### 1. Quy tắc nhận diện
- Phát hiện bất thường tiêu cực, thiên tai, sâu bệnh hại tấn công, hỏng hóc máy móc cần xử lý cấp bách.
- **Từ khóa nhận diện**: *"bị sâu"*, *"bị rầy"*, *"vàng lá"*, *"cháy mô tơ"*, *"bể ống nước"*, *"chuột cắn"*, *"chết cây"*, *"hư máy bơm"*.
- **Ví dụ thực tế**: *"Vườn cam khu B xuất hiện rầy chổng cánh nhiều quá, lá non bị xoăn tít."*

#### 2. Cơ chế đánh giá mức độ nghiêm trọng
- AI tự động phân cấp `severity`:
  - `CRITICAL`: Cháy máy bơm chính, vỡ đường ống nước tưới toàn vườn, dịch bệnh lây lan diện rộng.
  - `HIGH`: Rầy rệp tấn công lá non, hỏng thiết bị cục bộ một luống.
  - `MEDIUM`: Chuột cắn rải rác, rò rỉ nhẹ đầu van.
  - `LOW`: Vách lưới rách nhỏ, mất cọc tiêu.
- **Ràng buộc an toàn**: Sự cố luôn mở ở trạng thái `status = 'OPEN'`.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "issues",
  "action_type": "INSERT",
  "payload_json": {
    "zone_id": "ZONE_CAM_B",
    "title": "Rầy chổng cánh hại cam khu B",
    "description": "Rầy xuất hiện mật độ cao, xoăn đọt non vườn cam",
    "severity": "HIGH",
    "status": "OPEN",
    "reported_by": "Bác giữ vườn"
  },
  "summary_text": "Báo cáo sự cố: Rầy chổng cánh hại cam Khu B (Mức độ CAO)"
}
```

---

### ACTION 6: Cập Nhật Ghi Chú & Tiến Trình Xử Lý Sự Cố (`UPDATE_ISSUE_NOTES`)

#### 1. Quy tắc nhận diện
- Nhân công hoặc chủ vườn thông báo tiến độ, biện pháp tạm thời hoặc kết quả xử lý ban đầu của một sự cố đã được ghi nhận trước đó.
- **Từ khóa nhận diện**: *"vụ rầy nâu sáng nay đã..."*, *"sự cố máy bơm: đã sửa xong phần điện"*, *"cập nhật vụ van nước rỉ"*, *"ghi chú thêm vào sự cố"*, *"tình hình sâu bệnh đỡ rồi"*.
- **Ví dụ thực tế**: *"Báo cáo vụ rầy chổng cánh khu B: sáng nay anh Ba đã phun thuốc sinh học thảo mộc đợt 1 rồi nghen."*

#### 2. Cơ chế cập nhật nối dòng (Append Notes Mechanism)
- AI tìm `issue_id` tương ứng đang ở trạng thái `OPEN` hoặc `IN_PROGRESS` tại khu vực được nhắc tới.
- Nối thêm nội dung mới vào trường `notes` kèm mốc thời gian ISO: `[YYYY-MM-DD HH:MM] Nội dung cập nhật`.
- Tự động chuyển `status = 'IN_PROGRESS'` nếu sự cố đang ở trạng thái `OPEN`.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "issues",
  "action_type": "UPDATE",
  "payload_json": {
    "where": { "issue_id": 8 },
    "data": {
      "status": "IN_PROGRESS",
      "notes": "[2026-10-15 11:00] Đã phun thuốc sinh học thảo mộc đợt 1 để khống chế mật độ rầy."
    }
  },
  "summary_text": "Cập nhật tiến độ sự cố #8: Đã phun thuốc sinh học đợt 1 (Khu B)"
}
```

---

### ACTION 7: Nghiệm Thu & Đóng Sự Cố / Hoàn Thành Việc Ad-hoc (`CLOSE_ISSUE`)

#### 1. Quy tắc nhận diện
- Thông báo xác nhận sự cố đã được khắc phục hoàn toàn, hoặc công việc đột xuất đã hoàn tất đạt yêu cầu.
- **Ràng buộc phân quyền RBAC**: **Chỉ có Chủ trang trại (`OWNER`) hoặc Quản lý (`ADMIN`) mới có quyền nghiệm thu và đóng sự cố**. Nhân công (`WORKER`) nếu báo xong thì chỉ được ghi nhận vào `notes` và chuyển `IN_PROGRESS` chờ chủ vườn duyệt đóng.
- **Từ khóa nhận diện**: *"nghiệm thu xong sự cố"*, *"đóng sự cố giùm tôi"*, *"máy bơm sửa xong chạy tốt rồi, đóng lại"*, *"đã kiểm tra xong vườn cam hết rầy, đóng việc"*.
- **Ví dụ thực tế**: *"Vụ rầy chổng cánh vườn cam khu B đã xử lý dứt điểm, đọt non ra khỏe, nghiệm thu đóng sự cố lại."*

#### 2. Cơ chế thực thi
- Cập nhật `status = 'CLOSED'` (hoặc `RESOLVED`).
- Ghi nhận `closed_at = CURRENT_TIMESTAMP` và lưu kết luận vào `resolution_notes`.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "issues",
  "action_type": "UPDATE",
  "payload_json": {
    "where": { "issue_id": 8 },
    "data": {
      "status": "CLOSED",
      "closed_at": "2026-10-15 16:30:00",
      "resolution_notes": "Đã xử lý triệt để bằng thuốc sinh học thảo mộc, đọt non phục hồi tốt."
    }
  },
  "summary_text": "Nghiệm thu đóng sự cố #8: Rầy chổng cánh Khu B (Hoàn thành)"
}
```

---

### ACTION 8: Thu Hoạch Nông Sản & Phân Loại Sản Lượng (`RECORD_HARVEST`)

#### 1. Quy tắc nhận diện
- Hoạt động thu hái, cắt quả, kéo cá, xuất chuồng lấy sản phẩm cuối cùng từ vụ mùa.
- **Từ khóa nhận diện**: *"thu hoạch được"*, *"cắt được ... kg"*, *"hái được ... tấn"*, *"kéo lưới được"*, *"bẻ dưa"*, *"cân đợt 1"*.
- **Ví dụ thực tế**: *"Sáng nay cắt tỉa đợt 1 dưa lưới nhà màng thu được 1 tấn 2, loại A được 800 ký, bán ước tính được 35 triệu."*

#### 2. Cơ chế suy diễn & Liên hoàn bảng
- AI nhận diện `cycle_id` tương ứng của nhà màng dưa lưới.
- Tự động bóc tách sản lượng tổng (`total_quantity = 1200`), phân loại phẩm cấp loại A (`800 kg`), loại B (`400 kg`).
- Khi duyệt: Ghi bản ghi vào `harvests` và tự động sinh phiếu nhập kho nông sản thương phẩm vào `inventory_transactions`.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "harvests",
  "action_type": "INSERT",
  "payload_json": {
    "cycle_id": 3,
    "harvest_date": "2026-10-15",
    "harvest_type": "PARTIAL",
    "total_quantity": 1200.0,
    "unit": "kg",
    "total_value": 35000000,
    "notes": "Thu hoạch dưa lưới đợt 1: Loại A 800kg, Loại B 400kg"
  },
  "summary_text": "Thu hoạch Dưa Lưới: 1,200 kg (Giá trị ước tính 35 triệu)"
}
```

---

### ACTION 9: Ghi Nhận Thu / Chi Tài Chính Tiền Mặt & Chuyển Khoản (`RECORD_FINANCIAL_TRANSACTION`)

#### 1. Quy tắc nhận diện
- Phát sinh dòng tiền thu vào hoặc chi ra thực tế.
- **Từ khóa nhận diện**: *"chi tiền"*, *"thu tiền"*, *"trả tiền công"*, *"chuyển khoản ... triệu"*, *"mua hết ... ngàn tiền mặt"*, *"tiền điện"*, *"tiền dầu"*.
- **Ví dụ thực tế**: *"Chi 1 triệu 500 ngàn tiền mặt trả công tỉa cành cho anh Ba."*

#### 2. Chuẩn hóa số tiền nguyên tuyệt đối
- Chuyển đổi toàn bộ ngôn ngữ khẩu ngữ số đếm (*"triệu rưỡi"*, *"hai trăm rưởi"*, *"bốn chai"*) thành **số nguyên VND chính xác**: `1500000`. Tuyệt đối không dùng số thực dấu phẩy động.
- Xác định phương thức thanh toán: `CASH` (tiền mặt), `TRANSFER` (chuyển khoản).

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "financial_transactions",
  "action_type": "INSERT",
  "payload_json": {
    "category_id": 6,
    "type": "EXPENSE",
    "amount": 1500000,
    "transaction_date": "2026-10-15",
    "partner_name": "Anh Ba",
    "payment_method": "CASH",
    "status": "COMPLETED",
    "notes": "Trả công tỉa cành vườn cam"
  },
  "summary_text": "Chi tiền mặt: 1,500,000 VND (Trả công tỉa cành - Anh Ba)"
}
```

---

### ACTION 10: Trao Đổi Hàng Hóa Trực Tiếp Phi Tiền Tệ (`RECORD_BARTER_EXCHANGE`)

#### 1. Quy tắc nhận diện
- Giao dịch lấy nông sản/phụ phẩm đổi lấy vật tư/con giống khác, không thông qua tiền mặt hoặc chỉ bù trừ một phần tiền chênh lệch.
- **Từ khóa nhận diện**: *"đổi ... lấy ..."*, *"lấy phân chuồng đổi cây giống"*, *"đổi ngô lấy cám"*, *"bù thêm ... tiền mặt"*.
- **Ví dụ thực tế**: *"Đem 10 bao ngô hạt đổi lấy 3 bao cám gà công nghiệp với anh Bảy, hai bên đổi ngang không bù tiền."*

#### 2. Cơ chế đối ứng hai vế đồng thời
- AI nhận diện đồng thời:
  - Vế đem đổi: 10 bao ngô hạt (`give_category_id = 9`, `give_quantity = 10.0`).
  - Vế nhận về: 3 bao cám gà (`receive_category_id = 12`, `receive_quantity = 3.0`).
  - Chênh lệch tiền: `cash_difference_vnd = 0`.
- Khi duyệt: Tự động xuất kho ngô và nhập kho cám gà mà không làm biến động số dư tiền mặt.

#### 3. Cấu trúc Staging Payload
```json
{
  "target_table": "barter_transactions",
  "action_type": "INSERT",
  "payload_json": {
    "partner_name": "Anh Bảy",
    "give_category_id": 9,
    "give_quantity": 10.0,
    "give_unit": "bao",
    "receive_category_id": 12,
    "receive_quantity": 3.0,
    "receive_unit": "bao",
    "estimated_value_vnd": 2500000,
    "cash_difference_vnd": 0,
    "status": "COMPLETED",
    "notes": "Đổi ngang 10 bao ngô hạt lấy 3 bao cám gà với anh Bảy"
  },
  "summary_text": "Đổi hàng: 10 bao ngô lấy 3 bao cám gà (Đổi ngang với Anh Bảy)"
}
```

---

### ACTION 11: Ghi Nhận Công Nợ & Trả Nợ Từng Đợt (`RECORD_DEBT` / `PAY_DEBT`)

#### 1. Quy tắc nhận diện
- Mua hàng hoặc bán hàng chưa thanh toán tiền ngay, hoặc trả nốt khoản nợ cũ.
- **Từ khóa nhận diện**: *"cho nợ"*, *"ghi sổ nợ"*, *"hẹn cuối vụ trả"*, *"trả nốt tiền nợ"*, *"thanh toán đợt 1 tiền giống"*.
- **Ví dụ thực tế**:
  - Phát sinh nợ: *"Mua 50 cây cam giống của trại cây giống Tư Bé giá 4 triệu, hẹn 2 tháng nữa thanh toán."*
  - Trả nợ dần: *"Nay chuyển khoản trả trước 2 triệu tiền giống cam cho Tư Bé."*

#### 2. Cơ chế cấn trừ nợ lũy kế
- Khi phát sinh nợ: Tạo bản ghi `debt_records` với `initial_amount = 4000000`, `status = 'UNPAID'`.
- Khi trả nợ: Tạo `debt_payments` số tiền `2000000`, tự động cập nhật `paid_amount = 2000000`, số nợ còn lại tự động tính `remaining_amount = 2000000`, trạng thái chuyển sang `PARTIAL`.

---

### ACTION 12: Khởi Tạo Chu Kỳ Canh Tác / Vụ Mùa Mới (`START_PRODUCTION_CYCLE`)

#### 1. Quy tắc nhận diện (Hai trường hợp kích hoạt)
Chu kỳ sản xuất / vụ mùa mới được khởi tạo khi thỏa mãn một trong hai điều kiện:
1. **Trường hợp A: Nhận con giống / cây giống (Auto-Trigger on Seed Receipt)**:
   - Khi có sự kiện nhập kho một mặt hàng thuộc nhóm giống cây trồng hoặc vật nuôi (ví dụ: *Gà giống 1 ngày tuổi, Heo giống, Cá giống, Cây giống cam xoàn*), AI tự động nhận diện đây là thời điểm bắt đầu một chu kỳ nuôi trồng mới và đề xuất khởi tạo `production_cycles`.
2. **Trường hợp B: Khẩu lệnh yêu cầu trực tiếp**:
   - Chủ vườn hoặc nhân công thông báo bắt đầu xuống giống, thả lứa mới.
   - **Từ khóa nhận diện**: *"bắt đầu vụ mới"*, *"xuống giống đợt..."*, *"thả 200 con gà giống"*, *"trồng mới vườn bưởi"*.
- **Ví dụ thực tế**:
  - *"Vừa nhận 200 con gà giống Ri lai từ trại giống Ba Vì giao tới Chuồng 1, bắt đầu lứa nuôi từ hôm nay."*
  - *"Bắt đầu xuống giống vụ Dưa Lưới Tết 2026 tại Nhà Màng 2, diện tích 1000m2."*

#### 2. Bước kiểm tra đã tồn tại & Chống trùng lặp (Active Cycle Deduplication & Zone Contention Check)
Trước khi tạo bản ghi chu kỳ mới, AI **bắt buộc phải thực hiện bước kiểm tra sự tồn tại** thông qua công cụ `search_production_cycle(zone_id=zone_id, status='ACTIVE')`:

1. **Kịch bản A: Trùng lặp cùng lứa / Đã tạo gần đây**:
   - Nếu tại `zone_id` đã có một chu kỳ đang `ACTIVE` với cùng đối tượng giống (`subject_name` hoặc `input_category_id`) được tạo gần đây:
   - **AI tuyệt đối không tạo chu kỳ mới** (tránh nhân đôi lịch trình SOP).
   - Thay vào đó, AI chuyển sang hành động **cộng dồn số lượng giống hoặc gắn sự kiện nhập giống vào chu kỳ hiện tại**:
     > *"Dạ chú ơi, lứa gà tại Chuồng 1 đã có sẵn trong hệ thống rồi, con đã ghi nhận bổ sung thêm 200 con giống vào lứa hiện tại luôn nghen!"*

2. **Kịch bản B: Xung đột khu vực (Zone Contention - Vụ cũ chưa đóng)**:
   - Nếu khu vực đó đang có một vụ mùa khác chưa kết thúc (`status = 'ACTIVE'`, `actual_end_date IS NULL`), ví dụ: Chuồng 1 đang có lứa gà cũ chưa xuất chuồng, hoặc Nhà màng 2 đang trồng dưa lưới chưa dọn dẹp:
   - **AI không tự ý tạo đè**, mà chủ động gửi cảnh báo kèm gợi ý lựa chọn trên Telegram cho Chủ trang trại:
     > *"Khu vực [Nhà Màng 2] hiện vẫn đang có vụ [Dưa Lưới Vụ 1] ở trạng thái ACTIVE chưa đóng. Chú có muốn kết thúc vụ cũ để mở vụ mới, hay đây là vụ trồng xen canh/gối đầu ạ?"*

3. **Kịch bản C: Khu vực hoàn toàn sẵn sàng (Clean Zone)**:
   - Tại `zone_id` không có vụ mùa nào đang hoạt động (hoặc các vụ cũ đều đã `COMPLETED` / `CANCELLED`):
   - AI an toàn tiến hành tạo bản ghi `production_cycles` mới.

#### 3. Cơ chế tự động sinh lịch làm việc (Auto-SOP Activation)
- Sau khi chu kỳ mới được Chủ trang trại phê duyệt, AI ghi nhận chính thức vào `production_cycles` với mốc bắt đầu $t_{\text{base}} = \text{hôm nay}$, liên kết nhóm giống `input_category_id` trong `dictionary`.
- Hệ thống tự động kích hoạt hàm `build_running_tasks_for_cycle` để quét các công việc mẫu trong quy trình chuẩn (`tasks`/`subtasks`) và sinh sẵn toàn bộ lịch chạy thực địa `running_tasks` trong 90 ngày tới.

#### 4. Cấu trúc Staging Payload
```json
{
  "target_table": "production_cycles",
  "action_type": "INSERT",
  "payload_json": {
    "zone_id": "ZONE_CHUONG_1",
    "name": "Lứa Gà Ri Lai Tết 2026",
    "subject_name": "Gà Ri Lai",
    "start_date": "2026-10-15",
    "input_category_id": 22,
    "input_quantity": 200.0,
    "input_unit": "con",
    "area_size": 150.0,
    "unit_of_size": "m2",
    "status": "ACTIVE"
  },
  "summary_text": "Bắt đầu vụ mùa: Lứa Gà Ri Lai Tết 2026 (Chuồng 1 - 200 con giống)"
}
```

#### 5. Phản hồi xác nhận qua Telegram
> *"Dạ, con đã kiểm tra Chuồng 1 hiện đang trống và đã lên lịch bắt đầu lứa Gà Ri Lai 200 con từ hôm nay. Toàn bộ lịch tiêm phòng và cữ ăn theo quy trình 90 ngày đã sẵn sàng chờ chú duyệt ạ!"*

---

### ACTION 13: Tra Cứu, Tìm Kiếm & Hỏi Đáp Tức Thì (`QUERY_AND_SEARCH`)

#### 1. Quy tắc nhận diện (Read-only Q&A)
- Các câu hỏi thông tin, thống kê, kiểm tra số liệu trang trại.
- **Từ khóa nhận diện**: *"cho xem..."*, *"kiểm tra giùm..."*, *"hôm nay có việc gì"*, *"còn bao nhiêu bao phân"*, *"khu A có sự cố gì không"*, *"vụ cam lời hay lỗ"*.
- **Ví dụ thực tế**: *"Kiểm tra giùm tôi xem trong kho còn bao nhiêu bao vôi bột?"*

#### 2. Cơ chế Lớp phủ ảo thời gian thực (Zero-Staging Read)
- **Tuyệt đối không tạo bản ghi trong `pending_events`**.
- AI kích hoạt các tool tra cứu chuyên biệt (`search_dictionary`, `search_category`, `search_task`, `search_issue`...).
- Dữ liệu trả về được tự động hợp nhất với các sự kiện chưa duyệt thông qua `get_data_with_pending_applied`.
- AI tổng hợp và trả lời ngay bằng tiếng Việt tự nhiên:
  > *"Dạ thưa chú, trong từ điển kho hiện còn ghi nhận 15 bao vôi bột (trong đó có 2 bao vừa xuất sáng nay đang chờ chú duyệt ạ)!"*

---

### ACTION 14: Xử Lý Khẩu Lệnh Phức Hợp Đa Hành Động (`MULTI_ACTION_VOICE_HANDLING`)

#### 1. Tình huống thực tế
Người nông dân nói gộp nhiều việc trong một lần gửi voice note:
> *"Sáng nay vừa mua 10 bao phân NPK hết 3 triệu tiền mặt của tiệm Năm Lúa, xuất luôn 3 bao bón cho vườn bưởi, sẵn tiện thấy van nước tưới khu A bị nứt gãy chảy tràn lan."*

#### 2. Cơ chế phân tách & Đóng gói đồng bộ của AI
AI phân tích ngữ nghĩa và tách thành **4 sự kiện In-Flight riêng biệt có cùng nguồn âm thanh**:
1. **Event 1 (Nhập kho)**: `target_table = 'inventory_transactions'`, `action_type = 'INSERT'`, nhập 10 bao NPK.
2. **Event 2 (Tài chính)**: `target_table = 'financial_transactions'`, `action_type = 'INSERT'`, chi 3,000,000 VND tiền mặt.
3. **Event 3 (Xuất kho)**: `target_table = 'inventory_transactions'`, `action_type = 'INSERT'`, xuất 3 bao NPK bón vườn bưởi.
4. **Event 4 (Báo sự cố)**: `target_table = 'issues'`, `action_type = 'INSERT'`, sự cố nứt van nước khu A (Mức độ HIGH).

Cả 4 event đều trỏ chung một `audio_path` gốc. Chủ vườn nhận được thẻ thông báo tổng hợp trên Telegram với danh sách từng mục kèm nút duyệt riêng lẻ hoặc nút `[Duyệt tất cả]`.

---

## 3. Bảng Ánh Xạ Ý Định Sang Tool & Bảng Đích (Intent to Tool Mapping Matrix)

| Mã Ý Định (Intent) | Mô tả nghiệp vụ | Công cụ Function Calling (`tools.py`) | Bảng cơ sở dữ liệu đích | Trạng thái ghi nhận |
| :--- | :--- | :--- | :--- | :--- |
| `RECORD_INVENTORY_RECEIPT` | Nhập kho vật tư / hàng hóa | `create_inventory_transaction` | `inventory_transactions` | In-Flight (PENDING) |
| `RECORD_INVENTORY_ISSUE` | Xuất kho bón cây / bán hàng | `create_inventory_transaction` | `inventory_transactions` | In-Flight (PENDING) |
| `COMPLETE_TASK` | Báo xong việc định kỳ & tự trừ kho | `complete_running_task` | `running_tasks` + `inventory_transactions` | In-Flight (PENDING) |
| `ASSIGN_ADHOC_TASK` | Giao việc nhanh đột xuất (tạo issue) | `create_issue` | **`issues`** | In-Flight (PENDING) |
| `REPORT_ISSUE` | Báo cáo sự cố / sâu bệnh mới | `create_issue` | `issues` | In-Flight (PENDING) |
| `UPDATE_ISSUE_NOTES` | Cập nhật tiến độ / ghi chú sự cố | `manage_issue` | `issues` | In-Flight (PENDING) |
| `CLOSE_ISSUE` | Nghiệm thu & Đóng sự cố / việc ad-hoc | `manage_issue` | `issues` | In-Flight (PENDING) |
| `RECORD_HARVEST` | Thu hoạch nông sản | `create_harvest` | `harvests` + `yield_records` | In-Flight (PENDING) |
| `START_PRODUCTION_CYCLE` | Nhận giống hoặc mở vụ mùa mới | `create_production_cycle` | `production_cycles` + `running_tasks` | In-Flight (PENDING) |
| `RECORD_FINANCIAL_TRANSACTION`| Thu / Chi tiền mặt, ngân hàng | `create_financial_transaction` | `financial_transactions` | In-Flight (PENDING) |
| `RECORD_BARTER_EXCHANGE` | Đổi hàng hóa phi tiền tệ | `record_barter_exchange` | `barter_transactions` + `inventory_transactions` | In-Flight (PENDING) |
| `PROCESS_DEBT_PAYMENT` | Trả nợ từng đợt | `process_debt_payment` | `debt_payments` + `financial_transactions` | In-Flight (PENDING) |
| `CREATE_ZONE` | Khai báo khu vực / lô đất | `create_new_zone` | `zones` | In-Flight (PENDING) |
| `CREATE_DICTIONARY_ENTRY` | Khai báo vật tư / kho mới | `create_category` / `create_product` | `dictionary` | In-Flight (PENDING) |
| `QUERY_AND_SEARCH` | Tra cứu, hỏi đáp số liệu | `search_*` (17 search tools) | Views + Virtual Overlay | **Trả lời tức thì (Read-only)** |

---

## 4. Quy Chuẩn Phản Hồi Giọng Điệu AI (Tone of Voice & Persona Standards)

Để người nông dân cảm thấy gần gũi, tin cậy và gắn bó với trợ lý ảo:
1. **Dân dã, lễ phép, tôn trọng**: Xưng *"con"* hoặc *"em"*, gọi người dùng là *"chú"*, *"bác"*, *"anh"*, *"chị"*.
2. **Ngắn gọn, súc tích (Dưới 3 câu thoại)**: Không trả lời dong dài, hoa mỹ. Báo thẳng vào nội dung cốt lõi: Đã ghi nhận cái gì, số lượng bao nhiêu, ai sẽ duyệt.
3. **Chủ động nhắc khéo thông tin còn thiếu**:
   - *Ví dụ*: *"Dạ con đã ghi xuất 5 bao NPK cho Vườn Cam. Mà chú Năm ơi, chú lấy từ kho nào để con ghi chú thêm cho chú dễ nhớ nghen?"*
4. **Minh bạch trạng thái kiểm duyệt**: Luôn cho nhân công biết sự kiện đang ở trạng thái *"chờ chủ duyệt"* để tránh hiểu lầm là dữ liệu đã tự ý chốt sổ.
