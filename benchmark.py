"""The accuracy benchmark.

    python benchmark.py

        Sends every test report to the everyday model, compares the answers with
        the expected ones, prints the report in Arabic and saves it in results/.
        The main reports and the holdout reports (data/holdout) are scored separately.

    python benchmark.py --repeat 3

        The same, three times in a row, and then what changed between the runs:
        how many reports got a different priority, type, place or supervisor flag.

    python benchmark.py --compare-holdout claude-sonnet-5-5

        The comparison the owner approved for the holdout reports: the everyday
        model and a larger one read the holdout reports only. It runs once, and
        only when there are holdout reports. Everything is saved in comparison/.

    python benchmark.py --compare claude-sonnet-5-5

        The first comparison, on the main reports. It was run once on
        25 November 2026, so this command now refuses.

Priority is always scored for the journey stage the expected answers were
written for (data.EXPECTED_STAGE), whatever the live setting in routing.py says.

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
from rasd.data import EXPECTED_STAGE, load_expected, load_holdout, load_reports
from rasd.scoring import Holdout, Run, render, render_comparison, render_holdout, render_stability
from rasd.understand import DEFAULT_MODEL, KEY_VARIABLE, make_client, understand

PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_DIR / "results"  # everyday runs; not committed
COMPARISON_DIR = PROJECT_DIR / "comparison"  # the comparisons that run once; committed

SET_NAMES = {"main": "الأساسية", "holdout": "المحجوبة"}

# The benchmark sends many reports in a row, which the live system never does,
# so a new key can be told to slow down. That is not a wrong answer: here the
# client waits and asks again more times than the live system's 2.
RETRIES = 6

# Words copied from a message. They are left out of anything saved about holdout reports.
WORDS_FROM_THE_MESSAGE = ("number_words", "risk_words")


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
    """One model reads the main reports and then the holdout reports, if there are any.

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


def holdout_comparison_was_recorded() -> bool:
    return (COMPARISON_DIR / "holdout_answers.json").exists()


