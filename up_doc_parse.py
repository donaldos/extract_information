"""
파일명: up_doc_parse.py
작성자: Codex
작성일: 2026-06-12
수정일: 2026-06-12

개요:
    Upstage Document Parse API 호출을 담당하는 모듈이다.
    문서 파일을 multipart/form-data 요청으로 전송하고, 응답 JSON에서
    Markdown 파일로 저장할 텍스트를 추출한다.
"""

from dataclasses import dataclass
from html import unescape
import json
import logging
import mimetypes
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


DEFAULT_ENDPOINT = "https://api.upstage.ai/v1/document-ai/document-parse"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentParseOptions:
    """
    기능:
        Upstage Document Parse 요청에 필요한 설정 값을 보관한다.

    입력:
        api_key: Upstage API 키
        endpoint: Document Parse API 엔드포인트
        ocr: OCR 처리 방식(auto 또는 force)
        formats: API에 요청할 출력 포맷 목록
        coordinates: 좌표 정보 요청 여부
        timeout: 요청 제한 시간(초)

    출력:
        DocumentParseOptions 인스턴스
    """

    api_key: str
    endpoint: str = DEFAULT_ENDPOINT
    ocr: str = "auto"
    formats: tuple[str, ...] = ("markdown", "text", "html")
    coordinates: bool = False
    timeout: int = 120


def parse_document(document_path: Path, options: DocumentParseOptions) -> dict:
    """
    기능:
        단일 문서 파일을 Upstage Document Parse API로 전송하고 JSON 응답을 반환한다.

    입력:
        document_path: 파싱할 문서 파일 경로
        options: API 요청 옵션

    출력:
        dict: Upstage API가 반환한 JSON 응답

    예외:
        FileNotFoundError: 문서 파일이 존재하지 않는 경우
        ValueError: API 키가 비어 있는 경우
        RuntimeError: API 연결 실패, 비정상 응답, JSON 파싱 실패가 발생한 경우
    """
    source_path = document_path.expanduser().resolve()

    if not source_path.is_file():
        raise FileNotFoundError(f"Document file does not exist: {source_path}")

    if not options.api_key:
        raise ValueError("Missing Upstage API key.")

    content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    logger.debug(
        "Preparing Upstage request for %s with content type %s",
        source_path.name,
        content_type,
    )
    fields = {
        "ocr": options.ocr,
        "output_formats": json.dumps(list(options.formats)),
        "coordinates": str(options.coordinates).lower(),
    }

    body, boundary = build_multipart_body(
        fields=fields,
        file_field_name="document",
        file_path=source_path,
        content_type=content_type,
    )
    headers = {
        # Do not log this header; it contains the API key.
        "Authorization": f"Bearer {options.api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    request = Request(options.endpoint, data=body, headers=headers, method="POST")

    try:
        logger.info("Sending document to Upstage: %s", source_path.name)
        with urlopen(request, timeout=options.timeout) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        status_code = exc.code
        response_body = exc.read().decode("utf-8", errors="replace")
        logger.warning("Upstage returned HTTP error for %s: %s", source_path.name, status_code)
    except URLError as exc:
        logger.error("Failed to connect to Upstage API for %s: %s", source_path.name, exc)
        raise RuntimeError(f"Failed to connect to Upstage API: {exc}") from exc

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as exc:
        logger.error("Upstage returned non-JSON response for %s", source_path.name)
        raise RuntimeError(
            f"Upstage API returned non-JSON response "
            f"({status_code}): {response_body[:500]}"
        ) from exc

    if status_code < 200 or status_code >= 300:
        logger.error("Upstage request failed for %s: %s", source_path.name, status_code)
        raise RuntimeError(
            f"Upstage API request failed ({status_code}): "
            f"{json.dumps(result, ensure_ascii=False)}"
        )

    logger.info("Upstage request completed for %s: %s", source_path.name, status_code)
    return result


def build_multipart_body(
    fields: dict[str, str],
    file_field_name: str,
    file_path: Path,
    content_type: str,
) -> tuple[bytes, str]:
    """
    기능:
        Upstage API 요청에 사용할 multipart/form-data 본문과 boundary를 생성한다.

    입력:
        fields: form-data에 포함할 일반 필드 딕셔너리
        file_field_name: 파일 필드 이름
        file_path: 업로드할 파일 경로
        content_type: 업로드 파일의 MIME 타입

    출력:
        tuple[bytes, str]: 요청 본문 bytes, multipart boundary 문자열
    """
    boundary = f"----upstage-document-parse-{uuid4().hex}"
    line_break = b"\r\n"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"),
                b"",
                value.encode("utf-8"),
            ]
        )

    chunks.extend(
        [
            f"--{boundary}".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field_name}"; '
                f'filename="{file_path.name}"'
            ).encode("utf-8"),
            f"Content-Type: {content_type}".encode("utf-8"),
            b"",
            file_path.read_bytes(),
            f"--{boundary}--".encode("utf-8"),
            b"",
        ]
    )
    return line_break.join(chunks), boundary


