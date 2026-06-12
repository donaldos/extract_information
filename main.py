"""
파일명: main.py
작성자: Codex
작성일: 2026-06-12
수정일: 2026-06-12

개요:
    inputdataset 디렉토리의 문서를 순차적으로 Upstage Document API에 전달하고,
    Parse 결과 JSON/Markdown 파일과 선택적인 Structured Extract 결과를
    outputdataset 디렉토리에 저장한다.
"""

import argparse
import json
import logging
import os
import re
from pathlib import Path

from up_doc_extract import (
    DEFAULT_EXTRACT_ENDPOINT,
    DocumentExtractOptions,
    load_json_schema,
    structured_extract_document,
)
from oa_doc_extract import (
    DEFAULT_OPENAI_ENDPOINT,
    DEFAULT_OPENAI_MODEL,
    OpenAIExtractOptions,
    structured_extract_markdown,
)
from up_doc_parse import (
    DEFAULT_ENDPOINT,
    DocumentParseOptions,
    extract_markdown_from_parse_result,
    parse_document,
)


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = PROJECT_DIR / ".env"
DEFAULT_INPUT_DIR = PROJECT_DIR / "inputdataset"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputdataset"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

# Upstage Document Parse / Information Extraction이 지원하는 입력 파일 확장자.
SUPPORTED_INPUT_EXTENSIONS = {
    ".pdf",
    ".hwp",
    ".hwpx",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".tif",
    ".gif",
    ".webp",
    ".heic",
}

logger = logging.getLogger(__name__)


def load_env_file(path: Path = DEFAULT_ENV_PATH) -> None:
    """
    기능:
        .env 파일의 KEY=VALUE 설정을 현재 프로세스 환경변수로 로드한다.
        이미 외부에서 설정된 환경변수는 덮어쓰지 않는다.

    입력:
        path: 읽을 .env 파일 경로

    출력:
        없음

    예외:
        ValueError: .env 라인 형식 또는 환경변수 키 형식이 올바르지 않은 경우
    """
    env_path = path.expanduser()
    if not env_path.is_absolute():
        env_path = PROJECT_DIR / env_path

    if not env_path.is_file():
        return

    for line_number, raw_line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            raise ValueError(f"Invalid .env line {line_number}: expected KEY=VALUE")

        key, value = line.split("=", 1)
        key = key.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise ValueError(f"Invalid .env key on line {line_number}: {key}")

        # Keep shell-provided environment variables higher priority than .env.
        os.environ.setdefault(key, parse_env_value(value))


def parse_env_value(value: str) -> str:
    """
    기능:
        .env 파일의 값 문자열을 파싱한다.
        따옴표로 감싼 값과 인라인 주석을 처리한다.

    입력:
        value: .env 파일에서 읽은 원본 값 문자열

    출력:
        파싱된 환경변수 값 문자열
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    return value.split("#", 1)[0].rstrip()


def parse_args() -> argparse.Namespace:
    """
    기능:
        배치 실행에 필요한 명령행 인자를 정의하고 파싱한다.

    입력:
        없음. argparse가 sys.argv를 사용한다.

    출력:
        argparse.Namespace: 파싱된 실행 옵션
    """
    parser = argparse.ArgumentParser(
        description="Batch parse documents in inputdataset with Upstage Document Parse."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory containing input documents. Default: {DEFAULT_INPUT_DIR}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to save JSON and Markdown outputs. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("UPSTAGE_API_KEY"),
        help="Upstage API key. Defaults to UPSTAGE_API_KEY from .env or environment.",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Document Parse API endpoint. Default: {DEFAULT_ENDPOINT}",
    )
    parser.add_argument(
        "--ocr",
        choices=["auto", "force"],
        default="auto",
        help="OCR mode. Default: auto",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["markdown", "text", "html"],
        help="Output formats requested from the API. Default: markdown text html",
    )
    parser.add_argument(
        "--coordinates",
        action="store_true",
        help="Request coordinate data if supported by the API.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Request timeout in seconds. Default: 120",
    )
    parser.add_argument(
        "--structured-extract",
        action="store_true",
        help=(
            "Run schema-based structured extract with both Upstage Information Extraction "
            "(.structured_upstage.json) and OpenAI (.structured_openai.json)."
        ),
    )
    parser.add_argument(
        "--extract-schema",
        type=Path,
        help="JSON Schema file for --structured-extract.",
    )
    parser.add_argument(
        "--extract-prompt",
        help="Optional instruction prompt for Upstage Information Extract.",
    )
    parser.add_argument(
        "--extract-endpoint",
        default=os.getenv("UPSTAGE_EXTRACT_ENDPOINT", DEFAULT_EXTRACT_ENDPOINT),
        help=f"Information Extract API endpoint. Default: {DEFAULT_EXTRACT_ENDPOINT}",
    )
    parser.add_argument(
        "--openai-api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="OpenAI API key. Defaults to OPENAI_API_KEY from .env or environment.",
    )
    parser.add_argument(
        "--openai-model",
        default=DEFAULT_OPENAI_MODEL,
        help=f"OpenAI model for Markdown-based structured extract. Default: {DEFAULT_OPENAI_MODEL}",
    )
    parser.add_argument(
        "--openai-endpoint",
        default=os.getenv("OPENAI_EXTRACT_ENDPOINT", DEFAULT_OPENAI_ENDPOINT),
        help=f"OpenAI Chat Completions API endpoint. Default: {DEFAULT_OPENAI_ENDPOINT}",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files when both output JSON and Markdown already exist.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop the batch immediately when a document fails.",
    )
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level. Default: INFO",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Optional path to also write logs to a file.",
    )
    return parser.parse_args()


def configure_logging(level_name: str, log_file: Path | None = None) -> None:
    """
    기능:
        콘솔 로그를 설정하고, 선택적으로 로그 파일에도 같은 내용을 저장한다.

    입력:
        level_name: DEBUG, INFO, WARNING, ERROR, CRITICAL 중 하나
        log_file: 로그를 파일로 저장할 경로. None이면 콘솔에만 출력한다.

    출력:
        없음
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        resolved_log_file = log_file.expanduser()
        if not resolved_log_file.is_absolute():
            resolved_log_file = PROJECT_DIR / resolved_log_file

        resolved_log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(resolved_log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level_name),
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )


