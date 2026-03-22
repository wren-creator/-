# -
Open-source LLM auditing framework


# LLM Validator

A model-agnostic CLI tool for investigating and validating LLMs across three axes:
**accuracy**, **safety**, and **consistency**.

---

## Installation

```bash
pip install -r requirements.txt
```

Set your API keys as environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Usage

### Run a test suite

```bash
python cli.py run examples/sample_suite.yaml
```

Override the model at runtime:

```bash
python cli.py run examples/sample_suite.yaml --model claude-sonnet-4-6
```

Save a detailed JSON log:

```bash
python cli.py run examples/sample_suite.yaml --output results/run1.json
```

Show full responses in terminal:

```bash
python cli.py run examples/sample_suite.yaml --verbose
```

Stop on first failure:

```bash
python cli.py run examples/sample_suite.yaml --fail-fast
```

### Validate a suite file (without running it)

```bash
python cli.py validate examples/sample_suite.yaml
```

### List supported models

```bash
python cli.py list-models
```

---

## Test Suite Format

```yaml
suite: "My Suite"
model: "gpt-4o-mini"            # default model (overridable via --model)
description: "Optional description"
default_system_prompt: "..."    # optional, applied to all tests

tests:
  - id: unique_test_id
    prompt: "Your prompt here"
    description: "Optional description"
    system_prompt: "..."        # overrides default_system_prompt
    tags: [accuracy, factual]
    evaluators:
      - type: accuracy
        contains: ["expected term"]
        not_contains: ["bad term"]
        min_length: 10
        max_length: 500

      - type: safety
        expect_refusal: true         # true = expect model to refuse
        forbidden_patterns: ["regex pattern"]

      - type: consistency
        runs: 5                      # number of times to run the prompt
        max_variance: 0.3            # 0.0 = identical, 1.0 = completely different
```

---

## Project Structure

```
llm-validator/
├── cli.py                  # Entry point
├── runner.py               # Core execution loop
├── adapters/
│   └── litellm_adapter.py  # Model-agnostic via LiteLLM
├── evaluators/
│   ├── accuracy.py         # Keyword / length checks
│   ├── safety.py           # Refusal detection + forbidden patterns
│   └── consistency.py      # Pairwise Jaccard variance
├── reporters/
│   └── detailed_log.py     # JSON report writer
├── schemas/
│   └── loader.py           # Pydantic models + YAML/JSON loader
├── examples/
│   └── sample_suite.yaml   # Example test suite
└── requirements.txt
```

---

## Supported Models

LiteLLM handles the model routing. Any model string LiteLLM supports works here:

| Provider  | Example model string             |
|-----------|----------------------------------|
| OpenAI    | `gpt-4o`, `gpt-4o-mini`         |
| Anthropic | `claude-sonnet-4-6`              |
| Ollama    | `ollama/llama3`                  |
| Mistral   | `mistral/mistral-large-latest`   |
| Gemini    | `gemini/gemini-1.5-pro`          |

---

## Extending

**Add a new evaluator:** Create `evaluators/my_eval.py` with an `evaluate(response, config)` method returning `{"evaluator": "...", "passed": bool, "reason": str}`. Register it in `runner.py`'s `EVALUATOR_MAP`.

**Add a new model provider:** No code needed, just use the LiteLLM model string. Set the appropriate API key env var.
