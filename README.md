# Upstage Document Parse Batch

Python script for sending every file in `inputdataset` to Upstage Document Parse
and saving JSON and Markdown outputs to `outputdataset`. It can also run
schema-based structured metadata extraction (title, author, date, keywords,
table of contents, etc.) two ways:

- Upstage Information Extraction, sending the original document file.
- OpenAI Chat Completions, sending the Markdown text produced by Document Parse.

## Setup

Create a local `.env` file:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```env
UPSTAGE_API_KEY=YOUR_UPSTAGE_API_KEY
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

The script automatically loads `.env` from the project root. Existing
`UPSTAGE_API_KEY`/`OPENAI_API_KEY` shell environment variables take precedence,
and `--api-key`/`--openai-api-key` still override both. `OPENAI_API_KEY` is
only required when `--structured-extract` (or `--extract-schema`) is used.

No external Python package is required.

## Run

```powershell
py main.py
```

For each input file, the script creates outputs with the same base name:

```text
inputdataset/sample.pdf
outputdataset/sample.json
outputdataset/sample.md
outputdataset/sample.structured_upstage.json
outputdataset/sample.structured_openai.json
```

The `.structured_upstage.json` and `.structured_openai.json` files are only
created when `--structured-extract` (or `--extract-schema`) is used.

Optional batch examples:

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

By default, the script reads files from:

```text
inputdataset
```

Results are saved to:

```text
outputdataset
```

The default API endpoint is:

```text
https://api.upstage.ai/v1/document-ai/document-parse
```

The default Upstage Information Extraction endpoint is:

```text
https://api.upstage.ai/v1/information-extraction
```

The default OpenAI Chat Completions endpoint is:

```text
https://api.openai.com/v1/chat/completions
```

The default OpenAI model is `gpt-4o-mini`. You can override endpoints and the
model with:

```powershell
py main.py --structured-extract --extract-schema .\schemas\metadata_schema.example.json --extract-endpoint "https://api.upstage.ai/v1/information-extraction" --openai-endpoint "https://api.openai.com/v1/chat/completions" --openai-model gpt-4o-mini
```