def iter_input_files(input_dir: Path) -> list[Path]:
    """
    기능:
        입력 디렉토리에서 SUPPORTED_INPUT_EXTENSIONS에 해당하는 파일 목록을
        이름 기준으로 정렬해서 반환한다. 지원하지 않는 확장자의 파일은 건너뛴다.

    입력:
        input_dir: 문서/이미지 파일이 들어 있는 입력 디렉토리

    출력:
        list[Path]: 정렬된 입력 파일 경로 목록
    """
    files = sorted(
        (path for path in input_dir.iterdir() if path.is_file()),
        key=lambda path: path.name.lower(),
    )

    supported_files = []
    for path in files:
        if path.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS:
            supported_files.append(path)
        else:
            logger.info("Skipped unsupported file: %s", path.name)

    return supported_files


def build_output_paths(source_path: Path, output_dir: Path) -> dict[str, Path]:
    """
    기능:
        입력 파일명과 동일한 기본 이름을 사용해 단계별 출력 경로를 만든다.

    입력:
        source_path: 원본 입력 파일 경로
        output_dir: 결과물을 저장할 디렉토리

    출력:
        dict[str, Path]: parse_json, markdown, structured_upstage_json, structured_openai_json 출력 경로
    """
    return {
        "parse_json": output_dir / f"{source_path.stem}.json",
        "markdown": output_dir / f"{source_path.stem}.md",
        "structured_upstage_json": output_dir / f"{source_path.stem}.structured_upstage.json",
        "structured_openai_json": output_dir / f"{source_path.stem}.structured_openai.json",
    }


def should_run_structured_extract(args: argparse.Namespace) -> bool:
    """
    기능:
        구조화 추출을 실행해야 하는지 판단한다.
        schema 파일이 지정되면 --structured-extract를 생략해도 실행 대상으로 본다.

    입력:
        args: parse_args()에서 반환된 실행 옵션

    출력:
        bool: 구조화 추출 실행 여부
    """
    return bool(args.structured_extract or args.extract_schema)


def requested_outputs_exist(output_paths: dict[str, Path], args: argparse.Namespace) -> bool:
    """
    기능:
        현재 실행 옵션에서 필요한 출력 파일이 이미 모두 존재하는지 확인한다.

    입력:
        output_paths: build_output_paths()가 반환한 단계별 출력 경로
        args: parse_args()에서 반환된 실행 옵션

    출력:
        bool: 필요한 출력 파일이 모두 존재하면 True, 하나라도 없으면 False
    """
    required_paths = [output_paths["parse_json"], output_paths["markdown"]]

    if should_run_structured_extract(args):
        required_paths.append(output_paths["structured_upstage_json"])
        required_paths.append(output_paths["structured_openai_json"])

    return all(path.is_file() for path in required_paths)


