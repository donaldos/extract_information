# Upstage Document Parse 배치 처리

`inputdataset` 디렉토리의 모든 파일을 Upstage Document Parse API로 전송하고,
그 결과를 JSON/Markdown 형식으로 `outputdataset` 디렉토리에 저장하는 Python 스크립트입니다.
또한 JSON Schema 기반 구조화 메타데이터 추출(제목, 작성자, 날짜, 키워드, 목차 등)을
다음 두 가지 방식으로 실행할 수 있습니다.

- **Upstage Information Extraction**: 원본 문서 파일을 그대로 전송
- **OpenAI Chat Completions**: Document Parse가 생성한 Markdown 텍스트를 전송

## 처리 프로세스

`py main.py` 실행 시 아래 순서로 처리가 진행됩니다.

```text
1. .env / 명령행 인자 로드
        │
2. inputdataset 디렉토리 스캔
   └─ 지원 확장자(SUPPORTED_INPUT_EXTENSIONS)만 필터링
        │
3. 파일별 순차 처리 ─────────────────────────────────────┐
   │  3-1. Upstage Document Parse API 호출               │
   │        └─ sample.json (Parse 결과 전체)             │
   │        └─ sample.md   (Markdown 본문)               │
   │                                                      │
   │  3-2. (옵션) --structured-extract / --extract-schema │
   │        ├─ Upstage Information Extraction            │
   │        │   원본 파일 → sample.structured_upstage.json│
   │        └─ OpenAI Chat Completions                   │
   │            sample.md → sample.structured_openai.json│
   └──────────────────────────────────────────────────────┘
        │
4. 결과를 outputdataset 디렉토리에 저장, 실패 목록 로그 출력
```

- **1단계**: `.env`에서 `UPSTAGE_API_KEY`/`OPENAI_API_KEY` 등을 로드하고, 명령행 옵션을 파싱합니다.
- **2단계**: `inputdataset`의 파일 중 [지원 입력 파일 형식](#지원-입력-파일-형식)에 해당하는 파일만 이름순으로 처리 대상에 포함합니다. 그 외 파일은 로그에 남기고 건너뜁니다.
- **3단계**: 파일마다 다음을 수행합니다.
  - Document Parse API로 원본 문서를 JSON/Markdown으로 변환합니다.
  - `--structured-extract`(또는 `--extract-schema`)가 지정된 경우, 동일한 JSON Schema를 사용해 Upstage Information Extraction(원본 파일 기반)과 OpenAI Chat Completions(Markdown 기반) 양쪽에서 구조화 정보를 추출합니다. 두 결과는 상호 비교/검증용으로 별도 파일에 저장됩니다.
- **4단계**: 모든 결과 파일은 `outputdataset`에 저장되며, 처리 중 실패한 파일은 실패 목록으로 로그에 기록됩니다. `--stop-on-error` 옵션을 주면 첫 실패 시 배치를 즉시 중단합니다.

## 설치

로컬 `.env` 파일을 생성합니다.

```powershell
Copy-Item .env.example .env
```

`.env` 파일을 편집합니다.

```env
UPSTAGE_API_KEY=YOUR_UPSTAGE_API_KEY
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

스크립트는 프로젝트 루트의 `.env`를 자동으로 로드합니다. 이미 셸 환경변수로
`UPSTAGE_API_KEY`/`OPENAI_API_KEY`가 설정되어 있으면 `.env` 값보다 우선하며,
`--api-key`/`--openai-api-key` 옵션은 둘 다보다 우선합니다. `OPENAI_API_KEY`는
`--structured-extract`(또는 `--extract-schema`)를 사용할 때만 필요합니다.

외부 Python 패키지 설치는 필요하지 않습니다.

## 지원 입력 파일 형식

`inputdataset` 디렉토리에 있는 파일 중 다음 확장자만 처리 대상으로 선택됩니다.
지원하지 않는 확장자의 파일은 건너뛰고 로그에 남깁니다.

```text
.pdf
.hwp, .hwpx
.doc, .docx
.ppt, .pptx
.xls, .xlsx
.png, .jpg, .jpeg, .bmp, .tiff, .tif, .gif, .webp, .heic
```

## 실행

```powershell
py main.py
```

각 입력 파일에 대해 동일한 기본 이름(base name)으로 다음 출력 파일들이 생성됩니다.

```text
inputdataset/sample.pdf
outputdataset/sample.json
outputdataset/sample.md
outputdataset/sample.structured_upstage.json
outputdataset/sample.structured_openai.json
```

`.structured_upstage.json`과 `.structured_openai.json`은 `--structured-extract`
(또는 `--extract-schema`)를 사용할 때만 생성됩니다.

자주 사용하는 실행 예시는 다음과 같습니다.

```powershell
py main.py --ocr force --coordinates
py main.py --formats markdown html
py main.py --input-dir .\inputdataset --output-dir .\outputdataset
py main.py --skip-existing
py main.py --stop-on-error
py main.py --log-level DEBUG
py main.py --log-file .\outputdataset\batch.log
py main.py --structured-extract --extract-schema .\schemas\metadata_schema.example.json
```

기본적으로 스크립트는 다음 디렉토리에서 파일을 읽습니다.

```text
inputdataset
```

결과는 다음 디렉토리에 저장됩니다.

```text
outputdataset
```

## API 엔드포인트

Document Parse API 기본 엔드포인트:

```text
https://api.upstage.ai/v1/document-ai/document-parse
```

Upstage Information Extraction 기본 엔드포인트:

```text
https://api.upstage.ai/v1/information-extraction
```

OpenAI Chat Completions 기본 엔드포인트:

```text
https://api.openai.com/v1/chat/completions
```

기본 OpenAI 모델은 `gpt-4o-mini`입니다. 엔드포인트와 모델은 다음과 같이
직접 지정할 수 있습니다.

```powershell
py main.py --structured-extract --extract-schema .\schemas\metadata_schema.example.json --extract-endpoint "https://api.upstage.ai/v1/information-extraction" --openai-endpoint "https://api.openai.com/v1/chat/completions" --openai-model gpt-4o-mini
```

## 구조화 추출 스키마

`--extract-schema`에 지정하는 JSON Schema는 Upstage Information Extraction과
OpenAI Chat Completions 양쪽에 동일하게 사용되며, 둘 중 더 제약이 강한
Upstage Information Extraction 규칙을 따라야 합니다.

- 최상위(root)는 `type: object`이어야 합니다.
- **최상위 properties는 `object` 타입을 사용할 수 없습니다.** `string`,
  `number`, `integer`, `boolean`, `array`만 허용됩니다. object가 필요하면
  array의 `items`로 감싸야 합니다.
- 모든 property는 `required` 배열에 포함되어야 하며, `additionalProperties`는
  `false`로 설정해야 합니다(strict mode).

`schemas/` 디렉토리의 예시 파일:

- `schemas/metadata_schema.example.json`: 문서 제목/작성자/날짜/키워드/목차 등
  일반 문서 메타데이터 추출용 스키마
- `schemas/real_estate_contract_schema.example.json`: 부동산 계약서의 소재지,
  토지/건물 정보, 매매대금/계약금/중도금/잔금 및 지급일 등을 추출하는 스키마
