"""
API Key Management
------------------
API 키를 파일로 관리하는 옵션을 우선 지원합니다.

우선순위
 1. `config/APIkey` 파일 (추천)
 2. 환경변수 `GEMINI_API_KEY_FILE`이 가리키는 키 파일
 3. 환경변수 `GEMINI_API_KEY`
 4. 프로젝트 루트의 `.env` 파일
 5. 레포 밖 기본 키 파일 (`EXTERNAL_KEY_FILES`, 예: ~/Documents/geminiapi.txt)

`.env` 예시 (기존 방식):
    GEMINI_API_KEY=your_actual_api_key_here

주의: API 키를 코드에 직접 작성하거나 Git에 커밋하지 마세요.
      로그·예외 메시지에도 키 값이 아니라 '어디서 읽었는지'만 남깁니다.
"""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (환경변수 우선권 확보를 위해 파일에서 읽어 환경변수로 설정)
load_dotenv()

logger = logging.getLogger(__name__)

# 레포 밖에 보관하는 키 파일 기본 위치 (파일 내용은 키 값만)
EXTERNAL_KEY_FILES: tuple[Path, ...] = (
    Path.home() / "Documents" / "geminiapi.txt",
)


def _read_key_file(path: Path) -> str | None:
    try:
        txt = path.read_text(encoding="utf-8").strip()
        return txt if txt else None
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError):
        return None


def get_api_key() -> str:
    """다양한 소스에서 Gemini API 키를 가져옵니다.

    우선순위:
        `config/APIkey` -> `GEMINI_API_KEY_FILE` -> `GEMINI_API_KEY`(.env 포함)
        -> `EXTERNAL_KEY_FILES`
    반환값은 앞뒤 공백이 제거된 문자열입니다.
    """
    # 1) config/APIkey 파일 우선
    cfg_file = Path(__file__).parent / "APIkey"
    key = _read_key_file(cfg_file)
    if key:
        logger.info("API 키 로드: %s", cfg_file)
        return key

    # 2) 환경변수로 지정한 키 파일
    key_file_env = os.environ.get("GEMINI_API_KEY_FILE")
    if key_file_env:
        key_path = Path(key_file_env).expanduser()
        key = _read_key_file(key_path)
        if key:
            logger.info("API 키 로드: %s (GEMINI_API_KEY_FILE)", key_path)
            return key
        logger.warning("GEMINI_API_KEY_FILE 경로에서 키를 읽지 못했습니다: %s", key_path)

    # 3) 환경변수 (load_dotenv()로 .env도 여기에 반영됨)
    key = os.environ.get("GEMINI_API_KEY")
    if key and key.strip():
        logger.info("API 키 로드: 환경변수 GEMINI_API_KEY")
        return key.strip()

    # 4) 레포 밖 기본 키 파일
    for external in EXTERNAL_KEY_FILES:
        key = _read_key_file(external)
        if key:
            logger.info("API 키 로드: %s", external)
            return key

    raise EnvironmentError(
        "Gemini API 키를 찾을 수 없습니다.\n"
        "다음 중 하나로 설정하세요:\n"
        " 1) 파일에 API 키 저장: config/APIkey (파일 내용만 키 값)\n"
        " 2) 키 파일 경로 지정: export GEMINI_API_KEY_FILE=/path/to/keyfile\n"
        " 3) 환경변수로 설정: export GEMINI_API_KEY=your_key_here\n"
        " 4) 프로젝트 루트에 .env 파일 생성: GEMINI_API_KEY=your_key_here\n"
        f" 5) 기본 키 파일 위치: {', '.join(str(p) for p in EXTERNAL_KEY_FILES)}\n"
    )
