"""
파일명: oa_doc_extract.py
작성자: Codex
작성일: 2026-06-12
수정일: 2026-06-12

개요:
    OpenAI Chat Completions API를 사용해 Document Parse가 생성한 Markdown 텍스트로부터
    JSON Schema(response_format) 기반 구조화 메타데이터를 추출하는 모듈이다.
"""

from dataclasses import dataclass
from typing import Any

from chat_completion import send_chat_completion


DEFAULT_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_SCHEMA_NAME = "document_metadata"


@dataclass(frozen=True)
class OpenAIExtractOptions:
    """
    기능:
        OpenAI 구조화 추출 요청에 필요한 설정 값을 보관한다.

    입력:
        api_key: OpenAI API 키
        endpoint: Chat Completions API 엔드포인트
        model: 사용할 모델 이름
        timeout: 요청 제한 시간(초)
        schema: 구조화 추출에 사용할 JSON Schema 딕셔너리
        schema_name: response_format.json_schema.name에 사용할 이름

    출력:
        OpenAIExtractOptions 인스턴스
    """

    api_key: str
    endpoint: str = DEFAULT_OPENAI_ENDPOINT
    model: str = DEFAULT_OPENAI_MODEL
    timeout: int = 120
    schema: dict[str, Any] | None = None
    schema_name: str = DEFAULT_SCHEMA_NAME


def structured_extract_markdown(
    markdown_text: str,
    label: str,
    options: OpenAIExtractOptions,
) -> dict:
    """
    기능:
        Document Parse Markdown 텍스트로부터 JSON Schema 기반 구조화 메타데이터를 추출한다.

    입력:
        markdown_text: Document Parse가 생성한 Markdown 본문
        label: 로그 및 오류 메시지에 표시할 이름(예: 원본 파일명)
        options: API 요청 옵션. schema 값이 반드시 필요하다.

    출력:
        dict: response_format 스키마에 맞춰 추출된 필드 딕셔너리

    예외:
        ValueError: schema 또는 API 키가 설정되지 않은 경우
        RuntimeError: API 연결 실패, 비정상 응답, JSON 파싱 실패가 발생한 경우
    """
    if not options.schema:
        raise ValueError("Structured extract requires a JSON schema.")

    if not options.api_key:
        raise ValueError("Missing OpenAI API key.")

    payload = build_openai_extract_payload(markdown_text, options)
    return send_chat_completion(
        endpoint=options.endpoint,
        api_key=options.api_key,
        payload=payload,
        timeout=options.timeout,
        label=label,
        provider="OpenAI information extraction",
    )


def build_openai_extract_payload(markdown_text: str, options: OpenAIExtractOptions) -> dict[str, Any]:
    """
    기능:
        OpenAI Chat Completions API에 보낼 JSON 요청 본문을 만든다.

    입력:
        markdown_text: Document Parse가 생성한 Markdown 본문
        options: API 요청 옵션

    출력:
        dict[str, Any]: model/messages/response_format을 포함한 요청 본문
    """
    instruction = (
        "Extract structured metadata from the following Markdown document. "
        "Respond using only information found in the document.\n\n"
        f"{markdown_text}"
    )

    return {
        "model": options.model,
        "messages": [{"role": "user", "content": instruction}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": options.schema_name,
                "strict": True,
                "schema": options.schema,
            },
        },
    }