def extract_markdown_from_parse_result(parse_result: dict) -> str:
    """
    기능:
        Upstage API 응답에서 Markdown 파일로 저장하기에 가장 적합한 텍스트를 추출한다.
        markdown, text, html, other 순서로 후보를 선택한다.

    입력:
        parse_result: Upstage API 응답 JSON 딕셔너리

    출력:
        str: Markdown 파일에 저장할 텍스트. 찾지 못하면 빈 문자열
    """
    candidates = {
        "markdown": [],
        "text": [],
        "html": [],
        "other": [],
    }

    collect_text_candidates(parse_result, "", candidates)

    for bucket in ("markdown", "text", "html", "other"):
        joined = join_unique_texts(candidates[bucket])
        if joined:
            logger.debug("Extracted %s characters from %s result", len(joined), bucket)
            return joined

    logger.warning("No text content found in Upstage parse result")
    return ""


def collect_text_candidates(value, key: str, candidates: dict[str, list[str]]) -> None:
    """
    기능:
        중첩된 API 응답 구조를 재귀적으로 탐색하면서 문자열 후보를 유형별로 분류한다.

    입력:
        value: 탐색할 현재 응답 값
        key: 현재 값에 대응하는 키 이름
        candidates: markdown/text/html/other 후보 문자열을 담는 딕셔너리

    출력:
        없음. candidates 딕셔너리를 직접 갱신한다.
    """
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            collect_text_candidates(child_value, str(child_key), candidates)
        return

    if isinstance(value, list):
        for item in value:
            collect_text_candidates(item, key, candidates)
        return

    if not isinstance(value, str):
        return

    cleaned = value.strip()
    if not cleaned:
        return

    # Prefer markdown when present, then readable text, then HTML converted to text.
    key_lower = key.lower()
    if "markdown" in key_lower or key_lower == "md":
        candidates["markdown"].append(cleaned)
    elif "text" in key_lower or "content" in key_lower:
        candidates["text"].append(cleaned)
    elif "html" in key_lower:
        candidates["html"].append(strip_html(cleaned))
    elif len(cleaned) >= 80 or "\n" in cleaned:
        candidates["other"].append(cleaned)


def join_unique_texts(texts: list[str]) -> str:
    """
    기능:
        중복된 텍스트 조각을 제거하고 하나의 문자열로 합친다.

    입력:
        texts: 텍스트 후보 목록

    출력:
        str: 중복이 제거되어 줄바꿈으로 연결된 문자열
    """
    unique_texts = []
    seen = set()

    for text in texts:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        unique_texts.append(text)

    return "\n".join(unique_texts)


def strip_html(value: str) -> str:
    """
    기능:
        HTML 조각에서 태그를 제거하고 읽기 쉬운 일반 텍스트로 변환한다.

    입력:
        value: HTML 문자열

    출력:
        str: 태그가 제거된 일반 텍스트
    """
    value = re.sub(r"<(br|p|div|li|tr|h[1-6])\b[^>]*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"[ \t]+", " ", value).strip()
