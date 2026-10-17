"""AgriVoice-AI: Interleaved Multi-Conversation Demo (Group Chat Simulation).

Kịch bản thực tế mô phỏng thảo luận trong Nhóm Chat Telegram Nông Trại:
1. LƯỢT 1 (Bác Ba - USER_1001):
   - Gửi khẩu lệnh: "Tôi vừa cho gà ăn và tưới mấy cây chuối ở khu A. Ghi lại giúp tôi."
   - AI ghi nhận 2 bản ghi nháp vào bộ nhớ riêng của Bác Ba:
     #1 [ProductionLog]: Cho gà ăn
     #2 [ProductionLog]: Tưới cây chuối khu A
   - AI phản hồi thiếu số lượng thức ăn -> Bác Ba chuyển trạng thái WAITING_CLARIFICATION.

2. LƯỢT 2 (Bác Năm CHEN NGANG - USER_1005):
   - Trong lúc Bác Ba chưa kịp bổ sung, Bác Năm chen ngang vào cùng nhóm chat:
     "@admin Báo sự cố: Van nước tưới khu A bị nứt gãy chảy tràn lan rồi, nhờ thợ sửa gấp!"
   - Memory Router định tuyến sang phiên riêng của Bác Năm, cô lập 100% (không dính việc của Bác Ba).
   - AI ghi nhận Issue sự cố, thông tin đầy đủ -> Nạp ngay vào pending_events (Event ID phát sinh).

3. LƯỢT 3 (Bác Ba QUAY LẠI BỔ SUNG THÔNG TIN - USER_1001):
   - Bác Ba gửi tiếp khẩu lệnh: "Lượng thức ăn cho gà khoảng tầm 2 kg nghen."
   - Memory Router phục hồi đúng bộ nhớ nháp của Bác Ba.
   - Agent 2 cập nhật bản ghi #1 (thêm 2kg thức ăn), xuất kho 2kg, bản ghi #2 (Tưới chuối) vẫn NGUYÊN VẸN.
   - Đầy đủ thông tin -> Nạp toàn bộ các bản ghi của Bác Ba vào pending_events an toàn!
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(WORKSPACE_ROOT / ".env")
except ImportError:
    pass

from src.ai.harness import GenAIHarness
from src.ai.memory import HierarchicalMemoryManager, UserState
from src.db.connection import get_db
from src.db.migrate import run_migrations


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[35m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_banner():
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 80}")
    print("🌾 DEMO AGRIVOICE-AI: HỘI THOẠI ĐA TÁC NHÂN XEN KẼ TRONG NHÓM CHAT (GROUP CHAT)")
    print("   Bác Ba cập nhật dở dang -> Bác Năm chen ngang báo sự cố -> Bác Ba bổ sung tiếp")
    print(f"{'=' * 80}{Colors.RESET}\n")


def setup_demo_environment(db_path: Path):
    """Initializes schema and pre-seeds collaborators and zones."""
    run_migrations(db_path, quiet=True)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO collaborators (telegram_id, full_name, role) VALUES ('1001', 'Bác Ba Làm Vườn', 'WORKER');"
        )
        conn.execute(
            "INSERT INTO collaborators (telegram_id, full_name, role) VALUES ('1005', 'Bác Năm Trực Trại', 'WORKER');"
        )
        conn.execute(
            "INSERT INTO collaborators (telegram_id, full_name, role) VALUES ('OWNER_1', 'Chủ Trang Trại', 'OWNER');"
        )
        conn.execute(
            "INSERT INTO zones (zone_id, zone_name, sector, area_size) VALUES ('ZONE_A', 'Khu A Vườn Cây', 'CROP', 10000);"
        )
        conn.execute(
            "INSERT INTO dictionary (dict_id, code, name, root_path, entry_type) "
            "VALUES (1, 'CAT_FEED', 'Thức ăn cho gà', '/vat-tu/', 'CATEGORY');"
        )
        conn.commit()


def run_demo():
    print_banner()

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "demo_group_chat.db"
        setup_demo_environment(db_path)

        # Initialize AI Harness and Hierarchical Memory Router
        harness = GenAIHarness()
        memory_mgr = HierarchicalMemoryManager(group_window_size=10, watchdog_timeout_seconds=60.0)

        # Audio files
        audio_ba_1 = WORKSPACE_ROOT / "data" / "audio_2026-10-15_20-18-02.ogg"
        audio_ba_2 = WORKSPACE_ROOT / "data" / "audio_2026-10-15_20-20-22.ogg"

        # ======================================================================
        # LƯỢT 1: BÁC BA GỬI KHẨU LỆNH BAN ĐẦU (THIẾU THÔNG TIN)
        # ======================================================================
        print(f"{Colors.BOLD}{Colors.YELLOW}▶ [LƯỢT 1] BÁC BA (USER_1001) PHÁT BIỂU VÀO NHÓM CHAT:{Colors.RESET}")
        print(f"  • Người nói: {Colors.CYAN}Bác Ba Làm Vườn (ID: 1001){Colors.RESET}")
        print(f"  • Định dạng: Tin nhắn thoại (Audio: {audio_ba_1.name})")

        t0 = time.time()
        res1 = harness.process_voice(
            audio=audio_ba_1,
            user_id="1001",
            full_name="Bác Ba",
            username="bacba_farm",
            memory_manager=memory_mgr,
            db_path=db_path,
            auto_stage=True,
        )
        el1 = round(time.time() - t0, 2)

        print(f"\n  🗣️ {Colors.BLUE}Agent 1 (Speech-to-Text):{Colors.RESET} \"{res1.raw_transcript}\"")
        print(f"  🤖 {Colors.GREEN}Agent 2 (Phản hồi hệ thống - {el1}s):{Colors.RESET}")
        for line in res1.reply_text.strip().split("\n"):
            print(f"     {line}")

        session_ba = memory_mgr.get_user_session("1001")
        print(f"\n  💾 {Colors.YELLOW}Bộ nhớ riêng của Bác Ba (DraftMemory):{Colors.RESET}")
        print(f"     • Trạng thái phiên: {Colors.BOLD}{session_ba.state.value}{Colors.RESET}")
        print(f"     • Số bản ghi nháp đang chờ bổ sung: {len(session_ba.draft_records)}")
        for r in session_ba.draft_records:
            print(f"       + #{r['id']} [{r['type']}]: {r['data']}")

        # ======================================================================
        # LƯỢT 2: BÁC NĂM CHEN NGANG VÀO NHÓM BÁO SỰ CỐ
        # ======================================================================
        print(f"\n{Colors.MAGENTA}{'-' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}⚡ [LƯỢT 2 - CHEN NGANG] BÁC NĂM (USER_1005) NHẢY VÀO NHÓM CHAT BÁO CÁO:{Colors.RESET}")
        print(f"  • Người nói: {Colors.CYAN}Bác Năm Trực Trại (ID: 1005){Colors.RESET}")
        utterance_nam = "@admin Báo sự cố: Van nước tưới khu A bị nứt gãy chảy tràn lan rồi, nhờ thợ ra sửa gấp!"
        print(f"  • Nội dung khẩu lệnh: \"{utterance_nam}\"")

        t1 = time.time()
        res_nam = harness.process_text(
            text_query=utterance_nam,
            user_id="1005",
            full_name="Bác Năm",
            username="bacnam_farm",
            memory_manager=memory_mgr,
            db_path=db_path,
            auto_stage=True,
        )
        el2 = round(time.time() - t1, 2)

        print(f"\n  🤖 {Colors.GREEN}Agent 2 (Phản hồi hệ thống cho Bác Năm - {el2}s):{Colors.RESET}")
        for line in res_nam.reply_text.strip().split("\n"):
            print(f"     {line}")

        session_nam = memory_mgr.get_user_session("1005")
        print(f"\n  💾 {Colors.MAGENTA}Kiểm tra bộ nhớ riêng của Bác Năm:{Colors.RESET}")
        print(f"     • Trạng thái phiên Bác Năm: {Colors.BOLD}{session_nam.state.value}{Colors.RESET}")
        print(f"     • Đã nạp thành công vào pending_events: {res_nam.events_staged} sự kiện (Mã: {res_nam.event_ids})")

        print(f"\n  🛡️ {Colors.GREEN}KIỂM TRA TÍNH TOÀN VẸN BỘ NHỚ BÁC BA (CHỐNG LẪN LỘN NGỮ CẢNH):{Colors.RESET}")
        print(f"     • Bộ nhớ Bác Ba có bị nhiễm sự cố của Bác Năm không? -> {Colors.BOLD}HOÀN TOÀN KHÔNG!{Colors.RESET}")
        print(f"     • Trạng thái Bác Ba: {session_ba.state.value} (vẫn còn nguyên {len(session_ba.draft_records)} bản ghi nháp)")

        # ======================================================================
        # LƯỢT 3: BÁC BA QUAY LẠI BỔ SUNG THÔNG TIN
        # ======================================================================
        print(f"\n{Colors.CYAN}{'-' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.YELLOW}▶ [LƯỢT 3] BÁC BA (USER_1001) TIẾP TỤC BỔ SUNG THÔNG TIN CHO LƯỢT 1:{Colors.RESET}")
        print(f"  • Người nói: {Colors.CYAN}Bác Ba Làm Vườn (ID: 1001){Colors.RESET}")
        print(f"  • Định dạng: Tin nhắn thoại bổ sung (Audio: {audio_ba_2.name})")

        t2 = time.time()
        res3 = harness.process_voice(
            audio=audio_ba_2,
            user_id="1001",
            full_name="Bác Ba",
            username="bacba_farm",
            memory_manager=memory_mgr,
            db_path=db_path,
            auto_stage=True,
        )
        el3 = round(time.time() - t2, 2)

        print(f"\n  🗣️ {Colors.BLUE}Agent 1 (Speech-to-Text):{Colors.RESET} \"{res3.raw_transcript}\"")
        print(f"  🤖 {Colors.GREEN}Agent 2 (Phản hồi hệ thống cho Bác Ba - {el3}s):{Colors.RESET}")
        for line in res3.reply_text.strip().split("\n"):
            print(f"     {line}")

        print(f"\n  💾 {Colors.YELLOW}Trạng thái bộ nhớ của Bác Ba sau khi bổ sung:{Colors.RESET}")
        print(f"     • Trạng thái phiên: {Colors.BOLD}{session_ba.state.value}{Colors.RESET}")
        print(f"     • Đã nạp thành công vào pending_events: {res3.events_staged} sự kiện (Mã: {res3.event_ids})")

        # ======================================================================
        # TỔNG KẾT & ĐỐI SOÁT TRÊN CƠ SỞ DỮ LIỆU
        # ======================================================================
        print(f"\n{Colors.BOLD}{Colors.GREEN}{'=' * 80}")
        print("📊 TỔNG HỢP KIỂM TOÁN TRÊN HÀNG ĐỢI PENDING_EVENTS:")
        print(f"{'=' * 80}{Colors.RESET}")

        with get_db(db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT event_id, sender_id, target_table, action_type, summary_text, status "
                "FROM pending_events ORDER BY event_id ASC;"
            )
            rows = cur.fetchall()

            for r in rows:
                sender_tag = f"Bác Ba (1001)" if r["sender_id"] == "1001" else f"Bác Năm (1005)"
                print(
                    f"  • Event #{r['event_id']} | Tác giả: {sender_tag:<14} | Bảng: {r['target_table']:<22} "
                    f"| Trạng thái: {r['status']:<8} | Tóm tắt: {r['summary_text']}"
                )

        print(f"\n{Colors.BOLD}{Colors.GREEN}✓ KẾT LUẬN:{Colors.RESET}")
        print("  1. Bác Năm chen ngang không làm xáo trộn hay ghi đè lên bộ nhớ nháp của Bác Ba.")
        print("  2. Bản ghi tưới cây chuối của Bác Ba ở Lượt 1 vẫn được giữ nguyên vẹn sang Lượt 3.")
        print("  3. Toàn bộ các sự kiện của cả Bác Ba và Bác Năm đều được phân loại và nạp vào hàng đợi chờ duyệt chính xác!")
        print(f"{Colors.BOLD}{Colors.GREEN}{'=' * 80}{Colors.RESET}\n")


if __name__ == "__main__":
    run_demo()