def process_batch(args: argparse.Namespace) -> int:
    """
    기능:
        입력 디렉토리의 모든 파일을 순차적으로 파싱하고 결과 파일을 저장한다.
        기본적으로 개별 파일 실패 시 실패 목록에 기록하고 다음 파일 처리를 계속한다.

    입력:
        args: parse_args()에서 반환된 실행 옵션

    출력:
        int: 정상 완료 시 0, 하나 이상의 실패가 있으면 1

    예외:
        FileNotFoundError: 입력 디렉토리가 존재하지 않는 경우
        ValueError: API 키가 설정되지 않은 경우
    """
    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    if not args.api_key:
        raise ValueError(
            "Missing API key. Set UPSTAGE_API_KEY in .env or pass --api-key explicitly."
        )

    structured_schema = None
    if should_run_structured_extract(args):
        if not args.extract_schema:
            raise ValueError("Structured extract requires --extract-schema.")
        if not args.openai_api_key:
            raise ValueError(
                "Missing OpenAI API key. Set OPENAI_API_KEY in .env or pass --openai-api-key explicitly."
            )
        structured_schema = load_json_schema(args.extract_schema)
        logger.info("Loaded extract schema: %s", args.extract_schema)

    output_dir.mkdir(parents=True, exist_ok=True)
    input_files = iter_input_files(input_dir)

    if not input_files:
        logger.warning("No input files found: %s", input_dir)
        return 0

    logger.info("Input directory: %s", input_dir)
    logger.info("Output directory: %s", output_dir)
    logger.info("Found %s input file(s)", len(input_files))

    # Build immutable request options once and reuse them for every document.
    parse_options = DocumentParseOptions(
        api_key=args.api_key,
        endpoint=args.endpoint,
        ocr=args.ocr,
        formats=tuple(args.formats),
        coordinates=args.coordinates,
        timeout=args.timeout,
    )
    extract_options = DocumentExtractOptions(
        api_key=args.api_key,
        endpoint=args.extract_endpoint,
        timeout=args.timeout,
        prompt=args.extract_prompt,
        schema=structured_schema,
    )
    openai_extract_options = OpenAIExtractOptions(
        api_key=args.openai_api_key,
        endpoint=args.openai_endpoint,
        model=args.openai_model,
        timeout=args.timeout,
        schema=structured_schema,
    )
    failures: list[tuple[Path, Exception]] = []

    for index, input_path in enumerate(input_files, start=1):
        # Each input file always produces parse outputs and may produce extract outputs.
        output_paths = build_output_paths(input_path, output_dir)

        if args.skip_existing and requested_outputs_exist(output_paths, args):
            logger.info(
                "[%s/%s] Skipped existing: %s",
                index,
                len(input_files),
                input_path.name,
            )
            continue

        logger.info("[%s/%s] Parsing: %s", index, len(input_files), input_path.name)

        try:
            result = parse_document(input_path, parse_options)
            markdown = extract_markdown_from_parse_result(result)

            output_paths["parse_json"].write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            output_paths["markdown"].write_text(markdown, encoding="utf-8")

            logger.info("Saved JSON: %s", output_paths["parse_json"])
            logger.info("Saved Markdown: %s", output_paths["markdown"])

            if should_run_structured_extract(args):
                structured_upstage_result = structured_extract_document(input_path, extract_options)
                output_paths["structured_upstage_json"].write_text(
                    json.dumps(structured_upstage_result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info("Saved Upstage Structured Extract JSON: %s", output_paths["structured_upstage_json"])

                structured_openai_result = structured_extract_markdown(
                    markdown, input_path.name, openai_extract_options
                )
                output_paths["structured_openai_json"].write_text(
                    json.dumps(structured_openai_result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info("Saved OpenAI Structured Extract JSON: %s", output_paths["structured_openai_json"])
        except Exception as exc:
            # Batch mode keeps going by default so one bad file does not block the rest.
            failures.append((input_path, exc))
            logger.error(
                "Failed to parse %s: %s",
                input_path.name,
                exc,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            if args.stop_on_error:
                logger.error("Stopping batch because --stop-on-error is enabled")
                break

    if failures:
        logger.error("Completed with %s failure(s)", len(failures))
        for failed_path, exc in failures:
            logger.error("Failed file: %s - %s", failed_path.name, exc)
        return 1

    logger.info("Completed successfully: %s file(s)", len(input_files))
    return 0


def main() -> None:
    """
    기능:
        프로그램 진입점이다.
        .env 로드, 명령행 인자 파싱, 로그 설정, 배치 실행을 순서대로 수행한다.

    입력:
        없음

    출력:
        없음. process_batch() 결과 코드를 프로그램 종료 코드로 사용한다.
    """
    load_env_file()
    args = parse_args()
    configure_logging(args.log_level, args.log_file)
    logger.debug("Loaded environment file if present: %s", DEFAULT_ENV_PATH)
    raise SystemExit(process_batch(args))


if __name__ == "__main__":
    main()
