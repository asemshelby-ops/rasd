"""The accuracy benchmark.

    python benchmark.py

        Sends every test report to the everyday model, compares the answers with
        the expected ones, prints the report in Arabic and saves it in results/.
        The 35 main reports and the owner's holdout reports (data/holdout) are
        scored separately.

    python benchmark.py --compare claude-sonnet-5-5

        The one-time comparison with a larger model. Both models read the same
        reports, one after the other, and the gap in accuracy and cost is
        printed. Everything is saved in comparison/, which is committed.
        Project rule: this runs once only, so the command refuses a second time.

Every run prints what it cost, and stops if it costs more than 1 dollar.
"""

import argparse
import dataclasses
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

from rasd.cost import MAX_RUN_COST_USD, cost_usd
from rasd.data import load_expected, load_holdout, load_reports
from rasd.scoring import Holdout, Run, render, render_comparison
from rasd.understand import DEFAULT_MODEL, KEY_VARIABLE, make_client, understand

PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_DIR / "results"  # everyday runs; not committed
COMPARISON_DIR = PROJECT_DIR / "comparison"  # the one-time comparison; committed

SET_NAMES = {"main": "الأساسية", "holdout": "المحجوبة"}

# The benchmark sends many reports in a row, which the live system never does,
# so a new key can be told to slow down. That is not a wrong answer: here the
# client waits and asks again more times than the live system's 2.
RETRIES = 6


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


def run_benchmark(
    reports,
    understand_one,
    model: str,
    max_cost_usd: float = MAX_RUN_COST_USD,
    on_progress=None,
    already_spent_usd: float = 0.0,
) -> Run:
    """Runs understand_one(text) on every report, watching the cost after each call.

    already_spent_usd is what this command spent before this set of reports, so
    that one limit covers the whole command.
    """
    cost_usd(model, 0, 0)  # fails here, before any spending, if the model has no known price
    results = {}
    input_tokens = output_tokens = 0
    stopped = already_spent_usd > max_cost_usd
    start = time.perf_counter()
    for position, report in enumerate(reports, start=1):
        if stopped:
            break
        if on_progress:
            on_progress(position, len(reports))
        answer = understand_one(report.text)
        results[report.id] = answer
        input_tokens += answer.input_tokens
        output_tokens += answer.output_tokens
        stopped = already_spent_usd + cost_usd(model, input_tokens, output_tokens) > max_cost_usd
    return Run(model=model, results=results, seconds=time.perf_counter() - start, stopped_at_cost_limit=stopped)


def measure(
    model: str,
    understand_one,
    reports,
    holdout_set,
    max_cost_usd: float = MAX_RUN_COST_USD,
    on_progress=None,
    already_spent_usd: float = 0.0,
) -> tuple[Run, Holdout | None]:
    """One model reads the main reports and then the owner's holdout reports, if there are any.

    holdout_set is what load_holdout() returned: (reports, expected answers) or None.
    on_progress, if given, is called as on_progress("main" or "holdout", position, total).
    """

    def progress(set_name):
        return (lambda position, total: on_progress(set_name, position, total)) if on_progress else None

    run = run_benchmark(reports, understand_one, model, max_cost_usd, progress("main"), already_spent_usd)
    if holdout_set is None:
        return run, None
    held_reports, held_expected = holdout_set
    held_run = run_benchmark(
        held_reports, understand_one, model, max_cost_usd, progress("holdout"), already_spent_usd + run.cost
    )
    return run, Holdout(run=held_run, reports=held_reports, expected=held_expected)


def comparison_was_recorded() -> bool:
    return (COMPARISON_DIR / "answers.json").exists()


def answers_as_json(runs: list[Run], recorded_at: str) -> str:
    """What each model answered for each main report, so the comparison can be checked later."""
    return json.dumps(
        {
            "recorded_at": recorded_at,
            "note": "Raw answers of the one-time model comparison, for the main reports only.",
            "runs": [
                {
                    "model": run.model,
                    "seconds": round(run.seconds, 1),
                    "stopped_at_cost_limit": run.stopped_at_cost_limit,
                    "answers": {str(report_id): dataclasses.asdict(answer) for report_id, answer in run.results.items()},
                }
                for run in runs
            ],
        },
        ensure_ascii=False,
        indent=1,
    )


def _save(folder: Path, name: str, text: str) -> Path:
    """Saves a text file that Windows programs open as Arabic. Returns its path inside the project."""
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8-sig")
    return path.relative_to(folder.parent)


def main(argv=None) -> None:
    # Windows terminals often cannot print Arabic; never crash because of that.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Rasd accuracy benchmark")
    parser.add_argument(
        "--compare",
        metavar="MODEL",
        help=f"run the one-time comparison of {DEFAULT_MODEL} with this larger model, for example claude-sonnet-5-5",
    )
    larger = parser.parse_args(argv).compare
    models = [DEFAULT_MODEL, larger] if larger else [DEFAULT_MODEL]

    # Everything that can be checked for free is checked before the first paid call.
    try:
        if larger == DEFAULT_MODEL:
            raise ValueError(f"--compare needs a model other than the everyday one ({DEFAULT_MODEL}).")
        if larger and comparison_was_recorded():
            raise RuntimeError(
                "The larger-model comparison was already run; its results are in the comparison folder. "
                "Project rule: it runs once only. If the owner approves a new run, delete that folder first."
            )
        for model in models:
            cost_usd(model, 0, 0)
        client = make_client().with_options(max_retries=RETRIES)
        for model in models:
            check_access(client, model)
        reports, expected = load_reports(), load_expected()
        holdout_set = load_holdout()
    except (RuntimeError, ValueError) as problem:
        sys.exit(f"Benchmark not run. {problem}")

    measured = []  # one (run, holdout) pair per model
    spent = 0.0
    for model in models:
        run, holdout = measure(
            model,
            lambda text, model=model: understand(text, client, model),
            reports,
            holdout_set,
            on_progress=lambda set_name, position, total, model=model: print(
                f"‏{model}: جارٍ فهم البلاغات {SET_NAMES[set_name]}، {position} من {total}", flush=True
            ),
            already_spent_usd=spent,
        )
        spent += run.cost + (holdout.run.cost if holdout else 0.0)
        measured.append((run, holdout))

    saved = []
    folder = COMPARISON_DIR if larger else RESULTS_DIR
    if larger:
        # The raw answers are saved first: this run is not repeated, so nothing may be lost.
        recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        COMPARISON_DIR.mkdir(exist_ok=True)
        (COMPARISON_DIR / "answers.json").write_text(
            answers_as_json([run for run, _ in measured], recorded_at), encoding="utf-8"
        )
        saved.append(Path(COMPARISON_DIR.name) / "answers.json")

    texts = []
    for run, holdout in measured:
        text = render(run, reports, expected, holdout)
        texts.append(text)
        saved.append(_save(folder, f"benchmark_{run.model}.txt", text))
    if larger:
        text = f"‏تاريخ المقارنة: {recorded_at}\n" + render_comparison(measured[0][0], measured[1][0], reports, expected)
        text += f"\n‏التكلفة التقريبية لهذا التشغيل كله (النموذجان معاً): {spent:.4f} دولار\n"
        texts.append(text)
        saved.append(_save(folder, "comparison.txt", text))

    print()
    print("\n\n".join(texts))
    for path in saved:
        print(f"‏حُفظ في الملف: {path.as_posix()}")


if __name__ == "__main__":
    main()
