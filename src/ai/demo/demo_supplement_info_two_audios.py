"""AgriVoice-AI: Multi-Audio Conversation & Information Supplement Demo.

Minh họa quy trình thực tế:
1. Audio 1: Nông dân gửi khẩu lệnh ban đầu nhưng còn thiếu thông tin cụ thể (mã vụ, lượng vật tư...).
2. AI Lượt 1: Ghi nhận sơ bộ và chỉ rõ mục [Thông tin cần làm rõ].
3. Audio 2: Nông dân gửi tiếp file ghi âm thứ 2 bổ sung thông tin còn thiếu.
4. AI Lượt 2: Kế thừa ngữ cảnh Lượt 1, tổng hợp thông tin, gọi đầy đủ công cụ và hoàn tất ghi nhận.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(WORKSPACE_ROOT / ".env")
except ImportError:
    pass

from src.ai.harness import GenAIHarness


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def run_two_audio_demo(audio1_path: Path, audio2_path: Path):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 75}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}🌾 DEMO AGRIVOICE-AI: NHÀ NÔNG BỔ SUNG THÔNG TIN QUA 2 FILE GHI ÂM LIÊN TIẾP{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 75}{Colors.RESET}\n")

    harness = GenAIHarness()

    # --------------------------------------------------------------------------
    # LƯỢT 1: Audio ban đầu
    # --------------------------------------------------------------------------
    print(f"{Colors.BOLD}{Colors.YELLOW}▶ LƯỢT 1: NÔNG DÂN GỬI AUDIO KHẨU LỆNH BAN ĐẦU{Colors.RESET}")
    print(f"  • File: {audio1_path.name}")
    print(f"  ⏳ AI đang phân tích âm thanh lượt 1...")
    t0 = time.time()
    res1 = harness.process_voice(audio1_path, auto_stage=False)
    el1 = round(time.time() - t0, 3)

    print(f"\n{Colors.BOLD}🤖 PHẢN HỒI CỦA AI (LƯỢT 1 - {el1}s):{Colors.RESET}")
    print(f"{Colors.BOLD}{res1.reply_text}{Colors.RESET}")
    if res1.records_created:
        print(f"\n{Colors.YELLOW}📋 Các bản ghi sơ bộ đã tạo ({len(res1.records_created)}):{Colors.RESET}")
        for r in res1.records_created:
            print(f"   + [{r.__class__.__name__}]: {r.__dict__}")

    # --------------------------------------------------------------------------
    # LƯỢT 2: Audio bổ sung thông tin
    # --------------------------------------------------------------------------
    print(f"\n{Colors.CYAN}{'-' * 75}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.YELLOW}▶ LƯỢT 2: NÔNG DÂN GỬI AUDIO THỨ 2 BỔ SUNG THÔNG TIN{Colors.RESET}")
    print(f"  • File: {audio2_path.name}")
    print(f"  ⏳ AI đang kế thừa ngữ cảnh Lượt 1 và phân tích âm thanh Lượt 2...")

    t1 = time.time()
    res2 = harness.process_voice(
        audio=audio2_path,
        conversation_history=res1.history,
        auto_stage=False,
    )
    el2 = round(time.time() - t1, 3)

    print(f"\n{Colors.BOLD}🤖 PHẢN HỒI CỦA AI (LƯỢT 2 - TỔNG HỢP SAU KHI BỔ SUNG - {el2}s):{Colors.RESET}")
    print(f"{Colors.BOLD}{res2.reply_text}{Colors.RESET}")

    if res2.records_created:
        print(f"\n{Colors.BOLD}{Colors.GREEN}📋 TỔNG HỢP TOÀN BỘ CÁC BẢN GHI ĐÃ ĐƯỢC TẠO HOÀN CHỈNH ({len(res2.records_created)}):{Colors.RESET}")
        for idx, r in enumerate(res2.records_created, start=1):
            clean_fields = {k: v for k, v in r.__dict__.items() if v is not None and k not in ("created_at", "updated_at")}
            print(f"  {idx}. [{r.__class__.__name__}]: {clean_fields}")

    print(f"\n{Colors.BOLD}{Colors.GREEN}{'=' * 75}")
    print(f"✓ ĐÃ HOÀN TẤT DEMO 2 AUDIO THÀNH CÔNG!")
    print(f"{'=' * 75}{Colors.RESET}\n")


def main():
    default_a1 = WORKSPACE_ROOT / "data" / "audio_2026-10-15_20-18-02.ogg"
    default_a2 = WORKSPACE_ROOT / "data" / "audio_2026-10-15_20-20-22.ogg"

    if len(sys.argv) >= 3:
        a1 = Path(sys.argv[1]).expanduser().resolve()
        a2 = Path(sys.argv[2]).expanduser().resolve()
    else:
        a1 = default_a1
        a2 = default_a2

    if not a1.exists():
        print(f"{Colors.RED}❌ Không tìm thấy file 1: {a1}{Colors.RESET}")
        sys.exit(1)
    if not a2.exists():
        print(f"{Colors.RED}❌ Không tìm thấy file 2: {a2}{Colors.RESET}")
        sys.exit(1)

    run_two_audio_demo(a1, a2)


if __name__ == "__main__":
    main()
