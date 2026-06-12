"""
파일명: up_doc_extract.py
작성자: Codex
작성일: 2026-06-12
수정일: 2026-06-12

개요:
    Upstage Information Extraction API 호출을 담당하는 모듈이다.
    문서 파일을 base64로 인코딩해 JSON 요청 본문에 담아 전송하고,
    JSON Schema(response_format) 기반 구조화 추출 결과를 dict로 반환한다.
"""

from dataclasses import dataclass
from typing import Any
import base64
import json
import logging
import mimetypes
from pathlib import Path

from chat_completion import send_chat_completion


DEFAULT_EXTRACT_ENDPOINT = "https://api.upstage.ai/v1/information-extraction"
DEFAULT_EXTRACT_MODEL = "information-extract"
DEFAULT_SCHEMA_NAME = "document_metadata"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentExtractOptions:
    """
    기능:
        Upstage Information Extraction 요청에 필요한 설정 값을 보관한다.

    입력:
        api_key: Upstage API 키
        endpoint: Information Extraction API 엔드포인트
        model: 사용할 모델 이름
        timeout: 요청 제한 시간(초)
        prompt: 추출 기준을 보충 설명하는 선택 텍스트
        schema: 구조화 추출에 사용할 JSON Schema 딕셔너리
        schema_name: response_format.json_schema.name에 사용할 이름

    출력:
        DocumentExtractOptions 인스턴스
    """

    api_key: str
    endpoint: str = DEFAULT_EXTRACT_ENDPOINT
    model: str = DEFAULT_EXTRACT_MODEL
    timeout: int = 120
    prompt: str | None = None
    schema: dict[str, Any] | None = None
    schema_name: str = DEFAULT_SCHEMA_NAME


def structured_extract_document(
    document_path: Path,
    options: DocumentExtractOptions,
) -> dict:
    """
    기능:
        JSON Schema를 사용해 단일 문서 파일의 구조화 정보 추출 결과를 반환한다.

    입력:
        document_path: 구조화 정보 추출 대상 문서 파일 경로
        options: API 요청 옵션. schema 값이 반드시 필요하다.

    출력:
        dict: response_format 스키마에 맞춰 추출된 필드 딕셔너리

    예외:
        ValueError: schema 또는 API 키가 설정되지 않은 경우
        FileNotFoundError: 문서 파일이 존재하지 않는 경우
        RuntimeError: API 연결 실패, 비정상 응답, JSON 파싱 실패가 발생한 경우
    """
    if not options.schema:
        raise ValueError("Structured extract requires a JSON schema.")

    if not options.api_key:
        raise ValueError("Missing Upstage API key.")

    source_path = document_path.expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Document file does not exist: {source_path}")

    payload = build_extract_payload(source_path, options)
    return send_chat_completion(
        endpoint=options.endpoint,
        api_key=options.api_key,
        payload=payload,
        timeout=options.timeout,
        label=source_path.name,
        provider="Upstage information extraction",
    )


def build_extract_payload(source_path: Path, options: DocumentExtractOptions) -> dict[str, Any]:
    """
    기능:
        Information Extraction API에 보낼 chat completions 형식의 JSON 요청 본문을 만든다.

    입력:
        source_path: 업로드할 문서 파일 경로
        options: API 요청 옵션

    출력:
        dict[str, Any]: model/messages/response_format을 포함한 요청 본문
    """
    content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
    data_url = f"data:{content_type};base64,{encoded}"

    content: list[dict[str, Any]] = []
    if options.prompt:
        content.append({"type": "text", "text": options.prompt})
    content.append({"type": "image_url", "image_url": {"url": data_url}})

    return {
        "model": options.model,
        "messages": [{"role": "user", "content": content}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": options.schema_name,
                "strict": True,
                "schema": options.schema,
            },
        },
    }


def load_json_schema(schema_path: Path) -> dict[str, Any]:
    """
    기능:
        구조화 추출에 사용할 JSON Schema 파일을 읽어 딕셔너리로 반환한다.

    입력:
        schema_path: JSON Schema 파일 경로

    출력:
        dict[str, Any]: JSON Schema 딕셔너리

    예외:
        FileNotFoundError: schema 파일이 존재하지 않는 경우
        ValueError: schema 파일의 최상위 JSON 값이 객체가 아닌 경우
        json.JSONDecodeError: schema 파일이 올바른 JSON 형식이 아닌 경우
    """
    resolved_path = schema_path.expanduser().resolve()

    if not resolved_path.is_file():
        raise FileNotFoundError(f"Extract schema file does not exist: {resolved_path}")

    schema = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError(f"Extract schema must be a JSON object: {resolved_path}")

    return schema
