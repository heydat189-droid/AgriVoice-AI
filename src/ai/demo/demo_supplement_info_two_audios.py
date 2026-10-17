"""AgriVoice-AI: Multi-Audio Conversation & Information Supplement Demo.

Minh họa quy trình thực tế với Kiến trúc 2 Agents:
1. Agent 1 (Speech-to-Text): Chuyển đổi audio sang văn bản nguyên văn.
2. Agent 2 (Reasoning & Draft Memory):
   - Lượt 1: Ghi nhận sơ bộ vào bộ nhớ Draft Memory (python dictionary) và chỉ rõ mục [Thông tin cần làm rõ].
   - Lượt 2: Nông dân gửi file ghi âm thứ 2 bổ sung thông tin. Agent 2 gọi các tool `update_draft_record`
     để chỉnh sửa, bổ sung thông tin vào các bản ghi đã có, KHÔNG LÀM MẤT các bản ghi khác trong bộ nhớ.
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
    print(f"{Colors.BOLD}{Colors.CYAN}🌾 DEMO 2 AGENTS & DRAFT MEMORY: BỔ SUNG THÔNG TIN KHÔNG LÀM MẤT BẢN GHI CŨ{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 75}{Colors.RESET}\n")

    harness = GenAIHarness()
    mem = {"draft_records": []}

    # --------------------------------------------------------------------------
    # LƯỢT 1: Audio ban đầu
    # --------------------------------------------------------------------------
    print(f"{Colors.BOLD}{Colors.YELLOW}▶ LƯỢT 1: NÔNG DÂN GỬI AUDIO KHẨU LỆNH BAN ĐẦU{Colors.RESET}")
    print(f"  • File: {audio1_path.name}")
    t0 = time.time()
    res1 = harness.process_voice(audio1_path, memory=mem, auto_stage=False)
    el1 = round(time.time() - t0, 3)

    print(f"\n{Colors.BOLD}{Colors.BLUE}🗣️ AGENT 1 (SPEECH-TO-TEXT):{Colors.RESET}")
    print(f"  \"{res1.raw_transcript}\"")
    print(f"\n{Colors.BOLD}🤖 AGENT 2 (PHẢN HỒI HỆ THỐNG - {el1}s):{Colors.RESET}")
    print(f"{Colors.BOLD}{res1.reply_text}{Colors.RESET}")

    if res1.records_created:
        print(f"\n{Colors.YELLOW}📋 Các bản ghi trong bộ nhớ Draft Memory sau Lượt 1 ({len(res1.records_created)}):{Colors.RESET}")
        for idx, r in enumerate(res1.records_created, start=1):
            clean_fields = {k: v for k, v in r.__dict__.items() if v is not None and k not in ("created_at", "updated_at")}
            print(f"  {idx}. [{r.__class__.__name__}]: {clean_fields}")

    # --------------------------------------------------------------------------
    # LƯỢT 2: Audio bổ sung thông tin
    # --------------------------------------------------------------------------
    print(f"\n{Colors.CYAN}{'-' * 75}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.YELLOW}▶ LƯỢT 2: NÔNG DÂN GỬI AUDIO THỨ 2 BỔ SUNG THÔNG TIN{Colors.RESET}")
    print(f"  • File: {audio2_path.name}")
    t1 = time.time()
    res2 = harness.process_voice(
        audio=audio2_path,
        conversation_history=res1.history,
        memory=res1.memory,
        auto_stage=False,
    )
    el2 = round(time.time() - t1, 3)

    print(f"\n{Colors.BOLD}{Colors.BLUE}🗣️ AGENT 1 (SPEECH-TO-TEXT):{Colors.RESET}")
    print(f"  \"{res2.raw_transcript}\"")
    print(f"\n{Colors.BOLD}🤖 AGENT 2 (PHẢN HỒI HỆ THỐNG SAU KHI BỔ SUNG - {el2}s):{Colors.RESET}")
    print(f"{Colors.BOLD}{res2.reply_text}{Colors.RESET}")

    if res2.records_created:
        print(f"\n{Colors.BOLD}{Colors.GREEN}📋 TỔNG HỢP TOÀN BỘ CÁC BẢN GHI HOÀN CHỈNH TRONG BỘ NHỚ ({len(res2.records_created)}):{Colors.RESET}")
        for idx, r in enumerate(res2.records_created, start=1):
            clean_fields = {k: v for k, v in r.__dict__.items() if v is not None and k not in ("created_at", "updated_at")}
            print(f"  {idx}. [{r.__class__.__name__}]: {clean_fields}")

    print(f"\n{Colors.BOLD}{Colors.GREEN}{'=' * 75}")
    print(f"✓ ĐÃ HOÀN TẤT DEMO 2 AGENTS & BỘ NHỚ DRAFT MEMORY THÀNH CÔNG!")
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
