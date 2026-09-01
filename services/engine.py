"""
Engine
------
서비스들이 공유하는 실행 기반: 세션 생성·재시도 전송, 결과 저장,
히스토리 아카이브.

입력 준비(폴더 해석, 뷰 라벨, parts 조립)는 여기 없다 — 그건 각
서비스(services/*/*.py)의 책임이다.

사용 SDK: google-genai (신규 SDK)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from google import genai
from google.genai import types as genai_types

from config.api_config import get_api_key
from config.gemini import CHAT_CONFIG, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)


@dataclass
class StepResponse:
    """단일 API 호출의 결과 (텍스트 + 생성 이미지 목록)."""

    text: str = ""
    images: list[PILImage.Image] = field(default_factory=list)

    def has_image(self) -> bool:
        return len(self.images) > 0


class Session:
    """Gemini 채팅 세션. 히스토리를 유지하며 멀티모달 입출력을 다룬다."""

    def __init__(self, chat, client=None) -> None:
        self._chat = chat
        # chat은 내부적으로 client의 httpx 연결을 참조한다. client가 로컬
        # 변수로만 존재하면 GC 시 httpx 클라이언트가 닫혀 chat이 끊긴다.
        # Session이 살아있는 동안 client도 함께 살려둔다.
        self._client = client

    @property
    def history(self) -> list:
        """현재 채팅 히스토리를 반환합니다."""
        return list(self._chat.get_history())

    # ──────────────────────────────────────────────────
    # 메시지 전송
    # ──────────────────────────────────────────────────

    def send(self, parts: list, config=None) -> StepResponse:
        """메시지(텍스트 + 이미지 등)를 채팅 세션으로 전송하고 응답을 반환합니다.

        Args:
            parts: Gemini에 전달할 콘텐츠 리스트.
                   예: [PIL.Image.Image, "프롬프트 텍스트"]
            config: 이 호출에만 적용할 GenerateContentConfig. None이면 채팅 세션 기본값을 씁니다.

        Returns:
            StepResponse: 텍스트와 생성된 이미지 목록을 담은 결과 객체.

        Raises:
            RuntimeError: MAX_RETRIES 초과 시.
        """
        # 안전: parts에 중첩된 리스트가 있으면 평탄화합니다.
        try:
            parts = self._flatten_parts(parts)
        except Exception:
            logger.debug("parts 평탄화 중 오류 발생 — 원본을 그대로 사용합니다.")

        # 추가 안전 검사: 중첩된 리스트/튜플이 남아 있으면 재평탄화
        try:
            while any(isinstance(p, (list, tuple)) for p in parts):
                parts = self._flatten_parts(parts)
        except Exception:
            logger.debug("parts 추가 평탄화 중 오류 발생")

        # 허용되지 않는 파트 타입이 있으면 문자열로 변환해 보냅니다.
        sanitized: list = []
        for idx, p in enumerate(parts):
            # 허용되는 기본 타입: str, PIL.Image, genai File/Part, dict-like PartDict
            if isinstance(p, str) or isinstance(p, PILImage.Image):
                sanitized.append(p)
                continue
            # genai types: File, Part (실제 클래스만 isinstance 체크, TypedDict 제외)
            allowed_classes = tuple(
                t for t in (
                    getattr(genai_types, "File", None),
                    getattr(genai_types, "Part", None),
                )
                if t is not None and isinstance(t, type)
            )
            if allowed_classes and isinstance(p, allowed_classes):
                sanitized.append(p)
                continue
            # 앞 단계에서 생성된 이미지는 genai types.Image로 돌아옵니다. SDK가
            # 그대로는 못 받는 타입이라 Part로 감싸줍니다. 바이트를 그대로 넘기므로
            # 재인코딩이 없어 원본 화질이 유지됩니다.
            image_cls = getattr(genai_types, "Image", None)
            if image_cls is not None and isinstance(image_cls, type) and isinstance(p, image_cls):
                try:
                    sanitized.append(
                        genai_types.Part.from_bytes(
                            data=p.image_bytes, mime_type=p.mime_type or "image/png"
                        )
                    )
                    continue
                except Exception:
                    logger.exception("생성 이미지를 Part로 변환하지 못했습니다 — 이 파트를 건너뜁니다.")
                    continue
            # dict-like (PartDict / FileDict 는 TypedDict이므로 dict로만 판별)
            if isinstance(p, dict):
                sanitized.append(p)
                continue
            # 마지막 수단: repr로 변환
            logger.info("허용되지 않는 파트 타입 발견(%s) — repr으로 변환하여 전송합니다.", type(p))
            sanitized.append(repr(p)[:1000])

        parts = sanitized

        # Debug: log the outgoing parts and current chat history (if logger is set to DEBUG)
        try:
            logger.debug("=== Gemini API Request Parts ===\n%s", self._format_parts_for_log(parts))
        except Exception:
            logger.debug("=== Gemini API Request Parts: <failed to format parts> ===")

        try:
            logger.debug("=== Chat history BEFORE send ===\n%s", self._format_chat_history_for_log())
        except Exception:
            logger.debug("=== Chat history BEFORE send: <failed to format history> ===")

        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug("API 호출 시도 %d/%d", attempt, MAX_RETRIES)
                response = self._chat.send_message(parts, config=config)
                result = self._parse_response(response)

                logger.debug(
                    "API 응답 수신 완료 (텍스트: %d자, 이미지: %d장)",
                    len(result.text),
                    len(result.images),
                )

                # Debug: log a concise response preview and updated history
                try:
                    preview = result.text.replace("\n", " ")[:400]
                    logger.debug("=== Gemini API Response Preview ===\nlen=%d images=%d preview=%s", len(result.text), len(result.images), preview)
                except Exception:
                    logger.debug("=== Gemini API Response Preview: <failed to format> ===")

                try:
                    logger.debug("=== Chat history AFTER send ===\n%s", self._format_chat_history_for_log())
                except Exception:
                    logger.debug("=== Chat history AFTER send: <failed to format history> ===")

                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "API 호출 실패 (시도 %d/%d): %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        raise RuntimeError(
            f"Gemini API 호출이 {MAX_RETRIES}회 실패했습니다."
        ) from last_error

    # ──────────────────────────────────────────────────
    # 응답 파싱
    # ──────────────────────────────────────────────────

    @staticmethod
    def _parse_response(response) -> StepResponse:
        """API 응답에서 텍스트와 이미지를 추출합니다."""
        text_parts: list[str] = []
        images: list[PILImage.Image] = []

        for part in response.parts:
            # 사고(thought) 파트는 건너뜀
            if getattr(part, "thought", False):
                continue

            if part.text:
                text_parts.append(part.text)
            else:
                img = part.as_image()
                if img is not None:
                    images.append(img)

        return StepResponse(
            text="\n".join(text_parts).strip(),
            images=images,
        )

    # ──────────────────────────────────────────────────────────────────
    # Debug helpers
    # ──────────────────────────────────────────────────────────────────

    def _format_parts_for_log(self, parts: list) -> str:
        """Return a human-friendly summary of the `parts` list for logging."""
        lines: list[str] = []
        for idx, part in enumerate(parts):
            try:
                # PIL Image
                if isinstance(part, PILImage.Image):
                    filename = getattr(part, "filename", None)
                    size = getattr(part, "size", None)
                    mode = getattr(part, "mode", None)
                    lines.append(
                        f"part[{idx}]: Image filename={filename!r} size={size} mode={mode}"
                    )
                # Plain text prompt
                elif isinstance(part, str):
                    preview = " ".join(part.splitlines())[:200]
                    lines.append(f"part[{idx}]: Text(len={len(part)}) preview={preview!r}")
                else:
                    lines.append(f"part[{idx}]: {type(part).__name__} repr={repr(part)[:200]}")
            except Exception:
                lines.append(f"part[{idx}]: <failed to inspect part of type {type(part).__name__}>")
        return "\n".join(lines) if lines else "<no parts>"

    def _format_chat_history_for_log(self) -> str:
        """Render the current chat history in a compact chat-like UI style.

        Produces lines like:
        [18:49] You: Hello from the Left!
        [18:49] Peer: It works!

        Adds optional ANSI colors when stdout is a TTY.
        """
        try:
            return self._format_chat_history_for_log_inner()
        except Exception as exc:
            return f"<chat history formatting failed: {exc}>"

    def _format_chat_history_for_log_inner(self) -> str:
        history = self.history
        if not history:
            return "<empty chat history>"

        import sys
        import datetime

        use_color = sys.stdout.isatty()

        # ANSI color codes (used only when a TTY is detected)
        RESET = "\x1b[0m"
        DIM = "\x1b[2m"
        GREEN = "\x1b[32m"
        CYAN = "\x1b[36m"
        MAGENTA = "\x1b[35m"
        GREY = "\x1b[90m"

        def colorize(text: str, code: str) -> str:
            return f"{code}{text}{RESET}" if use_color else text

        def _fmt_ts(ts) -> str:
            if not ts:
                return ""
            try:
                if hasattr(ts, "ToDatetime"):
                    dt = ts.ToDatetime()
                elif isinstance(ts, datetime.datetime):
                    dt = ts
                elif isinstance(ts, (int, float)):
                    dt = datetime.datetime.fromtimestamp(ts)
                else:
                    # Fallback to str
                    return str(ts)
                return dt.strftime("%H:%M")
            except Exception:
                return str(ts)

        label_map = {"user": "You", "assistant": "Peer", "system": "System"}

        out_lines: list[str] = []

        for turn in history:
            role = getattr(turn, "role", "unknown")
            role_key = str(role).lower()
            label = label_map.get(role_key, str(role))

            ts = getattr(turn, "create_time", None) or getattr(turn, "timestamp", None) or getattr(turn, "time", None)
            ts_short = _fmt_ts(ts)
            ts_display = f"[{ts_short}]" if ts_short else ""

            # choose color for role
            if role_key == "user":
                role_color = GREEN
            elif role_key == "assistant":
                role_color = CYAN
            elif role_key == "system":
                role_color = MAGENTA
            else:
                role_color = GREY

            for p in getattr(turn, "parts", []):
                try:
                    if getattr(p, "text", None):
                        text = p.text.rstrip("\n")
                        if not text:
                            continue
                        # Split into lines; first line prints header, rest are indented
                        lines = text.splitlines()
                        first = lines[0]
                        if use_color:
                            ts_col = colorize(ts_display, DIM) + " " if ts_display else ""
                            role_col = colorize(label, role_color)
                            out_lines.append(f"{ts_col}{role_col}: {first}")
                        else:
                            prefix = f"{ts_display + ' ' if ts_display else ''}{label}:"
                            out_lines.append(f"{prefix} {first}")
                        for cont in lines[1:]:
                            out_lines.append("    " + cont)
                    elif getattr(p, "inline_data", None):
                        mime = getattr(p.inline_data, "mime_type", "unknown")
                        if use_color:
                            ts_col = colorize(ts_display, DIM) + " " if ts_display else ""
                            role_col = colorize(label, role_color)
                            out_lines.append(f"{ts_col}{role_col}: [Image mime={mime}]")
                        else:
                            out_lines.append(f"{ts_display + ' ' if ts_display else ''}{label}: [Image mime={mime}]")
                    else:
                        r = repr(p)
                        out_lines.append(f"{ts_display + ' ' if ts_display else ''}{label}: [{type(p).__name__}] {r[:300]}")
                except Exception:
                    out_lines.append(f"{label}: <failed to render part>")

        return "\n".join(out_lines) if out_lines else "<empty chat history>"

    def _flatten_parts(self, parts: list) -> list:
        """Recursively flatten lists/tuples inside parts but keep strings and image objects intact.

        The SDK expects a flat list of parts (or a single part). If callers accidentally
        pass nested lists (e.g. lists of images), flatten them so each element is an
        allowed part type.
        """
        flat: list = []

        def _rec(item):
            # strings are single parts
            if isinstance(item, str):
                flat.append(item)
                return
            # tuples/lists should be flattened
            if isinstance(item, (list, tuple)):
                for sub in item:
                    _rec(sub)
                return
            # otherwise append as-is (PIL images or genai File/Part objects)
            flat.append(item)

        _rec(parts)
        return flat


def new_session(model: str) -> Session:
    """새 Gemini 채팅 세션을 만든다. 모델은 서비스가 정한다."""
    client = genai.Client(api_key=get_api_key())
    chat = client.chats.create(model=model, config=CHAT_CONFIG)
    return Session(chat, client=client)


class RunOutput:
    """서비스 실행 결과를 파일로 저장한다.

    저장 구조:
        {out_dir}/{label}/
        └── {service}/
            ├── step_1_line_art.md
            └── step_1_line_art_generated_01.png
        {out_dir}/{label}/final_output.md
        {out_dir}/{label}/chat_history.json
    """

    def __init__(self, out_dir: Path, label: str) -> None:
        self._run_dir = Path(out_dir) / label
        # run dir is created lazily to allow image selection and other setup
        # to happen before filesystem side-effects.
        self._run_dir_created = False

    @property
    def run_dir(self) -> Path:
        """현재 실행의 출력 디렉터리 경로."""
        self._ensure_run_dir()
        return self._run_dir

    def service_dir(self, service: str) -> Path:
        """서비스별 출력 폴더 경로. 없으면 만든다."""
        self._ensure_run_dir()
        path = self._run_dir / service
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ──────────────────────────────────────────────────
    # 단계별 결과 저장
    # ──────────────────────────────────────────────────

    def save_step(
        self,
        service: str,
        step: int,
        name: str,
        description: str,
        prompt: str,
        response: str,
        generated_images: list | None = None,
    ) -> Path:
        """단계별 결과를 서비스 폴더에 Markdown 파일로 저장하고 생성된 이미지도 저장합니다.

        Returns:
            저장된 Markdown 파일의 경로.
        """
        service_dir = self.service_dir(service)

        # 생성된 이미지 저장 (파일명 안전화 및 예외 처리)
        saved_image_paths: list[Path] = []
        safe_name = self._sanitize_filename(name)
        for idx, img in enumerate(generated_images or [], start=1):
            img_filename = f"step_{step}_{safe_name}_generated_{idx:02d}.png"
            img_path = service_dir / img_filename
            try:
                img.save(img_path)
                saved_image_paths.append(img_path)
                logger.info("Step %d 생성 이미지 저장: %s", step, img_path)
            except Exception:
                logger.exception("이미지 저장 실패: %s", img_path)

        # Markdown 저장
        filename = f"step_{step}_{safe_name}.md"
        file_path = service_dir / filename

        content = self._format_step_markdown(
            step=step,
            description=description,
            prompt=prompt,
            response=response,
            saved_image_paths=saved_image_paths,
        )

        try:
            file_path.write_text(content, encoding="utf-8")
            logger.info("Step %d 결과 저장: %s", step, file_path)
        except Exception:
            logger.exception("Markdown 파일 저장 실패: %s", file_path)
        return file_path

    # ──────────────────────────────────────────────────
    # 최종 결과 저장
    # ──────────────────────────────────────────────────

    def save_final(self, text: str, generated_images: list | None = None, chat_history: list | None = None) -> Path:
        """최종 응답과 전체 채팅 히스토리를 저장합니다.

        Returns:
            저장된 파일의 경로.
        """
        self._ensure_run_dir()

        # 최종 생성 이미지 저장 (예외 처리)
        for idx, img in enumerate(generated_images or [], start=1):
            img_path = self._run_dir / f"final_generated_{idx:02d}.png"
            try:
                img.save(img_path)
                logger.info("최종 생성 이미지 저장: %s", img_path)
            except Exception:
                logger.exception("최종 이미지 저장 실패: %s", img_path)

        # 최종 응답 Markdown
        final_md_path = self._run_dir / "final_output.md"
        try:
            final_md_path.write_text(
                self._format_final_markdown(text),
                encoding="utf-8",
            )
            logger.info("최종 결과 저장: %s", final_md_path)
        except Exception:
            logger.exception("최종 Markdown 파일 저장 실패: %s", final_md_path)

        # 채팅 히스토리 JSON
        history_path = self._run_dir / "chat_history.json"
        history_data = self._serialize_history(chat_history or [])
        try:
            history_path.write_text(
                json.dumps(history_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("채팅 히스토리 저장: %s", history_path)
        except Exception:
            logger.exception("채팅 히스토리 저장 실패: %s", history_path)

        return final_md_path

    def _ensure_run_dir(self) -> None:
        """Create the run directory if it doesn't exist and log creation once."""
        if getattr(self, "_run_dir_created", False):
            return
        try:
            if not self._run_dir.exists():
                self._run_dir.mkdir(parents=True, exist_ok=True)
                logger.info("출력 디렉터리 생성: %s", self._run_dir)
        except Exception:
            logger.exception("출력 디렉터리 생성 실패: %s", self._run_dir)
        finally:
            self._run_dir_created = True

    # ──────────────────────────────────────────────────
    # 포맷터
    # ──────────────────────────────────────────────────

    @staticmethod
    def _format_step_markdown(
        step: int,
        description: str,
        prompt: str,
        response: str,
        saved_image_paths: list | None = None,
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 생성된 이미지 링크 목록
        if saved_image_paths:
            img_links = "\n".join(
                f"- ![생성이미지_{i}]({p.name})" for i, p in enumerate(saved_image_paths, 1)
            )
            generated_section = f"\n**생성된 이미지:**\n\n{img_links}\n"
        else:
            generated_section = "\n**생성된 이미지:** 없음\n"

        return (
            f"# Step {step}: {description}\n\n"
            f"> 생성 시각: {timestamp}\n\n"
            f"---\n\n"
            f"## 입력\n\n"
            f"**프롬프트:**\n\n"
            f"```\n{prompt}\n```\n\n"
            f"---\n\n"
            f"## Gemini 응답\n\n"
            f"### 텍스트\n\n"
            f"{response}\n"
            f"{generated_section}"
        )

    @staticmethod
    def _format_final_markdown(response: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"# 최종 출력 (Final Output)\n\n"
            f"> 생성 시각: {timestamp}\n\n"
            f"---\n\n"
            f"{response}\n"
        )

    @staticmethod
    def _serialize_history(history: list) -> list[dict]:
        """Gemini 채팅 히스토리를 JSON 직렬화 가능한 형태로 변환합니다."""
        serialized = []
        for turn in history:
            parts_data = []
            for part in turn.parts:
                if getattr(part, "text", None):
                    parts_data.append({"type": "text", "content": part.text})
                elif getattr(part, "inline_data", None):
                    parts_data.append({
                        "type": "image",
                        "content": f"[이미지 데이터 mime_type={part.inline_data.mime_type}]",
                    })
                else:
                    parts_data.append({"type": "unknown", "content": str(part)})
            serialized.append({"role": turn.role, "parts": parts_data})
        return serialized

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        """파일명으로 안전하게 변환합니다: 위험 문자 제거, 연속 구분자 축소."""
        if not value:
            return "untitled"
        # 위험한 문자들을 '_'로 대체
        s = re.sub(r'[\\/*?<>|:"\n\r]+', "_", value)
        # 공백을 언더스코어로
        s = re.sub(r"\s+", "_", s)
        # 여러 '_' 연속을 하나로
        s = re.sub(r"_+", "_", s)
        # 앞뒤 '_' 제거 및 길이 제한
        s = s.strip("_")[:100]
        return s or "untitled"


class HistoryArchive:
    """서비스마다 세션이 다르므로 턴을 모아둔다."""

    def __init__(self) -> None:
        self._turns: list = []

    def extend(self, turns) -> None:
        self._turns.extend(turns)

    def all(self) -> list:
        return list(self._turns)
