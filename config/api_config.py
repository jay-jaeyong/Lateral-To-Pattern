"""
API Key Management
------------------
OpenAI API 키를 파일/환경변수로 관리합니다.

우선순위:
 1. `/Users/jay/Documents/openaiapi.txt` 파일 (추천)
 2. 환경변수 `OPENAI_API_KEY`
 3. 프로젝트 루트의 `.env` 파일

주의: API 키를 코드에 직접 작성하거나 Git에 커밋하지 마세요.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _read_key_file(path: Path) -> str | None:
    try:
        txt = path.read_text(encoding="utf-8").strip()
        return txt if txt else None
    except FileNotFoundError:
        return None


def get_openai_api_key() -> str:
    """OpenAI(GPT) API 키를 가져옵니다."""
    cfg_file = Path("/Users/jay/Documents/openaiapi.txt")
    key = _read_key_file(cfg_file)
    if key:
        return key

    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip()

    raise EnvironmentError(
        "OpenAI API 키를 찾을 수 없습니다.\n"
        "다음 중 하나로 설정하세요:\n"
        " 1) 파일에 API 키 저장: /Users/jay/Documents/openaiapi.txt (파일 내용만 키 값)\n"
        " 2) 환경변수로 설정: export OPENAI_API_KEY=your_key_here\n"
        " 3) 프로젝트 루트에 .env 파일 생성: OPENAI_API_KEY=your_key_here\n"
    )
