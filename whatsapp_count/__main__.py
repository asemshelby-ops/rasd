"""The command.

    python -m whatsapp_count PATH                  print the counts
    python -m whatsapp_count PATH --hand-check     write 50 random messages to mark by hand
    python -m whatsapp_count PATH --score FILE     print how often the rules agree with the marks

PATH is a WhatsApp export (.txt, or the .zip an iPhone makes) kept OUTSIDE this
repository. The command refuses a file inside it.
"""

import argparse
import sys
from pathlib import Path

from whatsapp_count.counting import count, render
from whatsapp_count.export import parse_export, read_export
from whatsapp_count.handcheck import render_agreement, score, write_sample

REPOSITORY = Path(__file__).resolve().parent.parent


def inside_repository(path: Path) -> bool:
    resolved = Path(path).resolve()
    return resolved == REPOSITORY or REPOSITORY in resolved.parents


def _fail(message: str) -> int:
    print(f"Stopped: {message}", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m whatsapp_count", description="Count a WhatsApp group export, locally.")
    parser.add_argument("export", help="the exported chat (.txt or .zip), kept outside this repository")
    parser.add_argument("--hotels", help="a text file with your hotel names, one per line (also outside the repository)")
    parser.add_argument("--month-first", action="store_true", help="dates are month/day/year")
    parser.add_argument("--window-hours", type=int, default=24, help="how long after a report a closing reply still counts")
    parser.add_argument("--hand-check", action="store_true", help="write random messages to a file for marking by hand")
    parser.add_argument("--sample", type=int, default=50, help="how many messages the hand check takes")
    parser.add_argument("--seed", type=int, default=None, help="pick the same random messages again")
    parser.add_argument("--score", help="the marked hand-check file: print how often the rules agree")
    options = parser.parse_args(argv)

    export = Path(options.export)
    for path in [export, options.hotels, options.score]:
        if path and inside_repository(Path(path)):
            return _fail(f"'{path}' is inside the repository. Keep WhatsApp exports and files made from them outside it.")
    if not export.is_file():
        return _fail(f"there is no file at '{export}'.")
    try:
        parsed = parse_export(read_export(export), month_first=True if options.month_first else None)
    except (OSError, ValueError) as e:
        return _fail(f"the file could not be read ({type(e).__name__}).")
    if parsed.unread_lines > len(parsed.messages):
        return _fail(
            f"the dates of {parsed.unread_lines} lines could not be read. "
            "Run it again " + ("without" if options.month_first else "with") + " --month-first."
        )
    if parsed.unread_lines:
        print(f"Warning: {parsed.unread_lines} lines were left out because their dates could not be read.", file=sys.stderr)
    if not parsed.messages:
        return _fail("no WhatsApp messages were found in this file. Export the chat 'without media' and pass the .txt file.")

    if options.score:
        try:
            result = score(parsed.messages, Path(options.score))
        except (OSError, ValueError) as e:
            return _fail(str(e) if isinstance(e, ValueError) else "the hand-check file could not be read.")
        print(render_agreement(result))
        return 0

    if options.hand_check:
        target = export.with_name(export.stem + ".rasd_hand_check.csv")
        written = write_sample(parsed.messages, target, size=options.sample, seed=options.seed)
        print(f"Wrote {written} messages to: {target}")
        print("Open it in Excel, write y or n in the 'report' column for each message, save it as CSV, then run:")
        print(f'  python -m whatsapp_count "{export}" --score "{target}"')
        print("The file holds message text. Keep it on this laptop and delete it when you are done.")
        return 0

    hotels = []
    if options.hotels:
        try:
            hotels = [line.strip() for line in Path(options.hotels).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        except OSError:
            return _fail("the hotels file could not be read.")
    text = render(count(parsed.messages, hotels=hotels, window_hours=options.window_hours), parsed.notes)
    saved = export.with_name(export.stem + ".rasd_counts.txt")
    saved.write_text(text + "\n", encoding="utf-8")  # saved first: a Windows terminal may fail to show Arabic
    try:
        print(text)
    except UnicodeEncodeError:
        print(f"This terminal cannot show Arabic. The counts are saved in: {saved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