def answers_as_json(runs: list[Run], recorded_at: str, note: str, leave_out=()) -> str:
    """What each model answered for each report, so a comparison can be checked later.

    leave_out names the fields that must not be saved.
    """

    def as_saved(answer) -> dict:
        return {field: value for field, value in dataclasses.asdict(answer).items() if field not in leave_out}

    return json.dumps(
        {
            "recorded_at": recorded_at,
            "note": note,
            "runs": [
                {
                    "model": run.model,
                    "seconds": round(run.seconds, 1),
                    "stopped_at_cost_limit": run.stopped_at_cost_limit,
                    "answers": {str(report_id): as_saved(answer) for report_id, answer in run.results.items()},
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


def _reader(client, model: str):
    """The function that reads one message with this model, at the stage the expected answers use."""
    return lambda text: understand(text, client, model, stage=EXPECTED_STAGE)


def _announce(model: str):
    return lambda set_name, position, total: print(
        f"‏{model}: جارٍ فهم البلاغات {SET_NAMES[set_name]}، {position} من {total}", flush=True
    )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# The three things the command can do. Each returns (texts to print, files saved).
# ---------------------------------------------------------------------------


def everyday_run(client, reports, expected, holdout_set, repeat: int):
    """The everyday model reads everything, `repeat` times."""
    measured = []  # one (run, holdout) pair per time
    spent = 0.0
    for _ in range(repeat):
        run, holdout = measure(
            DEFAULT_MODEL, _reader(client, DEFAULT_MODEL), reports, holdout_set,
            on_progress=_announce(DEFAULT_MODEL), already_spent_usd=spent,
        )  # fmt: skip
        spent += run.cost + (holdout.run.cost if holdout else 0.0)
        measured.append((run, holdout))

    if repeat == 1:
        run, holdout = measured[0]
        texts = [render(run, reports, expected, holdout)]
    else:
        texts = [
            f"‏======== التشغيل {number} من {repeat} ========\n" + render(run, reports, expected, holdout)
            for number, (run, holdout) in enumerate(measured, start=1)
        ]
        stability = render_stability([run for run, _ in measured], reports, expected)
        if holdout_set is not None:
            held_reports, held_expected = holdout_set
            stability += "\n" + render_stability(
                [holdout.run for _, holdout in measured], held_reports, held_expected, holdout=True
            )
        stability += f"\n‏التكلفة التقريبية لهذا التشغيل كله ({repeat} تشغيلات): {spent:.4f} دولار\n"
        texts.append(stability)

    saved = [_save(RESULTS_DIR, f"benchmark_{DEFAULT_MODEL}.txt", "\n\n".join(texts))]
    return texts, saved


def first_comparison(client, larger: str, reports, expected, holdout_set):
    """Both models read the main reports (and the holdout reports, if there are any)."""
    measured = []
    spent = 0.0
    for model in (DEFAULT_MODEL, larger):
        run, holdout = measure(
            model, _reader(client, model), reports, holdout_set, on_progress=_announce(model), already_spent_usd=spent
        )
        spent += run.cost + (holdout.run.cost if holdout else 0.0)
        measured.append((run, holdout))

    # The raw answers are saved first: this run is not repeated, so nothing may be lost.
    recorded_at = _now()
    COMPARISON_DIR.mkdir(exist_ok=True)
    note = "Raw answers of the first model comparison, for the main reports only."
    (COMPARISON_DIR / "answers.json").write_text(
        answers_as_json([run for run, _ in measured], recorded_at, note), encoding="utf-8"
    )
    saved = [Path(COMPARISON_DIR.name) / "answers.json"]

    texts = []
    for run, holdout in measured:
        texts.append(render(run, reports, expected, holdout))
        saved.append(_save(COMPARISON_DIR, f"benchmark_{run.model}.txt", texts[-1]))
    gap = f"‏تاريخ المقارنة: {recorded_at}\n" + render_comparison(measured[0][0], measured[1][0], reports, expected)
    gap += f"\n‏التكلفة التقريبية لهذا التشغيل كله (النموذجان معاً): {spent:.4f} دولار\n"
    texts.append(gap)
    saved.append(_save(COMPARISON_DIR, "comparison.txt", gap))
    return texts, saved


def holdout_comparison(client, larger: str, holdout_set):
    """Both models read the holdout reports only. No word of a holdout report is printed or saved."""
    held_reports, held_expected = holdout_set
    runs = []
    spent = 0.0
    for model in (DEFAULT_MODEL, larger):
        announce = _announce(model)
        run = run_benchmark(
            held_reports, _reader(client, model), model,
            on_progress=lambda position, total: announce("holdout", position, total), already_spent_usd=spent,
        )  # fmt: skip
        spent += run.cost
        runs.append(run)

    # The raw answers are saved first: this run is not repeated, so nothing may be lost.
    recorded_at = _now()
    COMPARISON_DIR.mkdir(exist_ok=True)
    note = "Raw answers of the model comparison on the holdout reports. Words copied from the messages are left out."
    (COMPARISON_DIR / "holdout_answers.json").write_text(
        answers_as_json(runs, recorded_at, note, leave_out=WORDS_FROM_THE_MESSAGE), encoding="utf-8"
    )
    saved = [Path(COMPARISON_DIR.name) / "holdout_answers.json"]

    texts = []
    for run in runs:
        texts.append(render_holdout(Holdout(run=run, reports=held_reports, expected=held_expected)))
        saved.append(_save(COMPARISON_DIR, f"holdout_benchmark_{run.model}.txt", texts[-1]))
    gap = f"‏تاريخ المقارنة: {recorded_at}\n"
    gap += render_comparison(runs[0], runs[1], held_reports, held_expected, holdout=True)
    gap += f"\n‏التكلفة التقريبية لهذا التشغيل كله (النموذجان معاً): {spent:.4f} دولار\n"
    texts.append(gap)
    saved.append(_save(COMPARISON_DIR, "holdout_comparison.txt", gap))
    return texts, saved


def main(argv=None) -> None:
    # Windows terminals often cannot print Arabic; never crash because of that.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Rasd accuracy benchmark")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--repeat", type=int, default=1, metavar="N", help="run N times and show what changed between the runs")
    choice.add_argument(
        "--compare-holdout",
        metavar="MODEL",
        help=f"compare {DEFAULT_MODEL} with this larger model on the holdout reports only (runs once)",
    )
    choice.add_argument(
        "--compare", metavar="MODEL", help="the first comparison, on the main reports (already run once)"
    )
    args = parser.parse_args(argv)
    larger = args.compare or args.compare_holdout
    models = [DEFAULT_MODEL, larger] if larger else [DEFAULT_MODEL]

    # Everything that can be checked for free is checked before the first paid call.
    try:
        if args.repeat < 1:
            raise ValueError("--repeat needs a number of runs: 1 or more.")
        if larger == DEFAULT_MODEL:
            raise ValueError(f"A comparison needs a model other than the everyday one ({DEFAULT_MODEL}).")
        if args.compare and comparison_was_recorded():
            raise RuntimeError(
                "The comparison on the main reports was already run; its results are in the comparison folder. "
                "Project rule: it runs once only. For the holdout reports use --compare-holdout."
            )
        if args.compare_holdout and holdout_comparison_was_recorded():
            raise RuntimeError(
                "The comparison on the holdout reports was already run; its results are in the comparison folder. "
                "The owner approved it once only."
            )
        for model in models:
            cost_usd(model, 0, 0)
        holdout_set = load_holdout()
        if args.compare_holdout and holdout_set is None:
            raise RuntimeError(
                "There are no holdout reports yet in data/holdout. "
                "The owner approved this comparison only after the holdout files exist."
            )
        reports, expected = load_reports(), load_expected()
        client = make_client().with_options(max_retries=RETRIES)
        for model in models:
            check_access(client, model)
    except (RuntimeError, ValueError) as problem:
        sys.exit(f"Benchmark not run. {problem}")

    if args.compare_holdout:
        texts, saved = holdout_comparison(client, larger, holdout_set)
    elif args.compare:
        texts, saved = first_comparison(client, larger, reports, expected, holdout_set)
    else:
        texts, saved = everyday_run(client, reports, expected, holdout_set, args.repeat)

    print()
    print("\n\n".join(texts))
    for path in saved:
        print(f"‏حُفظ في الملف: {path.as_posix()}")


if __name__ == "__main__":
    main()
