"""
파일명: chat_completion.py
작성자: Codex
작성일: 2026-06-12
수정일: 2026-06-12

개요:
    OpenAI 호환 chat completions 엔드포인트(Upstage Information Extraction,
    OpenAI 등)에 JSON 요청을 보내고, response_format(json_schema)으로
    추출된 콘텐츠를 dict로 반환하는 공통 로직을 제공한다.
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


def send_chat_completion(
    endpoint: str,
    api_key: str,
    payload: dict,
    timeout: int,
    label: str,
    provider: str,
) -> dict:
    """
    기능:
        OpenAI 호환 chat completions API에 JSON 요청을 보내고
        response_format으로 추출된 JSON 콘텐츠를 dict로 반환한다.

    입력:
        endpoint: chat completions API 엔드포인트
        api_key: Authorization: Bearer 헤더에 사용할 API 키
        payload: model/messages/response_format을 포함한 요청 본문
        timeout: 요청 제한 시간(초)
        label: 로그 및 오류 메시지에 표시할 이름
        provider: 로그 및 오류 메시지에 표시할 API 제공자 이름

    출력:
        dict: response_format 스키마에 맞춰 추출된 필드 딕셔너리

    예외:
        RuntimeError: API 연결 실패, 비정상 응답, JSON 파싱 실패가 발생한 경우
    """
    body = json.dumps(payload).encode("utf-8")
    headers = {
        # Do not log this header; it contains the API key.
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    request = Request(endpoint, data=body, headers=headers, method="POST")

    try:
        logger.info("Sending request to %s: %s", provider, label)
        with urlopen(request, timeout=timeout) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        status_code = exc.code
        response_body = exc.read().decode("utf-8", errors="replace")
        logger.warning("%s returned HTTP error for %s: %s", provider, label, status_code)
    except URLError as exc:
        logger.error("Failed to connect to %s API for %s: %s", provider, label, exc)
        raise RuntimeError(f"Failed to connect to {provider} API: {exc}") from exc

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as exc:
        logger.error("%s returned non-JSON response for %s", provider, label)
        raise RuntimeError(
            f"{provider} API returned non-JSON response ({status_code}): {response_body[:500]}"
        ) from exc

    if status_code < 200 or status_code >= 300:
        logger.error("%s request failed for %s: %s", provider, label, status_code)
        raise RuntimeError(
            f"{provider} API request failed ({status_code}): {json.dumps(result, ensure_ascii=False)}"
        )

    logger.info("%s completed for %s: %s", provider, label, status_code)
    return parse_chat_completion_content(result, label, provider)


def parse_chat_completion_content(result: dict, label: str, provider: str) -> dict:
    """
    기능:
        chat completions 응답에서 추출된 JSON 콘텐츠를 꺼내 dict로 반환한다.

    입력:
        result: API가 반환한 JSON 응답
        label: 오류 메시지에 표시할 이름
        provider: 오류 메시지에 표시할 API 제공자 이름

    출력:
        dict: response_format 스키마에 맞춰 추출된 필드 딕셔너리

    예외:
        RuntimeError: 응답에 추출 결과가 없거나 JSON으로 파싱할 수 없는 경우
    """
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"{provider} response has no content for {label}: {json.dumps(result, ensure_ascii=False)}"
        ) from exc

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{provider} content is not valid JSON for {label}: {content[:500]}"
        ) from exc
