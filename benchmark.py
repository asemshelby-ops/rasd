"""The accuracy benchmark. One command:

    python benchmark.py
    python benchmark.py --model claude-sonnet-5-5

It sends the 35 test reports to the understanding function, compares the answers
with data/expected.csv, prints the report in Arabic and saves it in results/.
It always prints what the run cost, and stops if a run costs more than 1 dollar.
"""

import argparse
import sys
import time
from pathlib import Path

import anthropic

from rasd.cost import MAX_RUN_COST_USD, cost_usd
from rasd.data import load_expected, load_reports
from rasd.scoring import Run, render
from rasd.understand import DEFAULT_MODEL, KEY_VARIABLE, make_client, understand

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def check_access(client, model: str) -> None:
    """Asks the API one free question, so a bad key or model name stops us before any spending."""
    try:
        client.models.retrieve(model)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise RuntimeError(
            f"Anthropic rejected the Claude key. Check the value of {KEY_VARIABLE}."
        ) from None
    except anthropic.NotFoundError:
        raise RuntimeError(f"The model '{model}' does not exist, or this key cannot use it.") from None
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"The Claude API answered with error {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Could not reach the Claude API. Check the internet connection.") from None


def run_benchmark(reports, understand_one, model: str, max_cost_usd: float = MAX_RUN_COST_USD, on_progress=None) -> Run:
    """Runs understand_one(text) on every report, watching the cost after each call."""
    cost_usd(model, 0, 0)  # fails here, before any spending, if the model has no known price
    results = {}
    input_tokens = output_tokens = 0
    stopped = False
    start = time.perf_counter()
    for position, report in enumerate(reports, start=1):
        if on_progress:
            on_progress(position, len(reports))
        answer = understand_one(report.text)
        results[report.id] = answer
        input_tokens += answer.input_tokens
        output_tokens += answer.output_tokens
        if cost_usd(model, input_tokens, output_tokens) > max_cost_usd:
            stopped = True
            break
    return Run(model=model, results=results, seconds=time.perf_counter() - start, stopped_at_cost_limit=stopped)


def main() -> None:
    # Windows terminals often cannot print Arabic; never crash because of that.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Rasd accuracy benchmark")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model to test (default: {DEFAULT_MODEL})")
    model = parser.parse_args().model

    try:
        cost_usd(model, 0, 0)
        client = make_client()
        check_access(client, model)
    except (RuntimeError, ValueError) as problem:
        sys.exit(f"Benchmark not run. {problem}")

    reports = load_reports()
    run = run_benchmark(
        reports,
        lambda text: understand(text, client, model),
        model,
        on_progress=lambda position, total: print(f"‏جارٍ فهم البلاغ {position} من {total}", flush=True),
    )
    text = render(run, reports, load_expected())

    RESULTS_DIR.mkdir(exist_ok=True)
    saved = RESULTS_DIR / f"benchmark_{model}.txt"
    saved.write_text(text, encoding="utf-8-sig")
    print()
    print(text)
    print(f"‏حُفظ التقرير في الملف: {saved.relative_to(RESULTS_DIR.parent)}")


if __name__ == "__main__":
    main()
