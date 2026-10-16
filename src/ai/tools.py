"""AgriVoice-AI: AI Tools Definitions & Schema Specs.

Provides function calling definitions (OpenAI and Google GenAI format)
for domain functions across farm management domains.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from google.genai import types


# ==============================================================================
# TOOL SCHEMAS (OpenAI-compatible JSON Schema)
# ==============================================================================

CREATE_NEW_ZONE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_new_zone",
    "description": (
        "Tạo hoặc khai báo một khu vực, lô đất, nhà màng, hoặc chuồng trại mới trong trang trại.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng thông báo quy hoạch, khai hoang, lập mới hoặc chia lô một khu vực/vườn mới.\n"
        "- Từ khóa nhận diện: 'tạo khu', 'thêm vườn mới', 'khai báo lô', 'lập nhà màng mới', 'mở thêm chuồng', 'quy hoạch khu'.\n"
        "- Ví dụ: 'Khai báo Vườn Sầu Riêng 2 diện tích 1.5 ha', 'Tạo khu A làm nhà màng dưa lưới'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi giao việc trên vườn đã có sẵn (dùng create_task).\n"
        "- KHÔNG dùng khi báo cáo sự cố (dùng create_issue) hoặc ghi nhật ký canh tác (dùng create_production_log).\n"
        "- KHÔNG dùng khi người dùng hỏi danh sách khu vực hiện có (dùng get_data_with_pending_applied)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "zone_name": {
                "type": "string",
                "description": "Tên định danh của khu vực (ví dụ: Vườn Cam Xoàn 1, Khu A, Nhà Màng Dưa Lưới).",
            },
            "sector": {
                "type": "string",
                "enum": ["CROP", "LIVESTOCK", "AQUACULTURE", "MIXED"],
                "description": "Mảng sản xuất chính của khu vực (CROP: Trồng trọt, LIVESTOCK: Chăn nuôi, AQUACULTURE: Thủy sản, MIXED: Kết hợp).",
            },
            "area_size": {
                "type": "number",
                "description": "Diện tích hoặc quy mô của khu vực.",
            },
            "unit_of_size": {
                "type": "string",
                "enum": ["m2", "ha", "m3"],
                "description": "Đơn vị đo diện tích hoặc dung tích (m2, ha, m3).",
            },
            "address": {
                "type": "string",
                "description": "Vị trí địa lý hoặc địa chỉ chi tiết trong trang trại.",
            },
            "current_stock_summary": {
                "type": "string",
                "description": "Hiện trạng cây trồng, vật nuôi đang canh tác tại khu vực.",
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú đặc điểm đất đai, nguồn nước, thổ nhưỡng.",
            },
        },
        "required": ["zone_name"],
    },
}

CREATE_TASK_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_task",
    "description": (
        "Tạo công việc, nhiệm vụ hoặc hạng mục cần làm trong trang trại (lên kế hoạch thực hiện tương lai).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng muốn giao việc, lên lịch, nhắc nhở hoặc chỉ định việc cần làm cho nhân công hoặc bản thân.\n"
        "- Từ khóa nhận diện: 'cần làm', 'giao việc', 'nhắc việc', 'lên lịch', 'ngày mai phải...', 'nhiệm vụ', 'hạn chót', 'phân công'.\n"
        "- Ví dụ: 'Ngày mai nhớ bón phân vườn bưởi', 'Giao anh Ba sửa máy bơm trước thứ 6', 'Lên lịch xịt thuốc sâu sáng mai'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi người dùng báo cáo việc ĐÃ LÀM XONG trong ngày (dùng create_production_log để ghi nhật ký).\n"
        "- KHÔNG dùng khi chỉ thông báo phát hiện sự cố, sâu bệnh mà chưa giao việc cụ thể (dùng create_issue).\n"
        "- KHÔNG dùng khi hỏi danh sách việc cần làm (dùng get_data_with_pending_applied)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Tiêu đề công việc (ví dụ: Bón phân NPK đợt 2, Sửa ống nước khu A).",
            },
            "description": {
                "type": "string",
                "description": "Mô tả chi tiết công việc hoặc hướng dẫn thực hiện.",
            },
            "priority": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"],
                "description": "Mức độ ưu tiên của công việc.",
            },
            "due_date": {
                "type": "string",
                "description": "Hạn chót hoàn thành (YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS).",
            },
            "project_id": {
                "type": "integer",
                "description": "ID dự án liên quan nếu có.",
            },
            "estimated_minutes": {
                "type": "integer",
                "description": "Thời lượng ước tính để hoàn thành (phút).",
            },
        },
        "required": ["title"],
    },
}

CREATE_PRODUCTION_LOG_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_production_log",
    "description": (
        "Ghi chép nhật ký hoạt động sản xuất, canh tác hàng ngày ĐÃ HOÀN THÀNH (tưới nước, bón phân, xịt thuốc, làm cỏ, cho ăn...).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng báo cáo công việc canh tác đã làm hoặc vừa thực hiện xong trong ngày kèm lượng vật tư tiêu hao.\n"
        "- Từ khóa nhận diện: 'hôm nay đã...', 'vừa mới tưới...', 'đã bón ... bao phân', 'xịt thuốc rầy xong rồi', 'đã cho ăn ... kg'.\n"
        "- Ví dụ: 'Sáng nay đã bón 3 bao NPK cho vụ dưa lưới', 'Vừa tưới nước xong khu A hết 2 tiếng', 'Đã phun thuốc đạo ôn lứa 1'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi lên kế hoạch việc tương lai chưa làm (dùng create_task).\n"
        "- KHÔNG dùng cho hoạt động thu hoạch nông sản cuối vụ (dùng create_harvest).\n"
        "- KHÔNG dùng khi chỉ nhập/xuất kho vật tư đơn thuần tại kho (dùng create_inventory_transaction)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cycle_id": {
                "type": "integer",
                "description": "ID vụ mùa / chu kỳ sản xuất đang triển khai (để null nếu chưa rõ vụ mùa).",
            },
            "zone_id": {
                "type": "string",
                "description": "Mã khu vực canh tác diễn ra hoạt động (ví dụ: ZONE_A).",
            },
            "title": {
                "type": "string",
                "description": "Tiêu đề nhật ký hoạt động (ví dụ: Tưới phân đợt 1, Bón phân NPK).",
            },
            "activity_type": {
                "type": "string",
                "enum": [
                    "SOWING",
                    "TRANSPLANTING",
                    "FERTILIZING",
                    "PEST_CONTROL",
                    "IRRIGATION",
                    "PRUNING",
                    "WEEDING",
                    "FEEDING",
                    "VACCINATION",
                    "MONITORING",
                    "HARVESTING",
                    "OTHER",
                ],
                "description": "Loại hoạt động canh tác.",
            },
            "log_date": {
                "type": "string",
                "description": "Ngày thực hiện (YYYY-MM-DD).",
            },
            "description": {
                "type": "string",
                "description": "Mô tả chi tiết việc đã thực hiện.",
            },
            "quantity": {
                "type": "number",
                "description": "Khối lượng hoặc lượng vật tư sử dụng.",
            },
            "unit": {
                "type": "string",
                "description": "Đơn vị vật tư (kg, lít, bao).",
            },
            "material_name": {
                "type": "string",
                "description": "Tên loại phân bón, thuốc bảo vệ thực vật hoặc thức ăn.",
            },
            "cost_amount": {
                "type": "number",
                "description": "Chi phí phát sinh (VND) nếu có.",
            },
        },
        "required": ["title"],
    },
}

CREATE_HARVEST_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_harvest",
    "description": (
        "Ghi nhận đợt thu hoạch nông sản / thủy sản từ chu kỳ canh tác hoặc vụ mùa.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng báo cáo việc cắt trút, thu hái, đánh bắt sản phẩm từ cây trồng/vật nuôi kèm sản lượng.\n"
        "- Từ khóa nhận diện: 'thu hoạch', 'cắt dưa', 'hái cam', 'kéo lưới cá', 'thu hoạch được ... tấn/kg', 'bẻ trái', 'thu gom đợt...'.\n"
        "- Ví dụ: 'Hôm nay thu hoạch vụ cam xoàn được 3.5 tấn', 'Đã cắt đợt dưa lưới tết được 1200 kg giá trị 30 triệu'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng cho hoạt động chăm sóc cây trồng hàng ngày (dùng create_production_log).\n"
        "- KHÔNG dùng khi chỉ bán hàng từ kho lưu trữ (dùng create_inventory_transaction / create_financial_transaction)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cycle_id": {
                "type": "integer",
                "description": "ID vụ mùa được thu hoạch.",
            },
            "harvest_date": {
                "type": "string",
                "description": "Ngày thu hoạch (YYYY-MM-DD).",
            },
            "harvest_type": {
                "type": "string",
                "enum": ["MAIN", "PARTIAL", "FINAL"],
                "description": "Hình thức thu hoạch (MAIN: chính vụ, PARTIAL: tỉa thưa/thu từng phần, FINAL: thu dọn dẹp kết thúc vụ).",
            },
            "total_quantity": {
                "type": "number",
                "description": "Tổng sản lượng thu hoạch được.",
            },
            "unit": {
                "type": "string",
                "description": "Đơn vị sản lượng (kg, tấn, giỏ).",
            },
            "total_value": {
                "type": "number",
                "description": "Tổng giá trị thu hoạch ước tính hoặc thực tế (VND).",
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú chất lượng hoặc tình hình thu hoạch.",
            },
        },
        "required": ["cycle_id"],
    },
}

CREATE_INVENTORY_TRANSACTION_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_inventory_transaction",
    "description": (
        "Ghi nhận giao dịch kho hàng (nhập kho, xuất kho, xuất bón cho cây/nuôi con, điều chuyển, điều chỉnh tồn kho, thanh lý hàng hư hỏng trong kho).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng thông báo:\n"
        "  1. MUA VẬT TƯ: Mua phân bón, thuốc trừ sâu, thức ăn, vật tư (ví dụ: 'mua 10 bao phân Quế Lâm', 'mua 5 bao vôi bột'). Khi mua vật tư, BẮT BUỘC GỌI ĐỒNG THỜI: create_inventory_transaction (để nhập kho, transaction_type='RECEIPT') VÀ create_financial_transaction (để chi tiền, type='EXPENSE').\n"
        "  2. NHẬP KHO: Nhận hàng về, nhập thêm hàng hóa vào kho.\n"
        "  3. XUẤT KHO: Xuất bón cây, xuất cho lứa nuôi (ví dụ: 'xuất 2 bao bón cho vườn bưởi khu B' -> transaction_type='ISSUE', quantity_change=-2.0).\n"
        "  4. ĐIỀU CHUYỂN HOẶC HỦY KHO: Chuyển kho, kiểm kê hoặc hủy hàng hỏng.\n"
        "[LƯU Ý THAM SỐ]:\n"
        "- Điền tên hàng hóa/vật tư vào item_name.\n"
        "- Nếu người dùng chưa nêu rõ kho lưu trữ, để warehouse_id = null.\n"
        "- Nếu chưa rõ đơn vị tính unit_id hoặc product_id, để null.\n"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "item_name": {
                "type": "string",
                "description": "Tên vật tư, phân bón, thuốc, thức ăn hoặc nông sản (ví dụ: 'Phân hữu cơ Quế Lâm', 'Vôi bột', 'Cám gà').",
            },
            "product_id": {
                "type": "integer",
                "description": "ID sản phẩm hoặc vật tư nếu đã xác định trong hệ thống.",
            },
            "category_id": {
                "type": "integer",
                "description": "ID danh mục từ điển nếu đã xác định.",
            },
            "warehouse_id": {
                "type": "integer",
                "description": "ID kho hàng phát sinh giao dịch (để null nếu chưa rõ kho).",
            },
            "transaction_type": {
                "type": "string",
                "enum": [
                    "RECEIPT",
                    "ISSUE",
                    "ISSUE_PRODUCTION",
                    "ISSUE_PROCESSING",
                    "TRANSFER_OUT",
                    "TRANSFER_IN",
                    "COUNT_ADJUSTMENT",
                    "RETURN_TO_SUPPLIER",
                    "DAMAGE_WRITE_OFF",
                    "EXPIRED_WRITE_OFF",
                ],
                "description": "Loại giao dịch (RECEIPT: nhập kho/mua về, ISSUE: xuất kho/bón/dùng, TRANSFER_OUT: chuyển đi...).",
            },
            "quantity_change": {
                "type": "number",
                "description": "Số lượng thay đổi (dương nếu nhập kho, âm nếu xuất kho).",
            },
            "unit_id": {
                "type": "integer",
                "description": "ID đơn vị tính (để null nếu chưa rõ).",
            },
            "unit_cost_vnd": {
                "type": "number",
                "description": "Đơn giá đơn vị (VND).",
            },
            "reference_note": {
                "type": "string",
                "description": "Ghi chú lý do xuất nhập kho hoặc thông tin nhà cung cấp / đối tác.",
            },
        },
        "required": ["transaction_type", "quantity_change"],
    },
}

CREATE_FINANCIAL_TRANSACTION_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_financial_transaction",
    "description": (
        "Ghi chép giao dịch thu chi tài chính bằng tiền (bán nông sản, mua vật tư, trả lương nhân công, chi phí xăng xe, điện nước...).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng nhắc đến SỐ TIỀN thanh toán, chi trả, tạm ứng hoặc thu tiền về trong trang trại.\n"
        "- Từ khóa nhận diện: 'thu tiền', 'chi tiền', 'mua hết ... triệu', 'bán được ... đồng', 'trả tiền công', 'chuyển khoản', 'thanh toán', 'tiền điện', 'tiền dầu'.\n"
        "- Ví dụ: 'Bán cam thu về 85 triệu chuyển khoản', 'Chi 2 triệu tiền công cắt tỉa cành cho anh Ba', 'Mua 5 bao phân hết 3 triệu 500 ngàn tiền mặt'.\n"
        "[ĐỒNG BỘ VẬT TƯ VÀ TIỀN]:\n"
        "- Khi mua hoặc bán vật tư, hàng hóa có đề cập số tiền, HÃY GỌI ĐỒNG THỜI: create_financial_transaction (ghi nhận thu/chi tiền) VÀ create_inventory_transaction (ghi nhận nhập/xuất kho vật tư).\n"
        "- Không dùng khi hỏi tổng doanh thu hay báo cáo tài chính (dùng get_data_with_pending_applied)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category_id": {
                "type": "integer",
                "description": "ID danh mục thu chi (ví dụ: Tiền bán nông sản, Tiền phân bón, Tiền nhân công).",
            },
            "type": {
                "type": "string",
                "enum": ["INCOME", "EXPENSE"],
                "description": "Loại giao dịch (INCOME: Thu vào, EXPENSE: Chi ra).",
            },
            "amount": {
                "type": "number",
                "description": "Số tiền giao dịch (VND).",
            },
            "transaction_date": {
                "type": "string",
                "description": "Ngày giao dịch (YYYY-MM-DD).",
            },
            "cycle_id": {
                "type": "integer",
                "description": "ID chu kỳ / vụ mùa liên quan để hạch toán chi phí giá thành.",
            },
            "partner_name": {
                "type": "string",
                "description": "Tên đối tác / khách hàng / nhà cung cấp liên quan.",
            },
            "payment_method": {
                "type": "string",
                "enum": ["CASH", "TRANSFER", "DEBT"],
                "description": "Hình thức thanh toán (CASH: Tiền mặt, TRANSFER: Chuyển khoản, DEBT: Công nợ).",
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú nội dung giao dịch thu chi.",
            },
        },
        "required": ["category_id", "type", "amount"],
    },
}

COMPLETE_RUNNING_TASK_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "complete_running_task",
    "description": (
        "Báo cáo hoàn thành một phiên công việc thực địa (running_task) và tự động xuất kho vật tư tiêu hao nếu có.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng báo cáo đã làm xong một cữ công việc định kỳ trong ngày (ví dụ: 'đã bón phân lót dưa lưới xong, dùng hết 2 bao vôi', 'đã tưới nước sáng khu A').\n"
        "- Từ khóa nhận diện: 'làm xong rồi', 'đã hoàn thành task', 'đã bón xong ... bao', 'vừa xịt thuốc xong khu...'.\n"
        "- Tự động liên kết: nếu có tiêu hao vật tư, hệ thống sẽ tự động trừ kho mà không cần gọi thêm lệnh xuất kho riêng.\n"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "running_task_id": {
                "type": "integer",
                "description": "Mã ID của phiên công việc trong bảng running_tasks cần đánh dấu hoàn thành (để null nếu chưa rõ).",
            },
            "task_name": {
                "type": "string",
                "description": "Tên công việc hoặc nội dung thực địa nếu chưa rõ running_task_id.",
            },
            "material_category_id": {
                "type": "integer",
                "description": "ID mục vật tư trong từ điển dictionary đã tiêu hao khi làm việc (nếu có).",
            },
            "quantity_used": {
                "type": "number",
                "description": "Số lượng vật tư đã sử dụng thực tế (ví dụ: 2.0).",
            },
            "material_unit": {
                "type": "string",
                "description": "Đơn vị tính vật tư tiêu hao (ví dụ: 'bao', 'chai', 'kg', 'lít').",
            },
            "completion_notes": {
                "type": "string",
                "description": "Ghi chú của người làm vườn sau khi hoàn thành công việc.",
            },
        },
        "required": [],
    },
}

RECORD_BARTER_EXCHANGE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "record_barter_exchange",
    "description": (
        "Ghi nhận giao dịch trao đổi hàng hóa trực tiếp phi tiền tệ (hàng đổi hàng) giữa nông hộ với đối tác/đại lý.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng thông báo đem nông sản/phụ phẩm đổi lấy vật tư/con giống khác (ví dụ: 'đổi 10 bao ngô lấy 3 bao cám gà', 'lấy 2 xe phân chuồng đổi 50 cây cam giống bù thêm 500k').\n"
        "- Từ khóa nhận diện: 'đổi ... lấy ...', 'hàng đổi hàng', 'lấy ... đổi lấy ...', 'bù thêm tiền đổi hàng'.\n"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "partner_name": {
                "type": "string",
                "description": "Tên đối tác hoặc nông hộ thực hiện trao đổi.",
            },
            "give_category_id": {
                "type": "integer",
                "description": "ID nhóm hàng trong từ điển mà trang trại đem đi đổi.",
            },
            "give_quantity": {
                "type": "number",
                "description": "Số lượng hàng hóa đem đi đổi.",
            },
            "give_unit": {
                "type": "string",
                "description": "Đơn vị tính hàng đem đổi (ví dụ: 'bao', 'kg', 'xe').",
            },
            "receive_category_id": {
                "type": "integer",
                "description": "ID nhóm hàng trong từ điển mà trang trại nhận về.",
            },
            "receive_quantity": {
                "type": "number",
                "description": "Số lượng hàng hóa nhận về.",
            },
            "receive_unit": {
                "type": "string",
                "description": "Đơn vị tính hàng nhận về (ví dụ: 'bao', 'cây', 'kg').",
            },
            "estimated_value_vnd": {
                "type": "integer",
                "description": "Giá trị ước tính quy đổi tương đương của giao dịch (VND).",
            },
            "cash_difference_vnd": {
                "type": "integer",
                "description": "Tiền chênh lệch bù trừ: > 0 nếu trang trại trả thêm, < 0 nếu thu thêm, = 0 nếu đổi ngang.",
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú thỏa thuận đổi hàng giữa hai bên.",
            },
        },
        "required": [
            "partner_name",
            "give_category_id",
            "give_quantity",
            "give_unit",
            "receive_category_id",
            "receive_quantity",
            "receive_unit",
        ],
    },
}

PROCESS_DEBT_PAYMENT_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "process_debt_payment",
    "description": (
        "Ghi nhận đợt thanh toán trả nợ từng lần cho một khoản nợ mua vật tư hoặc thu nợ từ khách hàng.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng thông báo thanh toán trả bớt một phần hoặc tất toán nợ cũ (ví dụ: 'nay chuyển khoản trả 2 triệu tiền giống cam cho Tư Bé', 'anh Ba trả nốt 5 triệu tiền dưa').\n"
        "- Từ khóa nhận diện: 'trả nợ', 'thanh toán tiền nợ', 'trả trước ... triệu tiền giống', 'thu nợ'.\n"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "debt_id": {
                "type": "integer",
                "description": "Mã số định danh của khoản nợ trong bảng debt_records.",
            },
            "amount_paid": {
                "type": "integer",
                "description": "Số tiền thanh toán đợt này (VND).",
            },
            "payment_method": {
                "type": "string",
                "enum": ["CASH", "TRANSFER"],
                "description": "Hình thức thanh toán: CASH (tiền mặt) hoặc TRANSFER (chuyển khoản).",
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú lần trả nợ.",
            },
        },
        "required": ["debt_id", "amount_paid"],
    },
}
CREATE_ISSUE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_issue",
    "description": (
        "Ghi nhận sự cố, dịch hại, sâu bệnh, thiên tai, hỏng hóc máy móc HOẶC GIAO VIỆC NHANH ĐỘT XUẤT NGOÀI VƯỜN (Ad-hoc Task).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng phát hiện và thông báo vấn đề bất thường, sâu bệnh tấn công, hư hại hoặc trục trặc kỹ thuật.\n"
        "- ĐỒNG THỜI kích hoạt khi người dùng giao việc đột xuất HOẶC BÁO CÁO VIỆC ĐÃ LÀM XONG MÀ CHƯA CÓ TRONG KẾ HOẠCH (nếu không có task nào khớp, tự tạo issue và đánh dấu luôn).\n"
        "- Từ khóa nhận diện: 'bị sâu', 'bị bệnh', 'rầy nâu', 'vàng lá', 'chết cây', 'hỏng máy bơm', 'rò rỉ ống nước', 'chập điện', 'gãy cành', 'sự cố', 'nhờ anh...', 'giao việc anh...', 'ra sửa...', 'đi phát cỏ'...\n"
        "- Ví dụ: 'Vườn cam xuất hiện rầy chổng cánh nhiều quá', 'Chiều nay anh Ba ra gia cố hàng rào khu nuôi gà khoảng 1 tiếng', 'Anh Ba đã sửa xong cái van nước bị nứt'.\n"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Tiêu đề sự cố / công việc phát sinh (ví dụ: Bệnh vàng lá gân xanh, Sửa van nước tưới, Cho gà ăn).",
            },
            "zone_id": {
                "type": "string",
                "description": "Mã khu vực phát sinh sự cố (để null nếu chưa rõ).",
            },
            "description": {
                "type": "string",
                "description": "Mô tả biểu hiện, triệu chứng hoặc vị trí hư hỏng chi tiết.",
            },
            "severity": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                "description": "Mức độ nghiêm trọng của sự cố.",
            },
            "status": {
                "type": "string",
                "enum": ["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"],
                "description": "Trạng thái: OPEN (mới phát hiện), IN_PROGRESS (đang xử lý/tiến độ), CLOSED (đã sửa xong/hoàn thành).",
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú tiến độ hoặc nội dung công việc đã làm.",
            },
            "resolution_notes": {
                "type": "string",
                "description": "Ghi chú kết quả hoàn thành hoặc phương án nghiệm thu.",
            },
            "reported_by": {
                "type": "string",
                "description": "Tên người báo cáo hoặc thực hiện.",
            },
        },
        "required": ["title"],
    },
}

MANAGE_ISSUE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "manage_issue",
    "description": (
        "Cập nhật tiến trình xử lý, bổ sung ghi chú hiện trường (notes) hoặc nghiệm thu đóng sự cố/việc thực địa (close/resolve).\n"
        "[TỰ ĐỘNG ĐỌC CẢ TASK VÀ ISSUE - NẾU KHÔNG KHỚP TỰ TẠO ISSUE VÀ UPDATE LUÔN]:\n"
        "- Hệ thống sẽ tự động tra cứu cả bảng running_tasks và bảng issues.\n"
        "- Nếu khớp với task -> hoàn thành task.\n"
        "- Nếu khớp với issue -> cập nhật issue.\n"
        "- NẾU KHÔNG CÓ CÁI NÀO KHỚP -> Tự động tạo issue mới và cập nhật luôn trạng thái (IN_PROGRESS hoặc CLOSED) kèm ghi chú thực địa, đảm bảo thông tin không bị mất.\n"
        "- Từ khóa nhận diện: 'cập nhật sự cố', 'vụ sâu rầy đã...', 'đã sửa xong', 'nghiệm thu đóng sự cố', 'đóng việc lại', 'báo cáo vụ...'.\n"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "issue_id": {
                "type": "integer",
                "description": "Mã ID sự cố nếu đã biết (để null nếu chưa rõ ID).",
            },
            "title": {
                "type": "string",
                "description": "Tên hoặc từ khóa sự cố/công việc cần cập nhật.",
            },
            "action": {
                "type": "string",
                "enum": ["IN_PROGRESS", "RESOLVED", "CLOSED"],
                "description": "Hành động: IN_PROGRESS (đang xử lý/bổ sung tiến độ), RESOLVED/CLOSED (đã khắc phục/nghiệm thu đóng dứt điểm).",
            },
            "notes": {
                "type": "string",
                "description": "Nội dung ghi chú mới hoặc tiến độ xử lý hiện trường vừa thực hiện.",
            },
            "resolution_notes": {
                "type": "string",
                "description": "Ghi chú kết luận nghiệm thu khi đóng việc / đóng sự cố.",
            },
            "zone_id": {
                "type": "string",
                "description": "Khu vực xảy ra sự cố/công việc.",
            },
        },
        "required": [],
    },
}
CREATE_PRODUCT_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_product",
    "description": (
        "Tạo mới một vật tư, giống cây trồng, phân bón hoặc sản phẩm MỚI vào danh mục quản lý chung (từ điển mặt hàng).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng muốn định danh một mặt hàng mới chưa từng có trong hệ thống (tên gọi, đơn vị tính, phân loại).\n"
        "- Từ khóa nhận diện: 'thêm mặt hàng mới', 'tạo sản phẩm mới', 'định danh giống mới', 'khai báo thuốc mới', 'thêm vật tư mới'.\n"
        "- Ví dụ: 'Tạo sản phẩm Phân Hữu Cơ Vi Sinh Quế Lâm đơn vị bao 50kg', 'Thêm giống Dưa Lưới Huỳnh Long vào danh mục vật tư'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi ghi nhận nhập/xuất kho mặt hàng đã có sẵn (dùng create_inventory_transaction).\n"
        "- KHÔNG dùng khi ghi nhật ký sử dụng vật tư (dùng create_production_log)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Tên vật tư hoặc sản phẩm (ví dụ: Phân NPK Đầu Trâu 20-20-15, Giống Dưa Lưới TL3).",
            },
            "sku": {
                "type": "string",
                "description": "Mã SKU quản lý kho (tùy chọn, sẽ tự sinh nếu bỏ trống).",
            },
            "base_unit_id": {
                "type": "integer",
                "description": "ID đơn vị tính cơ sở.",
            },
            "item_type": {
                "type": "string",
                "enum": ["TOOL", "SEED", "FERTILIZER", "PESTICIDE", "FEED", "CONSUMABLE", "HARVEST_OUTPUT", "OTHER"],
                "description": "Phân loại vật tư.",
            },
            "description": {
                "type": "string",
                "description": "Mô tả quy cách, công dụng.",
            },
        },
        "required": ["name", "base_unit_id"],
    },
}

CREATE_PRODUCTION_CYCLE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "create_production_cycle",
    "description": (
        "Tạo vụ mùa hoặc chu kỳ canh tác / nuôi trồng mới tại một khu vực cụ thể (ngày xuống giống, giống cây, dự kiến thu hoạch).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng bắt đầu triển khai một vụ canh tác mới (xuống giống đợt mới, thả lứa cá mới, bắt đầu chu kỳ mới).\n"
        "- ĐỒNG THỜI TỰ ĐỘNG KÍCH HOẠT KHI NHẬN CON GIỐNG HOẶC CÂY GIỐNG VỀ TRANG TRẠI (ví dụ: 'Vừa nhận 200 con gà giống Ri lai từ trại giống Ba Vì giao tới Chuồng 1', 'Mới lấy 50 cây cam giống về trồng khu B').\n"
        "- Từ khóa nhận diện: 'vụ mùa mới', 'bắt đầu vụ', 'xuống giống vụ...', 'thả lứa giống mới', 'nhận con giống', 'nhận cây giống', 'bắt đầu nuôi...'.\n"
        "- Ví dụ: 'Bắt đầu vụ dưa lưới Tết 2026 tại nhà màng 1 từ ngày mai', 'Khai báo vụ cam xoàn mùa thu ở khu C giống F1'.\n"
        "[KIỂM TRA ĐÃ TỒN TẠI TRƯỚC KHI TẠO / DEDUPLICATION CHECK]:\n"
        "- Trước khi gọi create_production_cycle, luôn kiểm tra xem khu vực (zone_id) đã có vụ mùa nào đang hoạt động (status='ACTIVE') hay chưa bằng tool search_production_cycle.\n"
        "- Nếu khu vực đã có chu kỳ active cùng giống vừa tạo, không tạo mới mà bổ sung số lượng giống vào chu kỳ hiện tại.\n"
        "- Nếu khu vực đang có vụ mùa khác chưa dọn, cảnh báo người dùng trước khi tạo đè.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng cho việc ghi nhật ký hoạt động hàng ngày trong vụ (dùng create_production_log).\n"
        "- KHÔNG dùng khi chỉ tạo lô đất/khu vực (dùng create_new_zone)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "zone_id": {
                "type": "string",
                "description": "Mã khu vực canh tác vụ mùa.",
            },
            "name": {
                "type": "string",
                "description": "Tên vụ mùa (ví dụ: Vụ Dưa Lưới Tết 2026, Vụ Cam Xoàn Mùa Thu).",
            },
            "subject_name": {
                "type": "string",
                "description": "Đối tượng nuôi trồng (Dưa lưới, Cam xoàn, Cá rô phi).",
            },
            "variety": {
                "type": "string",
                "description": "Giống cây con cụ thể (TL3, Kim Cô Nương, F1...).",
            },
            "start_date": {
                "type": "string",
                "description": "Ngày bắt đầu xuống giống / thả giống (YYYY-MM-DD).",
            },
            "expected_end_date": {
                "type": "string",
                "description": "Ngày dự kiến thu hoạch (YYYY-MM-DD).",
            },
            "notes": {
                "type": "string",
                "description": "Ghi chú kế hoạch vụ mùa.",
            },
        },
        "required": ["zone_id", "name", "subject_name"],
    },
}

GET_DATA_WITH_PENDING_APPLIED_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "get_data_with_pending_applied",
    "description": (
        "Truy vấn dữ liệu từ cơ sở dữ liệu và tự động cập nhật tuần tự với các sự kiện đang chờ duyệt (pending) "
        "theo thứ tự thời gian chuẩn SQL (INSERT, UPDATE, DELETE). Dữ liệu trả về ở dạng hợp nhất và sạch sẽ, "
        "phản ánh trạng thái thực tế mới nhất của trang trại để AI phân tích, trả lời câu hỏi hoặc lập báo cáo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "table": {
                "type": "string",
                "description": "Tên bảng dữ liệu cần lấy.",
            },
            "conditions": {
                "type": "object",
                "description": "Bộ lọc điều kiện tùy chọn dạng key-value.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "order_by": {
                "type": "string",
                "description": "Cột và chiều sắp xếp dữ liệu.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
        "required": ["table"],
    },
}

SEARCH_ZONE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_zone",
    "description": (
        "Tra cứu, tìm kiếm danh sách và thông tin các khu vực, lô đất, nhà màng, chuồng trại trong trang trại "
        "(kết hợp dữ liệu database và sự kiện pending mới nhất chưa duyệt).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi hoặc yêu cầu xem danh sách các khu vực, kiểm tra diện tích, hiện trạng canh tác.\n"
        "- Từ khóa nhận diện: 'cho xem các khu vực', 'danh sách vườn', 'tìm khu A', 'khu vực nào trồng dưa lưới', 'diện tích vườn cam', 'kiểm tra lô đất'.\n"
        "- Ví dụ: 'Cho xem danh sách các khu vực hiện có', 'Kiểm tra thông tin khu A xem diện tích bao nhiêu', 'Tìm các khu vực trồng trọt'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi khai báo khu vực mới (dùng create_new_zone)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "zone_id": {
                "type": "string",
                "description": "Mã định danh khu vực cần tìm (ví dụ: 'ZONE_A', 'ZONE_VUON_CAM').",
            },
            "sector": {
                "type": "string",
                "enum": ["CROP", "LIVESTOCK", "AQUACULTURE", "MIXED"],
                "description": "Lọc theo mảng sản xuất.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm theo tên khu vực, địa chỉ hoặc ghi chú.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_CATEGORY_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_category",
    "description": (
        "Tra cứu, tìm kiếm danh mục phân loại vật tư, sản phẩm, hàng hóa trong trang trại (kèm pending mới nhất).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng muốn xem danh sách các loại danh mục, tìm mã/tên danh mục vật tư.\n"
        "- Từ khóa nhận diện: 'xem danh mục', 'tìm danh mục phân bón', 'danh mục thuốc', 'các loại danh mục', 'phân loại hàng hóa'.\n"
        "- Ví dụ: 'Trong hệ thống có những danh mục vật tư nào?', 'Tìm danh mục thuốc trừ sâu'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi tìm sản phẩm/mặt hàng cụ thể (dùng search_product)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category_id": {
                "type": "integer",
                "description": "ID danh mục cần tìm.",
            },
            "name": {
                "type": "string",
                "description": "Tên danh mục.",
            },
            "code": {
                "type": "string",
                "description": "Mã code danh mục.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm theo tên hoặc mô tả.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_UNIT_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_unit",
    "description": (
        "Tra cứu, tìm kiếm các đơn vị tính được quản lý trong hệ thống (kg, bao, lít, chai, thùng, tấn...).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng cần tra cứu ID hoặc danh sách đơn vị tính để chọn khi nhập xuất kho hoặc lập sản phẩm.\n"
        "- Từ khóa nhận diện: 'xem đơn vị tính', 'tìm đơn vị kg', 'đơn vị tính bao có mã gì', 'danh sách đơn vị'.\n"
        "- Ví dụ: 'Đơn vị tính cho phân bón có những gì?', 'Tìm đơn vị đo lường thể tích'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi tra cứu sản phẩm hay kho hàng."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "unit_id": {
                "type": "integer",
                "description": "ID đơn vị tính.",
            },
            "code": {
                "type": "string",
                "description": "Ký hiệu đơn vị (ví dụ: 'kg', 'bao', 'lit').",
            },
            "name": {
                "type": "string",
                "description": "Tên đơn vị tính.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_SUPPLIER_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_supplier",
    "description": (
        "Tra cứu, tìm kiếm thông tin nhà cung cấp vật tư, giống cây, phân bón hoặc đối tác dịch vụ nông nghiệp.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi thông tin, số điện thoại, địa chỉ hoặc danh sách các đại lý, nhà cung cấp.\n"
        "- Từ khóa nhận diện: 'tìm đại lý', 'số điện thoại nhà cung cấp', 'danh sách nhà cung cấp', 'đại lý nào bán giống', 'liên hệ nhà cung cấp'.\n"
        "- Ví dụ: 'Cho tôi số điện thoại đại lý vật tư nông nghiệp Năm Lúa', 'Danh sách các nhà cung cấp phân bón hiện tại'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi ghi nhận giao dịch chi tiền mua hàng (dùng create_financial_transaction)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "supplier_id": {
                "type": "integer",
                "description": "ID nhà cung cấp.",
            },
            "name": {
                "type": "string",
                "description": "Tên nhà cung cấp / đại lý.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm theo tên, số điện thoại hoặc địa chỉ.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_WAREHOUSE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_warehouse",
    "description": (
        "Tra cứu, tìm kiếm thông tin các kho hàng, kho vật tư, kho nông sản trong trang trại.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi về danh sách các kho hàng, vị trí kho hoặc mã kho để xuất/nhập vật tư.\n"
        "- Từ khóa nhận diện: 'có những kho nào', 'danh sách kho', 'tìm kho trung tâm', 'kho phân bón ở đâu', 'thông tin kho'.\n"
        "- Ví dụ: 'Trang trại hiện có những kho hàng nào?', 'Tìm thông tin kho chứa vật tư khu A'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi kiểm tra giao dịch biến động nhập xuất kho (dùng search_inventory_transaction)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "warehouse_id": {
                "type": "integer",
                "description": "ID kho hàng.",
            },
            "warehouse_type": {
                "type": "string",
                "description": "Phân loại kho.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm tên kho hoặc mã kho.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_PRODUCT_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_product",
    "description": (
        "Tra cứu, tìm kiếm danh mục sản phẩm, vật tư nông nghiệp, phân bón, thuốc BVTV, giống cây trong trang trại.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng cần tìm thông tin vật tư, mã SKU, quy cách hoặc xem danh sách sản phẩm hiện có.\n"
        "- Từ khóa nhận diện: 'tìm phân NPK', 'thuốc diệt rầy có những loại nào', 'danh sách giống cây', 'mã vật tư', 'tra cứu sản phẩm'.\n"
        "- Ví dụ: 'Tìm xem có loại phân bón hữu cơ nào trong danh mục', 'Kiểm tra mã giống dưa lưới TL3'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi khai báo sản phẩm mới (dùng create_product)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "ID sản phẩm.",
            },
            "item_type": {
                "type": "string",
                "enum": ["TOOL", "SEED", "FERTILIZER", "PESTICIDE", "FEED", "CONSUMABLE", "HARVEST_OUTPUT", "OTHER"],
                "description": "Phân loại vật tư/sản phẩm.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm theo tên hoặc mã SKU.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_TASK_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_task",
    "description": (
        "Tra cứu, kiểm tra danh sách công việc, nhiệm vụ cần làm trong trang trại (kèm cập nhật pending mới nhất).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi xem có việc gì cần làm, kiểm tra hạn chót, tiến độ hoặc danh sách công việc theo độ ưu tiên.\n"
        "- Từ khóa nhận diện: 'có việc gì chưa làm', 'danh sách công việc', 'hôm nay cần làm gì', 'việc nào khẩn cấp', 'kiểm tra tiến độ công việc'.\n"
        "- Ví dụ: 'Hiện tại có những công việc nào chưa hoàn thành?', 'Xem danh sách công việc ưu tiên cao (HIGH)'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi giao việc mới (dùng create_task)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["TODO", "IN_PROGRESS", "IN_REVIEW", "DONE", "CANCELLED"],
                "description": "Trạng thái công việc.",
            },
            "priority": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"],
                "description": "Mức độ ưu tiên.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm theo tiêu đề hoặc mô tả công việc.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_ISSUE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_issue",
    "description": (
        "Tra cứu, kiểm tra danh sách sự cố, sâu bệnh, dịch hại hoặc hư hỏng thiết bị trên trang trại (kèm pending mới nhất).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi tình hình sự cố, sâu bệnh ở các khu vực, kiểm tra xem có máy móc nào bị hỏng không.\n"
        "- Từ khóa nhận diện: 'khu A có sâu bệnh gì', 'danh sách sự cố chưa xử lý', 'có máy bơm nào hỏng không', 'tình hình dịch hại', 'kiểm tra sự cố'.\n"
        "- Ví dụ: 'Cho tôi xem danh sách sự cố gần đây ở khu A', 'Có sự cố nghiêm trọng (CRITICAL) nào đang mở không?'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi báo cáo sự cố mới phát hiện (dùng create_issue)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "zone_id": {
                "type": "string",
                "description": "Mã khu vực cần kiểm tra sự cố (ví dụ: 'ZONE_A').",
            },
            "severity": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                "description": "Mức độ nghiêm trọng của sự cố.",
            },
            "status": {
                "type": "string",
                "enum": ["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"],
                "description": "Trạng thái sự cố.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm theo tiêu đề hoặc mô tả sự cố.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_PRODUCTION_CYCLE_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_production_cycle",
    "description": (
        "Tra cứu thông tin các vụ mùa, chu kỳ canh tác / nuôi trồng đang diễn ra hoặc đã hoàn thành tại các khu vực.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi về vụ mùa hiện tại, giống cây đang trồng, ngày dự kiến thu hoạch.\n"
        "- Từ khóa nhận diện: 'khu A đang trồng vụ gì', 'vụ dưa lưới bắt đầu khi nào', 'khi nào thu hoạch vụ cam', 'danh sách vụ mùa'.\n"
        "- Ví dụ: 'Kiểm tra xem vụ dưa lưới Tết bắt đầu từ ngày nào?', 'Các vụ mùa đang hoạt động (ACTIVE) trong vườn'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi khai báo vụ mùa mới (dùng create_production_cycle)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "zone_id": {
                "type": "string",
                "description": "Mã khu vực.",
            },
            "status": {
                "type": "string",
                "enum": ["PLANNED", "ACTIVE", "COMPLETED", "CANCELLED"],
                "description": "Trạng thái vụ mùa.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm tên vụ hoặc giống cây.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_PRODUCTION_LOG_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_production_log",
    "description": (
        "Tra cứu nhật ký hoạt động sản xuất, canh tác hàng ngày (tưới nước, bón phân, xịt thuốc...) đã thực hiện.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi về lịch sử chăm sóc, lần gần nhất bón phân/tưới nước, lượng vật tư đã dùng.\n"
        "- Từ khóa nhận diện: 'lần cuối bón phân khi nào', 'nhật ký canh tác khu A', 'hôm qua đã làm những gì', 'đã xịt thuốc gì rồi'.\n"
        "- Ví dụ: 'Kiểm tra xem vụ cam đợt rồi đã bón phân mấy lần?', 'Xem nhật ký tưới nước tuần này'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi báo cáo việc vừa làm xong hôm nay (dùng create_production_log)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cycle_id": {
                "type": "integer",
                "description": "ID vụ mùa.",
            },
            "activity_type": {
                "type": "string",
                "description": "Loại hoạt động canh tác (FERTILIZING, IRRIGATION, PEST_CONTROL...).",
            },
            "log_date": {
                "type": "string",
                "description": "Ngày thực hiện (YYYY-MM-DD).",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm trong nhật ký.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_HARVEST_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_harvest",
    "description": (
        "Tra cứu lịch sử và sản lượng các đợt thu hoạch nông sản / thủy sản từ các vụ mùa.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi về sản lượng thu hoạch, các đợt hái trái, cắt tỉa gần đây.\n"
        "- Từ khóa nhận diện: 'đã thu hoạch được bao nhiêu tấn cam', 'các đợt cắt dưa vừa rồi', 'sản lượng thu hoạch vụ tết'.\n"
        "- Ví dụ: 'Vụ cam vừa rồi thu hoạch được tổng cộng bao nhiêu tấn?', 'Cho xem đợt thu hoạch gần nhất'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi ghi nhận đợt thu hoạch vừa hoàn thành (dùng create_harvest)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cycle_id": {
                "type": "integer",
                "description": "ID vụ mùa.",
            },
            "harvest_type": {
                "type": "string",
                "enum": ["MAIN", "PARTIAL", "FINAL"],
                "description": "Hình thức thu hoạch.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_INVENTORY_TRANSACTION_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_inventory_transaction",
    "description": (
        "Tra cứu lịch sử biến động kho hàng (nhập kho, xuất kho, điều chuyển, hủy hàng hỏng).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi về lịch sử nhập xuất vật tư, kiểm tra gần đây đã nhập thêm phân bón nào chưa.\n"
        "- Từ khóa nhận diện: 'lịch sử nhập kho', 'đã xuất bao nhiêu bao vôi', 'kho vừa nhập những gì', 'kiểm tra giao dịch kho'.\n"
        "- Ví dụ: 'Kiểm tra xem tháng này đã nhập bao nhiêu bao phân NPK?', 'Lịch sử xuất kho cho khu B'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi thực hiện giao dịch kho mới (dùng create_inventory_transaction)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "ID sản phẩm/vật tư.",
            },
            "warehouse_id": {
                "type": "integer",
                "description": "ID kho.",
            },
            "transaction_type": {
                "type": "string",
                "description": "Loại giao dịch kho (RECEIPT, ISSUE_PRODUCTION...).",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm ghi chú giao dịch.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_FINANCIAL_TRANSACTION_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_financial_transaction",
    "description": (
        "Tra cứu lịch sử thu chi tài chính, các khoản tiền đã thanh toán hoặc tiền bán nông sản đã thu về.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi về dòng tiền, tổng chi tiêu, tiền đã trả cho đại lý hoặc tiền bán hàng thu về.\n"
        "- Từ khóa nhận diện: 'tháng này chi bao nhiêu tiền', 'đã trả bao nhiêu tiền phân', 'tiền bán cam thu được bao nhiêu', 'xem sổ thu chi'.\n"
        "- Ví dụ: 'Hôm nay đã thu chi những khoản nào?', 'Xem các khoản chi trả tiền công nhân'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi ghi nhận giao dịch thu chi mới phát sinh (dùng create_financial_transaction)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["INCOME", "EXPENSE"],
                "description": "Loại thu/chi.",
            },
            "category_id": {
                "type": "integer",
                "description": "ID danh mục thu chi.",
            },
            "partner_name": {
                "type": "string",
                "description": "Tên đối tác hoặc khách hàng.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm nội dung giao dịch.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_COLLABORATOR_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_collaborator",
    "description": (
        "Tra cứu danh sách nhân sự, nhân công, người cộng tác hoặc quản lý trong nông trại.\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng hỏi thông tin nhân công, tìm số telegram_id, vai trò hoặc danh sách nhân viên.\n"
        "- Từ khóa nhận diện: 'danh sách nhân công', 'anh Ba có vai trò gì', 'ai đang phụ trách', 'tìm người cộng tác'.\n"
        "- Ví dụ: 'Danh sách nhân công đang hoạt động trong vườn', 'Tìm thông tin nhân viên tên Ba'.\n"
        "[WHEN NOT TO USE / TRÁNH DÙNG KHI]:\n"
        "- KHÔNG dùng khi khai báo nhân sự mới (dùng create_collaborator)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": ["OWNER", "ADMIN", "WORKER", "VIEWER"],
                "description": "Vai trò.",
            },
            "full_name": {
                "type": "string",
                "description": "Họ và tên nhân sự.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi (mặc định False).",
            },
        },
    },
}

SEARCH_DICTIONARY_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_dictionary",
    "description": (
        "Tra cứu toàn diện từ điển nông trại hợp nhất (bao gồm cả danh mục vật tư, cây trồng, phân bón và các kho bãi/chòi chứa).\n"
        "[TRIGGER CONDITION / KHI NÀO DÙNG]:\n"
        "- Kích hoạt khi người dùng muốn tra cứu danh mục, tìm mã vật tư hoặc tìm thông tin kho bãi/điểm lưu trữ.\n"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "dict_id": {
                "type": "integer",
                "description": "ID mục từ điển.",
            },
            "code": {
                "type": "string",
                "description": "Mã code của mục từ điển.",
            },
            "name": {
                "type": "string",
                "description": "Tên mục từ điển.",
            },
            "entry_type": {
                "type": "string",
                "enum": ["CATEGORY", "LOCATION", "SERVICE", "OTHER"],
                "description": "Phân loại: CATEGORY (vật tư/hàng hóa) hoặc LOCATION (kho bãi/điểm lưu trữ).",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm theo tên hoặc bí danh khẩu ngữ.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa cần lấy.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Nếu True, trả về trực tiếp danh sách bản ghi.",
            },
        },
    },
}

SEARCH_BARTER_TRANSACTION_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_barter_transaction",
    "description": "Tra cứu lịch sử các giao dịch trao đổi hàng hóa trực tiếp phi tiền tệ.",
    "parameters": {
        "type": "object",
        "properties": {
            "partner_name": {
                "type": "string",
                "description": "Tên đối tác đổi hàng.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Trả về dạng list nếu True.",
            },
        },
    },
}

SEARCH_DEBT_RECORD_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_debt_record",
    "description": "Tra cứu sổ theo dõi công nợ (nợ phải trả đại lý vật tư hoặc nợ phải thu từ thương lái).",
    "parameters": {
        "type": "object",
        "properties": {
            "debt_type": {
                "type": "string",
                "enum": ["PAYABLE", "RECEIVABLE"],
                "description": "Loại nợ: PAYABLE (phải trả) hoặc RECEIVABLE (phải thu).",
            },
            "partner_name": {
                "type": "string",
                "description": "Tên chủ nợ hoặc con nợ.",
            },
            "status": {
                "type": "string",
                "enum": ["UNPAID", "PARTIAL", "SETTLED", "CANCELLED"],
                "description": "Trạng thái nợ.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Trả về dạng list nếu True.",
            },
        },
    },
}

SEARCH_RUNNING_TASK_TOOL: Dict[str, Any] = {
    "type": "function",
    "name": "search_running_task",
    "description": "Tra cứu các phiên công việc thực địa hôm nay hoặc trong vụ mùa.",
    "parameters": {
        "type": "object",
        "properties": {
            "cycle_id": {
                "type": "integer",
                "description": "ID vụ mùa.",
            },
            "status": {
                "type": "string",
                "enum": ["TODO", "IN_PROGRESS", "DONE", "SKIPPED", "CANCELLED"],
                "description": "Trạng thái công việc.",
            },
            "keyword": {
                "type": "string",
                "description": "Từ khóa tìm kiếm tiêu đề công việc.",
            },
            "limit": {
                "type": "integer",
                "description": "Số lượng bản ghi tối đa.",
            },
            "as_list": {
                "type": "boolean",
                "description": "Trả về dạng list nếu True.",
            },
        },
    },
}


# ==============================================================================
# ALL REGISTERED TOOLS
# ==============================================================================

ALL_TOOLS: List[Dict[str, Any]] = [
    # Creation and Operation tools
    CREATE_NEW_ZONE_TOOL,
    CREATE_TASK_TOOL,
    COMPLETE_RUNNING_TASK_TOOL,
    CREATE_PRODUCTION_CYCLE_TOOL,
    CREATE_PRODUCTION_LOG_TOOL,
    CREATE_HARVEST_TOOL,
    CREATE_INVENTORY_TRANSACTION_TOOL,
    CREATE_FINANCIAL_TRANSACTION_TOOL,
    RECORD_BARTER_EXCHANGE_TOOL,
    PROCESS_DEBT_PAYMENT_TOOL,
    CREATE_ISSUE_TOOL,
    MANAGE_ISSUE_TOOL,
    CREATE_PRODUCT_TOOL,
    # Domain-specific search tools replacing generic data retrieval
    SEARCH_ZONE_TOOL,
    SEARCH_DICTIONARY_TOOL,
    SEARCH_CATEGORY_TOOL,
    SEARCH_UNIT_TOOL,
    SEARCH_SUPPLIER_TOOL,
    SEARCH_WAREHOUSE_TOOL,
    SEARCH_PRODUCT_TOOL,
    SEARCH_TASK_TOOL,
    SEARCH_RUNNING_TASK_TOOL,
    SEARCH_ISSUE_TOOL,
    SEARCH_PRODUCTION_CYCLE_TOOL,
    SEARCH_PRODUCTION_LOG_TOOL,
    SEARCH_HARVEST_TOOL,
    SEARCH_INVENTORY_TRANSACTION_TOOL,
    SEARCH_FINANCIAL_TRANSACTION_TOOL,
    SEARCH_BARTER_TRANSACTION_TOOL,
    SEARCH_DEBT_RECORD_TOOL,
    SEARCH_COLLABORATOR_TOOL,
]


def dict_to_function_declaration(tool_dict: Dict[str, Any]) -> types.FunctionDeclaration:
    """Converts OpenAI tool dict into Google GenAI FunctionDeclaration."""
    d = tool_dict.get("function", tool_dict)
    name = d["name"]
    description = d.get("description", "")
    parameters = d.get("parameters", {})
    return types.FunctionDeclaration(
        name=name,
        description=description,
        parameters=parameters,
    )


def get_genai_tools(tools_list: Optional[List[Dict[str, Any]]] = None) -> List[types.Tool]:
    """Generates a list of Google GenAI Tool objects from the tool definitions."""
    tools = tools_list if tools_list is not None else ALL_TOOLS
    declarations = [dict_to_function_declaration(t) for t in tools]
    return [types.Tool(function_declarations=declarations)]
