"""
API Key Management
------------------
API 키를 파일로 관리하는 옵션을 우선 지원합니다.

우선순위
 1. `/Users/jay/Documents/geminiapi.txt` 파일 (추천)
 2. 환경변수 `GEMINI_API_KEY`
 3. 프로젝트 루트의 `.env` 파일

`.env` 예시 (기존 방식):
    GEMINI_API_KEY=your_actual_api_key_here

주의: API 키를 코드에 직접 작성하거나 Git에 커밋하지 마세요.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (환경변수 우선권 확보를 위해 파일에서 읽어 환경변수로 설정)
load_dotenv()


def _read_key_file(path: Path) -> str | None:
    try:
        txt = path.read_text(encoding="utf-8").strip()
        return txt if txt else None
    except FileNotFoundError:
        return None


def get_api_key() -> str:
    """다양한 소스에서 Gemini API 키를 가져옵니다.

    우선순위: `/Users/jay/Documents/geminiapi.txt` -> 환경변수 `GEMINI_API_KEY` -> `.env` 파일
    반환값은 앞뒤 공백이 제거된 문자열입니다.
    """
    # 1) 로컬 키 파일 우선
    cfg_file = Path("/Users/jay/Documents/geminiapi.txt")
    key = _read_key_file(cfg_file)
    if key:
        return key

    # 2) 환경변수
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()

    # 3) .env 파일을 통한 로드(이미 load_dotenv()가 호출되어 있음)
    # (위에서 환경변수 체크를 했으므로 여기서는 추가 처리 없이 실패 처리)
    raise EnvironmentError(
        "Gemini API 키를 찾을 수 없습니다.\n"
        "다음 중 하나로 설정하세요:\n"
        " 1) 파일에 API 키 저장: /Users/jay/Documents/geminiapi.txt (파일 내용만 키 값)\n"
        " 2) 환경변수로 설정: export GEMINI_API_KEY=your_key_here\n"
        " 3) 프로젝트 루트에 .env 파일 생성: GEMINI_API_KEY=your_key_here\n"
    )


def get_openai_api_key() -> str:
    """OpenAI(GPT) API 키를 가져옵니다.

    우선순위: `/Users/jay/Documents/openaiapi.txt` -> 환경변수 `OPENAI_API_KEY` -> `.env` 파일
    """
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
