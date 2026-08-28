#!/usr/bin/env python3
"""로컬 주석 웹페이지.

manifest에 적힌 이미지만 읽기 전용으로 제공하고, 정규화 좌표 주석 sidecar만
씁니다. 어떤 경로도 이미지 바이트를 쓰지 않고, 오버레이·마스크·축소본을 파일로
저장하지 않으며, Gemini나 외부 API를 호출하지 않습니다. 채점 API는 메모리
결과만 돌려주고 보고서 실행을 만들지 않습니다.

사용법:
    uv run python scripts/annotate_sketches.py \\
        --manifest annotations/sketch-scoring/dataset.json --host 127.0.0.1 --port 5000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, Response, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from sketch_scoring.annotations import (
    AnnotationError,
    detect_red_boxes,
    load_annotations,
    save_annotations,
    suggest_connection_anchors,
)
from sketch_scoring.manifest import (
    ManifestError,
    allowed_image_roots,
    load_manifest,
    resolve_read_path,
    resolve_write_path,
    version_sort_key,
)
from sketch_scoring.metrics import ImageDecodeError, ScoringConfig, load_rgb
from sketch_scoring.scoring import score_output

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WRITABLE_ANNOTATION_ROOT = Path("annotations/sketch-scoring")
DEFAULT_MANIFEST = WRITABLE_ANNOTATION_ROOT / "dataset.json"
DEFAULT_ANNOTATION_ROOT = WRITABLE_ANNOTATION_ROOT / "items"
ANNOTATED_ONLY_ANCHOR_REASON = (
    "빨간 표시가 합성된 주석 자료에서는 앵커를 자동 추정하지 않습니다. "
    "끊긴 재단선의 두 끝을 순서대로 클릭하세요."
)

_MAGIC_MIMETYPES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"BM", "image/bmp"),
)


class ApiError(Exception):
    """JSON 오류 응답으로 바꿀 요청 오류."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _image_mimetype(data: bytes) -> str:
    """확장자를 믿지 않고 실제 바이트로 Content-Type을 정합니다."""
    for magic, mimetype in _MAGIC_MIMETYPES:
        if data.startswith(magic):
            return mimetype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def create_app(
    manifest_path: Path,
    *,
    project_root: Path | None = None,
    annotation_root: Path | None = None,
) -> Flask:
    app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))
    root = Path(project_root or PROJECT_ROOT)
    app.config.update(
        MANIFEST_PATH=Path(manifest_path),
        PROJECT_ROOT=root,
        # 주석 쓰기는 허용된 루트 안으로만 제한합니다.
        ANNOTATION_ROOT=resolve_write_path(
            root,
            annotation_root or DEFAULT_ANNOTATION_ROOT,
            allowed_root=WRITABLE_ANNOTATION_ROOT,
        ),
        MAX_CONTENT_LENGTH=1_000_000,
    )
    app.config["TESTING"] = False

    @app.after_request
    def _never_store(response):
        """모든 응답에 no-store를 붙입니다.

        정상 응답, JSON 오류, 프레임워크가 만든 오류(404, 413)까지 한 곳에서
        처리해야 주석과 로컬 출력 변경이 곧바로 보이고 오래된 오류가 캐시되지
        않습니다.
        """
        response.headers["Cache-Control"] = "no-store"
        return response

    def manifest() -> dict:
        # 요청마다 다시 읽어 manifest 수정이 바로 반영되게 합니다.
        return load_manifest(
            app.config["MANIFEST_PATH"], project_root=app.config["PROJECT_ROOT"]
        )

    def item_or_404(item_id: str) -> dict:
        items = manifest()["items"]
        if item_id not in items:
            raise ApiError(f"manifest에 없는 항목: {item_id}", 404)
        return items[item_id]

    def resolved_image(item: dict, kind: str, version: str | None) -> Path:
        """manifest에 적힌 경로만 해석합니다. 사용자 경로는 받지 않습니다."""
        if kind == "source":
            relative = item["source"]
        elif kind == "output":
            record = (item["outputs"] or {}).get(version or "")
            if record is None:
                raise ApiError(f"manifest에 없는 판본: {version}", 404)
            relative = record.get("path")
            if not relative:
                raise ApiError(f"출력 경로가 확정되지 않은 판본: {version}", 404)
        else:
            raise ApiError(f"kind는 source 또는 output이어야 함: {kind}")
        try:
            return resolve_read_path(
                app.config["PROJECT_ROOT"],
                relative,
                allowed_roots=allowed_image_roots(app.config["PROJECT_ROOT"]),
            )
        except ManifestError as exc:
            raise ApiError(str(exc), 404) from exc

    def requested_image(item: dict) -> Path:
        payload = request.get_json(silent=True) or {}
        kind = str(payload.get("kind") or request.args.get("kind") or "output")
        version = payload.get("version") or request.args.get("version")
        return resolved_image(item, kind, version)

    @app.errorhandler(ApiError)
    def _api_error(error: ApiError):
        return jsonify({"error": error.message}), error.status

    @app.errorhandler(AnnotationError)
    def _annotation_error(error: AnnotationError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(ManifestError)
    def _manifest_error(error: ManifestError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(ImageDecodeError)
    def _decode_error(error: ImageDecodeError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(RequestEntityTooLarge)
    def _too_large(error: RequestEntityTooLarge):
        # 본문 크기 제한을 넘으면 HTML 오류 페이지가 아니라 JSON으로 알립니다.
        # 요청은 읽히지 않으므로 기존 사이드카는 그대로 남습니다.
        limit = app.config.get("MAX_CONTENT_LENGTH")
        # 413도 JSON 본문과 상태를 유지합니다(헤더는 after_request가 붙입니다).
        return jsonify({"error": f"요청 본문이 너무 큽니다 (최대 {limit} 바이트)"}), 413

    @app.get("/")
    def index():
        return render_template("annotate.html")

    @app.get("/api/images")
    def api_images():
        items = []
        for item_id, item in sorted(manifest()["items"].items()):
            versions = []
            for version in sorted(item["outputs"], key=version_sort_key):
                record = item["outputs"][version]
                exists = False
                if record.get("path"):
                    try:
                        resolved_image(item, "output", version)
                        exists = True
                    except ApiError:
                        exists = False
                versions.append(
                    {
                        "version": version,
                        "kind": record.get("kind", "clean"),
                        "exists": exists,
                    }
                )
            items.append(
                {
                    "id": item_id,
                    "display_name": item["display_name"],
                    "expected_canvas_ratio": item["expected_canvas_ratio"],
                    "needs_review": item["needs_review"],
                    "versions": versions,
                }
            )
        return jsonify({"items": items})

    @app.get("/api/image/<item_id>")
    def api_image(item_id: str):
        path = resolved_image(
            item_or_404(item_id),
            request.args.get("kind", "source"),
            request.args.get("version"),
        )
        data = path.read_bytes()
        return Response(data, mimetype=_image_mimetype(data))

    @app.get("/api/annotations/<item_id>")
    def api_get_annotations(item_id: str):
        item_or_404(item_id)
        document = load_annotations(app.config["ANNOTATION_ROOT"], item_id)
        return jsonify(document)

    @app.post("/api/annotations/<item_id>")
    def api_save_annotations(item_id: str):
        item_or_404(item_id)
        document = request.get_json(silent=True)
        if not isinstance(document, dict):
            raise ApiError("주석 문서(JSON)가 필요함")
        # 검증을 통과하지 못하면 기존 sidecar를 건드리지 않습니다.
        save_annotations(app.config["ANNOTATION_ROOT"], item_id, document)
        return jsonify(
            {
                "saved": True,
                "document": load_annotations(app.config["ANNOTATION_ROOT"], item_id),
            }
        )

    @app.post("/api/import-red-boxes/<item_id>")
    def api_import_red_boxes(item_id: str):
        path = requested_image(item_or_404(item_id))
        # 후보만 돌려줍니다. 저장은 사용자가 확인한 뒤 별도 요청으로 합니다.
        candidates = detect_red_boxes(load_rgb(path))
        return jsonify({"candidates": candidates, "saved": False})

    @app.post("/api/suggest-anchors/<item_id>")
    def api_suggest_anchors(item_id: str):
        item = item_or_404(item_id)
        payload = request.get_json(silent=True) or {}
        target_box = payload.get("target_box")
        if not isinstance(target_box, list):
            raise ApiError("target_box(정규화 좌표 네 개)가 필요함")

        kind = str(payload.get("kind") or request.args.get("kind") or "output")
        version = payload.get("version") or request.args.get("version")
        if kind == "output":
            record = (item["outputs"] or {}).get(str(version))
            if record is None:
                raise ApiError(f"manifest에 없는 판본: {version}", 404)
            if record.get("kind") == "annotated_only":
                # 합성된 빨간 표시가 선 끝처럼 보이므로 앵커를 추정하지 않습니다.
                # 이 출력은 디코드하지 않고 사용자에게 직접 클릭을 요청합니다.
                return jsonify(
                    {"anchors": [], "reason": ANNOTATED_ONLY_ANCHOR_REASON}
                )

        path = resolved_image(item, kind, version)
        # 후보가 정확히 두 개가 아니면 빈 목록이며 사용자가 직접 클릭합니다.
        anchors = suggest_connection_anchors(load_rgb(path), target_box)
        return jsonify({"anchors": anchors})

    @app.post("/api/score/<item_id>")
    def api_score(item_id: str):
        item = item_or_404(item_id)
        payload = request.get_json(silent=True) or {}
        version = payload.get("version") or request.args.get("version")
        record = (item["outputs"] or {}).get(str(version))
        if record is None:
            raise ApiError(f"manifest에 없는 판본: {version}", 404)
        # 메모리 결과만 돌려주고 보고서 실행을 만들지 않습니다.
        result = score_output(
            item_id,
            item,
            str(version),
            record,
            project_root=app.config["PROJECT_ROOT"],
            annotation_root=app.config["ANNOTATION_ROOT"],
            config=ScoringConfig(),
        )
        return jsonify({"result": result})

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="스케치 주석 로컬 웹페이지")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--annotation-root", type=Path, default=DEFAULT_ANNOTATION_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path.cwd()
    app = create_app(
        args.manifest if args.manifest.is_absolute() else project_root / args.manifest,
        project_root=project_root,
        annotation_root=args.annotation_root,
    )
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
