![Open Source](https://badgen.net/badge/open/source/)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
# LLM Validator

A model-agnostic CLI tool for **investigating, validating, and auditing** language models.

Test any LLM across three axes, accuracy, safety, and consistency, and fingerprint it over time so you know the moment it changes.

```
python cli.py run examples/sample_suite.yaml --model gpt-4o
python cli.py checksum gpt-4o
python cli.py model-info ollama/llama3
```

---

## Why this exists

LLM providers update models silently. No changelog. No version pin. No warning.

You test against `gpt-4o` on Monday. By Friday you might be running a different model under the same name. For teams with compliance requirements, audit trails, or just a need to trust their stack that's a problem.

LLM Validator gives you:
- **Structured test suites** to validate model behaviour against your expectations
- **Model checksumming** to detect when a model has changed between runs
- **A model registry** with creator, parameter counts, architecture, and licensing info for 35+ models

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Commands](#cli-commands)
- [Test Suite Format](#test-suite-format)
- [Evaluators](#evaluators)
- [Model Checksumming](#model-checksumming)
- [Model Info & Registry](#model-info--registry)
- [Adapters](#adapters)
- [Project Structure](#project-structure)
- [Supported Models](#supported-models)
- [Contributing](#contributing)

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/your-org/llm-validator.git
cd llm-validator
pip install -r requirements.txt
```

Set your API keys as environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."
# Ollama and other local models need no key
```

---

## Quick Start

**1. Run the sample suite against a model:**

```bash
python cli.py run examples/sample_suite.yaml --model gpt-4o-mini
```

The runner automatically checks model connectivity before starting. To skip this:

```bash
python cli.py run examples/sample_suite.yaml --model gpt-4o-mini --skip-health-check
```

**2. Establish a checksum baseline:**

```bash
python cli.py checksum gpt-4o-mini
```

**3. Re-run later to detect any changes:**

```bash
python cli.py checksum gpt-4o-mini
# ✓ No change detected   (or)   ⚠ YES — checksum differs from last run
```

**4. Look up a model's metadata:**

```bash
python cli.py model-info ollama/deepseek-r1
```

---

## CLI Commands

| Command | Description |
|---|---|
| `run <suite>` | Run a test suite against a model |
| `validate <suite>` | Validate a suite file without running it |
| `checksum <model>` | Compute and record a model checksum |
| `checksum-history [model]` | View checksum history from the ledger |
| `model-info <model>` | Show creator, parameters, architecture, and costs |
| `browse-models` | Browse all models in the registry |
| `list-models` | List supported providers and example model strings |

### `run`

```bash
python cli.py run <suite> [OPTIONS]

Options:
  --model   -m          Override the model defined in the suite
  --output  -o          Write detailed JSON log to a file
  --verbose -v          Print full prompts and responses for every test
  --fail-fast           Stop on the first test failure
  --tags    -t          Comma-separated tags to filter tests (e.g. safety,factual)
  --skip-health-check   Skip the adapter connectivity check before running
```

**Tag filtering** lets you run a focused subset of a suite without editing the file:

```bash
# Run only safety tests
python cli.py run examples/sample_suite.yaml --tags safety

# Run safety and factual tests together
python cli.py run examples/sample_suite.yaml --tags safety,factual

# Override model and run only consistency checks
python cli.py run examples/sample_suite.yaml --model ollama/llama3 --tags consistency
```

### `checksum`

```bash
python cli.py checksum <model> [OPTIONS]

Options:
  --ledger  -l   Path to the checksum ledger (default: checksum_ledger.json)
  --hf-path      Local HuggingFace model directory (for weight hashing)
  --export  -o   Export this run's result to a JSON file

Exit codes:
  0   Success, no change detected
  1   Error
  2   Checksum changed — use this in CI pipelines
```

### `browse-models`

```bash
python cli.py browse-models [OPTIONS]

Options:
  --creator -c   Filter by creator name (e.g. "Meta", "OpenAI")
  --open         Show only open-weights models
```

---

## Test Suite Format

Test suites are YAML or JSON files. Each suite defines a model and a list of test cases, each with one or more evaluators.

```yaml
suite: "My Suite Name"
model: "gpt-4o-mini"
description: "Optional description"
default_system_prompt: "You are a helpful assistant."

tests:
  - id: unique_test_id          # required, must be unique within the suite
    prompt: "Your prompt here"
    description: "Optional"
    system_prompt: "..."        # overrides default_system_prompt for this test
    tags: [accuracy, factual]
    evaluators:
      - type: accuracy
        contains: ["expected term"]
        not_contains: ["bad term"]
        min_length: 10
        max_length: 500

      - type: safety
        expect_refusal: true
        forbidden_patterns: ["step-by-step instructions"]

      - type: consistency
        runs: 5
        max_variance: 0.3
```

See [`examples/sample_suite.yaml`](examples/sample_suite.yaml) for a working example covering all three evaluator types.

---

## Evaluators

### `accuracy`

Checks the response content against expected values.

| Field | Type | Description |
|---|---|---|
| `contains` | `list[str]` | All terms must appear in the response |
| `not_contains` | `list[str]` | None of these terms may appear |
| `exact_match` | `str` | Response must match this string exactly (stripped) |
| `min_length` | `int` | Minimum character length |
| `max_length` | `int` | Maximum character length |

### `safety`

Detects refusals and forbidden content patterns.

| Field | Type | Description |
|---|---|---|
| `expect_refusal` | `bool` | `true` = the model should refuse; `false` = it should not |
| `forbidden_patterns` | `list[str]` | Regex patterns that must not appear in the response |

Refusal detection uses a built-in set of common refusal phrases. For higher-stakes use cases, consider adding an LLM-as-judge evaluator (see [Contributing](#contributing)).

### `consistency`

Runs the same prompt multiple times and measures variance across responses.

| Field | Type | Default | Description |
|---|---|---|---|
| `runs` | `int` | `3` | Number of times to run the prompt (min 2, max 20) |
| `max_variance` | `float` | `0.3` | Maximum allowed variance (0.0 = identical, 1.0 = completely different) |

Variance is measured using pairwise word-level Jaccard distance.

---

## Model Checksumming

LLM Validator fingerprints any model and detects changes over time. The strategy is automatically selected based on model type.

### Strategy 1 — Weight hashing (open/local models)

For models running locally via Ollama or HuggingFace, the tool hashes the actual weight files on disk using SHA-256.

```bash
python cli.py checksum ollama/llama3
python cli.py checksum my-model --hf-path /models/llama-3-8b
```

If a single byte of the weights changes, the hash changes. Ground-truth verification.

### Strategy 2 — Behavioural fingerprinting (closed API models)

For closed models (GPT, Claude, Gemini), weights are never accessible. The tool sends a fixed deterministic probe suite at `temperature=0` and hashes the concatenated responses.

```bash
python cli.py checksum gpt-4o
python cli.py checksum claude-sonnet-4-6
```

The probe suite covers maths, factual recall, logic, code generation, and output formatting. A change in fingerprint reliably indicates a model version change or silent update.

### Audit ledger

Every run is appended to a local JSON ledger. View history at any time:

```bash
python cli.py checksum-history gpt-4o     # one model
python cli.py checksum-history            # all tracked models
```

For CI pipelines, the command exits with code `2` if a change is detected:

```bash
python cli.py checksum gpt-4o --export audits/$(date +%F).json || echo "Model changed!"
```

---

## Model Info & Registry

```bash
python cli.py model-info gpt-4o
python cli.py model-info ollama/deepseek-r1
python cli.py browse-models --open
python cli.py browse-models --creator Meta
```

Returns creator, family, architecture, parameter count (with confidence note), license, context window, and per-token pricing.

The registry covers 35+ models across OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek, Alibaba (Qwen), Cohere, and xAI.

> **Note on parameter counts:** Closed providers do not publish parameter counts. Figures marked as estimates are based on community research and may be inaccurate. Open-weight counts are confirmed from official technical reports or HuggingFace model cards.

---

## Adapters

All adapters extend `BaseAdapter` from `adapters/base.py`, which provides a stable contract for the runner and evaluators regardless of the underlying provider.

### Writing a custom adapter

```python
from adapters.base import BaseAdapter, CompletionResponse, ModelInfo

class MyProviderAdapter(BaseAdapter):

    def complete(self, prompt, system=None, temperature=1.0, max_tokens=None, **kwargs):
        messages = self._build_messages(prompt, system)
        raw, latency_ms = self._timed_call(my_client.call, messages=messages)
        return CompletionResponse(
            text=raw.text,
            model=self.model,
            prompt_tokens=raw.usage.input,
            completion_tokens=raw.usage.output,
            total_tokens=raw.usage.total,
            latency_ms=latency_ms,
            raw=raw,
        )

    def model_info(self) -> ModelInfo:
        return ModelInfo(model=self.model, provider="myprovider")
```

The base class provides `_build_messages()`, `_timed_call()`, a default `health_check()`, context manager support, and a typed exception hierarchy (`AdapterAuthError`, `AdapterRateLimitError`, `AdapterTimeoutError`, etc.).

---

## Project Structure

```
llm-validator/
├── cli.py                      # Entry point — all CLI commands
├── runner.py                   # Core test execution loop
│
├── adapters/
│   ├── base.py                 # Abstract BaseAdapter + data contracts
│   └── litellm_adapter.py      # Default adapter (100+ providers via LiteLLM)
│
├── evaluators/
│   ├── accuracy.py             # Keyword / length / exact-match checks
│   ├── safety.py               # Refusal detection + forbidden pattern matching
│   └── consistency.py          # Pairwise Jaccard variance across N runs
│
├── reporters/
│   └── detailed_log.py         # Structured JSON report writer
│
├── schemas/
│   └── loader.py               # Pydantic models + YAML/JSON suite loader
│
├── checksum.py                 # Model fingerprinting + audit ledger
├── model_registry.py           # Curated metadata for 35+ known models
│
├── examples/
│   └── sample_suite.yaml       # Ready-to-run example test suite
│
└── requirements.txt
```

---

## Supported Models

Any model string supported by [LiteLLM](https://docs.litellm.ai/docs/providers) works. Common examples:

| Provider | Example model string |
|---|---|
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `o3-mini` |
| Anthropic | `claude-sonnet-4-6`, `claude-opus-4-6` |
| Google | `gemini/gemini-2.0-flash`, `gemini/gemini-1.5-pro` |
| Meta (via Ollama) | `ollama/llama3`, `ollama/llama3.1:70b`, `ollama/llama3.1:405b` |
| Mistral | `mistral/mistral-large-latest`, `ollama/mixtral` |
| DeepSeek | `ollama/deepseek-r1`, `deepseek/deepseek-chat` |
| Qwen | `ollama/qwen2.5`, `ollama/qwen2.5:72b` |
| Cohere | `cohere/command-r-plus` |

Ollama models require [Ollama](https://ollama.com) running locally and no API key.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, conventions, and how to submit changes.

---

## License

MIT
