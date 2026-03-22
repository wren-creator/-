# Contributing to LLM Validator

Thank you for your interest in contributing. This document covers everything you need to get set up, understand the codebase, and submit a quality contribution.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [How to Contribute](#how-to-contribute)
- [Development Guidelines](#development-guidelines)
- [Adding an Evaluator](#adding-an-evaluator)
- [Adding an Adapter](#adding-an-adapter)
- [Adding a Model to the Registry](#adding-a-model-to-the-registry)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Issues](#reporting-issues)

---

## Code of Conduct

This project is welcoming to contributors of all backgrounds. Please be respectful and constructive in all interactions, issues, pull requests, and discussions alike.

---

## Getting Started

### 1. Fork and clone

```bash
git clone https://github.com/wren-creator/llm-validator.git
cd llm-validator
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
.venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # linting, testing tools
```

> If `requirements-dev.txt` doesn't exist yet, install these manually:
> ```bash
> pip install pytest pytest-cov ruff mypy
> ```

### 4. Set up API keys

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

Or export them directly:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

You only need keys for the providers you intend to test against. Ollama requires no key but does need [Ollama](https://ollama.com) running locally.

### 5. Verify your setup

```bash
python cli.py validate examples/sample_suite.yaml
# ✓ Suite is valid: Basic LLM Validation
```

---

## Project Structure

```
llm-validator/
├── cli.py                  # All CLI commands (Typer)
├── runner.py               # Core test execution loop
├── checksum.py             # Model fingerprinting + audit ledger
├── model_registry.py       # Curated model metadata
│
├── adapters/
│   ├── base.py             # Abstract BaseAdapter — the interface contract
│   └── litellm_adapter.py  # Default adapter via LiteLLM
│
├── evaluators/
│   ├── accuracy.py         # Keyword / length / exact-match checks
│   ├── safety.py           # Refusal detection + forbidden patterns
│   └── consistency.py      # Pairwise Jaccard variance
│
├── reporters/
│   └── detailed_log.py     # JSON report writer
│
├── schemas/
│   └── loader.py           # Pydantic models + YAML/JSON loader
│
└── examples/
    └── sample_suite.yaml   # Ready-to-run example suite
```

The key architectural principle is **separation of concerns**:

- The **runner** only knows about adapters, evaluators, and reporters; it does not care about providers.
- **Adapters** translate between the runner's contract (`BaseAdapter`) and a specific provider's API.
- **Evaluators** operate only on response text and a config object, they are stateless and provider-agnostic.
- **Reporters** receive structured result dicts, they do not call any model.

---

## How to Contribute

Good first contributions include:

- Adding a new evaluator (e.g. LLM-as-judge, semantic similarity, toxicity scoring)
- Adding a new adapter (e.g. a direct OpenAI adapter, a vLLM adapter)
- Adding models to the registry
- Improving the behavioural fingerprint probe suite in `checksum.py`
- Writing or improving example test suites in `examples/`
- Bug fixes and documentation improvements

For larger changes (new CLI commands, architectural changes), please open an issue first to discuss the approach before writing code.

---

## Development Guidelines

### Code style

- Follow [PEP 8](https://peps.python.org/pep-0008/). Use `ruff` for linting: `ruff check .`
- Use type hints on all public functions and methods.
- Keep functions focused. If a function is doing more than one thing, split it.
- Prefer explicit over clever.

### Docstrings

Public classes and methods should have docstrings explaining what they do, their arguments, and what they return. Private helpers (`_prefixed`) need a one-liner at minimum.

```python
def evaluate(self, response: str, config: AccuracyConfig) -> dict:
    """
    Check the response against accuracy criteria.

    Args:
        response: The raw text returned by the model.
        config:   AccuracyEvaluator config from the test suite.

    Returns:
        dict with keys: evaluator (str), passed (bool), reason (str).
    """
```

### Tests

- Place tests in a `tests/` directory mirroring the source layout.
- Test evaluators against known inputs and expected outputs.
- Test adapters with mocked HTTP responses — do not make real API calls in tests.
- Run the suite: `pytest --cov=. tests/`

### Commits

Write clear, imperative commit messages:

```
Add LLM-as-judge evaluator
Fix Jaccard similarity edge case for empty responses
Add Gemma 3 to model registry
```

---

## Adding an Evaluator

Evaluators live in `evaluators/` and follow a simple pattern: a class with an `evaluate()` method that receives a response string and a config object, and returns a result dict.

### Step 1: Create the config in `schemas/loader.py`

```python
class MyEvaluator(BaseModel):
    type: str = "my_evaluator"
    my_param: str
    threshold: float = 0.5
```

Add it to the `EvaluatorConfig` union type and the `parsed_evaluators()` dispatch in `TestCase`.

### Step 2: Create the evaluator class

```python
# evaluators/my_evaluator.py

from typing import Dict, Any
from schemas.loader import MyEvaluator as MyEvaluatorConfig


class MyEvaluator:
    def evaluate(self, response: str, config: MyEvaluatorConfig) -> Dict[str, Any]:
        # Your logic here
        passed = True
        reason = "all checks passed"
        return {"evaluator": "my_evaluator", "passed": passed, "reason": reason}
```

The result dict must always contain:
- `evaluator` (str) — the evaluator type name
- `passed` (bool) — whether this check passed
- `reason` (str) — a human-readable explanation of the outcome

### Step 3: Register it in `runner.py`

```python
from evaluators.my_evaluator import MyEvaluator

EVALUATOR_MAP = {
    "accuracy": AccuracyEvaluator,
    "safety": SafetyEvaluator,
    "consistency": ConsistencyEvaluator,
    "my_evaluator": MyEvaluator,   # 👈 add this
}
```

### Step 4: Add an example to `examples/sample_suite.yaml`

Show how to use it so others can learn from a working example.

---

## Adding an Adapter

Adapters live in `adapters/` and must subclass `BaseAdapter`.

### Required methods

```python
from adapters.base import BaseAdapter, CompletionResponse, ModelInfo

class MyAdapter(BaseAdapter):

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> CompletionResponse:
        # Call your provider, return a CompletionResponse
        ...

    def model_info(self) -> ModelInfo:
        # Return metadata about the model
        ...
```

### Available base class utilities

| Method | Description |
|---|---|
| `self._build_messages(prompt, system)` | Returns an OpenAI-format messages list |
| `self._timed_call(fn, *args, **kwargs)` | Calls `fn` and returns `(result, latency_ms)` |
| `self.health_check()` | Default probe — override with a lighter check if available |
| `self.close()` | Called on context manager exit — override to release connections |

### Error handling

Raise from the typed exception hierarchy rather than bare exceptions:

```python
from adapters.base import AdapterAuthError, AdapterRateLimitError, AdapterTimeoutError

# Inside complete():
except ProviderAuthException as e:
    raise AdapterAuthError(str(e), provider="myprovider", model=self.model)
```

This allows the runner to handle specific failure modes cleanly.

---

## Adding a Model to the Registry

The registry lives in `model_registry.py`. Each entry is a `ModelMeta` dataclass.

```python
"my-org/my-model": ModelMeta(
    creator="My Org",
    family="My Model Family",
    parameters="7B",                            # None if undisclosed
    parameters_note="Confirmed by My Org",      # Always explain confidence
    release_year=2025,
    open_weights=True,
    architecture="Transformer (decoder-only)",
    license="Apache 2.0",
    hf_url="https://huggingface.co/my-org/my-model",
    notes="Optional extra context.",
),
```

**Guidelines for parameter counts:**

- If the provider has confirmed the count in an official technical report or model card, use that and note the source.
- If the count is a community estimate, say so explicitly: `"~70B (community estimate — not confirmed by provider)"`.
- If the provider has not disclosed it, set `parameters=None` and `parameters_note="Not disclosed by <Provider>"`.
- Never present an estimate as confirmed fact.

---

## Submitting a Pull Request

1. Create a branch from `main`:
   ```bash
   git checkout -b feat/my-evaluator
   ```

2. Make your changes, following the guidelines above.

3. Run linting and tests:
   ```bash
   ruff check .
   pytest tests/
   ```

4. Push your branch and open a pull request against `main`.

5. In the PR description:
   - Explain what the change does and why
   - Note any design decisions or trade-offs
   - Include example output or a test suite snippet if relevant

PRs are reviewed for correctness, test coverage, code clarity, and alignment with the project's architecture. Feedback is given constructively — expect a conversation, not just approval or rejection.

---

## Reporting Issues

When filing a bug report, please include:

- Your Python version (`python --version`)
- The command you ran
- The full error output
- The test suite file if the issue is suite-related (redact any sensitive prompt content)

For feature requests, describe the problem you're trying to solve, not just the solution you have in mind. This helps us understand the use case and consider alternatives.
