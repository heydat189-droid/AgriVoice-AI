"""AgriVoice-AI: Two-Agent Voice Audio Evaluation & Testing Suite.

Kiến trúc 2 Agents:
1. Agent 1 (Speech-to-Text): Tiếp nhận audio giọng nói nông dân và chép lại chính xác từng từ nguyên văn.
2. Agent 2 (Reasoning & Action Execution): Tiếp nhận văn bản từ Agent 1, quản lý danh sách bản ghi
   nghiệp vụ đang tổng hợp trong bộ nhớ (Draft Memory), thực thi tool calling (tạo mới, cập nhật, xóa bản ghi)
   và phản hồi lại hệ thống.

Bộ nhớ (Draft Memory) được lưu trữ trong python dictionary:
- Cho phép chỉnh sửa bổ sung thông tin qua các tool: `update_draft_record`, `remove_draft_record`, `get_draft_records`.
- Không bị mất các bản ghi đã ghi nhận ở các lượt trước khi người dùng bổ sung thông tin ở lượt sau.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(WORKSPACE_ROOT / ".env")
except ImportError:
    pass

from src.ai.harness import GenAIHarness, HarnessResult


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def clean_input_path(raw_path: str) -> Path:
    """Cleans input path string from quotes or whitespace and resolves to Path."""
    p = raw_path.strip().strip("'\"").strip()
    return Path(p).expanduser().resolve()


def evaluate_audio_file(
    audio_path: Union[str, Path],
    harness: Optional[GenAIHarness] = None,
    conversation_history: Optional[List[Any]] = None,
    memory: Optional[Dict[str, Any]] = None,
) -> HarnessResult:
    """Sends audio file through the 2-agent pipeline (Agent 1 STT -> Agent 2 Reasoning & Memory)."""
    target_path = clean_input_path(str(audio_path))
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file ghi âm: '{target_path}'")

    if harness is None:
        harness = GenAIHarness()

    return harness.process_voice(
        audio=target_path,
        auto_stage=False,
        conversation_history=conversation_history,
        memory=memory,
    )


def print_evaluation_result(audio_path: Union[Path, str], result: HarnessResult, turn_label: str = "") -> None:
    """Prints clear, human-readable evaluation output with Agent 1 and Agent 2 results."""
    header_title = f"🎙️ {turn_label.upper()} - FILE GHI ÂM: {audio_path}" if turn_label else f"🎙️ FILE GHI ÂM: {audio_path}"
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 75}{Colors.RESET}")
    print(f"{Colors.BOLD}{header_title}{Colors.RESET}")
    print(f"{Colors.BOLD}⚡ MÔ HÌNH SỬ DỤNG:{Colors.RESET} {result.model_used or 'N/A'}")
    print(f"{Colors.BOLD}⏱️ THỜI GIAN XỬ LÝ:{Colors.RESET} {result.execution_time_seconds}s")
    if result.raw_transcript:
        print(f"{Colors.BOLD}{Colors.BLUE}🗣️ AGENT 1 (SPEECH-TO-TEXT VĂN BẢN NÓI GỐC):{Colors.RESET}")
        print(f"  \"{result.raw_transcript}\"")
    print(f"{Colors.BOLD}{Colors.CYAN}{'-' * 75}{Colors.RESET}")

    if not result.success:
        print(f"{Colors.BOLD}{Colors.RED}❌ LỖI XỬ LÝ:{Colors.RESET}")
        print(f"  {result.error or result.reply_text}")
    else:
        print(f"{Colors.BOLD}{Colors.GREEN}🤖 AGENT 2 (PHẢN HỒI HỆ THỐNG):{Colors.RESET}")
        print(f"{Colors.BOLD}{result.reply_text}{Colors.RESET}")

        if result.records_created:
            print(f"\n{Colors.BOLD}{Colors.YELLOW}📋 DANH SÁCH BẢN GHI ĐANG TỔNG HỢP (DRAFT MEMORY) ({len(result.records_created)}):{Colors.RESET}")
            for idx, rec in enumerate(result.records_created, start=1):
                rec_name = rec.__class__.__name__
                details = getattr(rec, "to_dict", lambda: rec.__dict__)()
                clean_details = {k: v for k, v in details.items() if v is not None and k not in ("created_at", "updated_at")}
                print(f"  {idx}. [{rec_name}]: {clean_details}")

    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 75}{Colors.RESET}\n")


def process_two_audios(
    audio1_path: Path,
    audio2_path: Path,
    harness: Optional[GenAIHarness] = None,
) -> Tuple[HarnessResult, HarnessResult]:
    """Processes two audio files sequentially where Audio 2 supplements Audio 1 using DraftMemory."""
    if harness is None:
        harness = GenAIHarness()

    mem = {"draft_records": []}

    print(f"\n{Colors.YELLOW}⏳ Đang xử lý Lượt 1 qua 2 Agents ({audio1_path.name})...{Colors.RESET}")
    res1 = evaluate_audio_file(audio1_path, harness=harness, memory=mem)
    print_evaluation_result(audio1_path, res1, turn_label="Lượt 1: Khẩu lệnh ban đầu")

    print(f"{Colors.YELLOW}⏳ Đang xử lý Lượt 2: Nông dân bổ sung thông tin ({audio2_path.name})...{Colors.RESET}")
    res2 = evaluate_audio_file(
        audio2_path,
        harness=harness,
        conversation_history=res1.history,
        memory=res1.memory,
    )
    print_evaluation_result(audio2_path, res2, turn_label="Lượt 2: Bổ sung thông tin")

    return res1, res2


def interactive_loop():
    """Interactive loop allowing continuous evaluation of audio files."""
    print(f"{Colors.BOLD}{Colors.HEADER}")
    print("*" * 75)
    print("      ĐÁNH GIÁ 2 AGENTS & BỘ NHỚ DRAFT MEMORY (AGRIVOICE-AI)")
    print("          Nền tảng nhúng Raspberry Pi & Mô hình Google GenAI")
    print("*" * 75)
    print(f"{Colors.RESET}")

    default_a1 = WORKSPACE_ROOT / "data" / "audio_2026-10-15_20-18-02.ogg"
    default_a2 = WORKSPACE_ROOT / "data" / "audio_2026-10-15_20-20-22.ogg"
    harness = GenAIHarness()

    while True:
        try:
            print(f"{Colors.BOLD}Nhập đường dẫn file ghi âm:{Colors.RESET}")
            print("  • Có thể nhập 1 file: path/to/audio1.ogg")
            print("  • Có thể nhập 2 file bổ sung: path/to/audio1.ogg path/to/audio2.ogg")
            print(f"  • Nhấn Enter để chạy cặp 2 audio mẫu ({default_a1.name} -> {default_a2.name})")
            print("  • Gõ 'q' để thoát")
            user_input = input(f"{Colors.CYAN}> {Colors.RESET}").strip()

            if user_input.lower() in ("q", "quit", "exit"):
                print("Đã thoát chương trình đánh giá.")
                break

            # Default 2-audio pair
            if not user_input:
                if default_a1.exists() and default_a2.exists():
                    print(f"\n{Colors.GREEN}✓ Chạy cặp 2 file audio mẫu thực tế qua 2 Agents & DraftMemory:{Colors.RESET}")
                    process_two_audios(default_a1, default_a2, harness=harness)
                    continue
                else:
                    print(f"{Colors.RED}Không tìm thấy file mẫu. Vui lòng nhập đường dẫn.{Colors.RESET}\n")
                    continue

            # Check if user passed 2 paths separated by space or comma
            parts = [clean_input_path(p) for p in user_input.replace(",", " ").split() if p.strip()]
            if len(parts) >= 2:
                p1, p2 = parts[0], parts[1]
                if not p1.exists() or not p1.is_file():
                    print(f"{Colors.RED}❌ File 1 không tồn tại: '{p1}'{Colors.RESET}\n")
                    continue
                if not p2.exists() or not p2.is_file():
                    print(f"{Colors.RED}❌ File 2 không tồn tại: '{p2}'{Colors.RESET}\n")
                    continue
                process_two_audios(p1, p2, harness=harness)
                continue

            # Single audio input
            target_path = parts[0]
            if not target_path.exists() or not target_path.is_file():
                print(f"{Colors.RED}❌ File không tồn tại: '{target_path}'. Vui lòng thử lại.{Colors.RESET}\n")
                continue

            mem = {"draft_records": []}
            print(f"\n{Colors.YELLOW}⏳ Đang gửi file âm thanh tới 2 Agents ({target_path.name})...{Colors.RESET}")
            res1 = evaluate_audio_file(target_path, harness=harness, memory=mem)
            print_evaluation_result(target_path, res1, turn_label="Lượt 1")

            # Follow-up turn prompt
            print(f"{Colors.BOLD}{Colors.YELLOW}▶ BỔ SUNG THÔNG TIN CHO LƯỢT TIẾP THEO:{Colors.RESET}")
            follow_msg = (
                f"Nhập file ghi âm thứ 2 (hoặc gõ văn bản bổ sung, Enter để bỏ qua, 'q' để thoát): "
            )
            follow_input = input(follow_msg).strip()
            if follow_input.lower() in ("q", "quit", "exit"):
                break
            if not follow_input:
                continue

            follow_path = clean_input_path(follow_input)
            if follow_path.exists() and follow_path.is_file():
                print(f"\n{Colors.YELLOW}⏳ Đang gửi audio thứ 2 bổ sung thông tin ({follow_path.name})...{Colors.RESET}")
                res2 = evaluate_audio_file(
                    follow_path,
                    harness=harness,
                    conversation_history=res1.history,
                    memory=res1.memory,
                )
                print_evaluation_result(follow_path, res2, turn_label="Lượt 2: Bổ sung thông tin")
            else:
                # Text supplement
                print(f"\n{Colors.YELLOW}⏳ Đang gửi thông tin bổ sung dạng văn bản...{Colors.RESET}")
                res2 = harness.process_text(
                    follow_input,
                    conversation_history=res1.history,
                    memory=res1.memory,
                    auto_stage=False,
                )
                print_evaluation_result("Văn bản bổ sung", res2, turn_label="Lượt 2: Bổ sung thông tin")

        except (KeyboardInterrupt, EOFError):
            print("\nĐã dừng chương trình.")
            break
        except Exception as exc:
            print(f"{Colors.RED}❌ Đã xảy ra lỗi: {exc}{Colors.RESET}\n")


def main():
    if len(sys.argv) >= 3:
        p1 = clean_input_path(sys.argv[1])
        p2 = clean_input_path(sys.argv[2])
        if not p1.exists():
            print(f"{Colors.RED}❌ Không tìm thấy file 1: {p1}{Colors.RESET}")
            sys.exit(1)
        if not p2.exists():
            print(f"{Colors.RED}❌ Không tìm thấy file 2: {p2}{Colors.RESET}")
            sys.exit(1)
        process_two_audios(p1, p2)
    elif len(sys.argv) == 2:
        target_path = clean_input_path(sys.argv[1])
        if not target_path.exists() or not target_path.is_file():
            print(f"{Colors.RED}❌ File không tồn tại: '{target_path}'{Colors.RESET}")
            sys.exit(1)

        print(f"\n{Colors.YELLOW}⏳ Đang gửi file âm thanh tới AI ({target_path.name})...{Colors.RESET}")
        harness = GenAIHarness()
        result = evaluate_audio_file(target_path, harness=harness)
        print_evaluation_result(target_path, result)
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
