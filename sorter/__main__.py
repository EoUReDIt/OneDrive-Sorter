"""Command line: python -m sorter check|run|undo ..."""
import argparse
import sys

from . import engine
from .manifest import ManifestError, load_manifest


def _show(items):
    for it in items:
        mark = {"ready": "OK  ", "already there": "OK  ", "not selected": "HOLD"}.get(it.state, "FAIL")
        print(f"[{mark}] #{it.row.n:<3} {it.row.source}  ->  {it.row.dest_folder}   ({it.state}: {it.detail})")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sorter", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "run"):
        s = sub.add_parser(name)
        s.add_argument("manifest")
        s.add_argument("--root", required=True, help="folder to sort (for example your OneDrive folder)")
        s.add_argument("--include-flagged", action="store_true", help="also move rows that fail the rules")
        if name == "run":
            s.add_argument("--apply", action="store_true", help="really move (default is a dry run)")
            s.add_argument("--delay", type=float, default=0.25, help="seconds between moves")
            s.add_argument("--log-dir", help="where to write the undo log (default ~/.onedrive-sorter/logs)")
    sv = sub.add_parser("serve", help="start the local backend and print the address to open in your browser")
    sv.add_argument("--root", required=True)
    sv.add_argument("--port", type=int, default=8765, help="0 picks a free port")
    sv.add_argument("--log-dir")
    u = sub.add_parser("undo")
    u.add_argument("log")
    u.add_argument("--root", required=True)
    u.add_argument("--delay", type=float, default=0.25)
    a = p.parse_args(argv)

    try:
        if a.cmd == "serve":
            from .server import serve
            serve(a.root, a.port, a.log_dir)
            return 0
        if a.cmd == "undo":
            rep = engine.undo(a.log, a.root, delay=a.delay)
            for it in rep.failed:
                print(f"[FAIL] {it.src} -> {it.dst}: {it.detail}")
            print(f"Undone {len(rep.moved)}; failed {len(rep.failed)}.")
            return 1 if rep.failed else 0
        rows = load_manifest(a.manifest)
        if a.include_flagged:
            for r in rows:
                r.selected = True
        items = engine.check(rows, a.root)
        _show(items)
        ready = [i for i in items if i.state == engine.READY]
        if a.cmd == "check" or not a.apply:
            print(f"\n{len(ready)} of {len(rows)} row(s) ready. " + ("" if a.cmd == "check" else "Dry run: add --apply to move."))
            return 0
        rep = engine.execute(ready, a.root, log_dir=a.log_dir, delay=a.delay,
                             on_event=lambda ev, it: print(f"{ev.upper()}: {it.row.source}" + (f" ({it.detail})" if ev == 'failed' else "")))
        print(f"\nDone. Moved {len(rep.moved)}; failed {len(rep.failed)}. Undo log: {rep.log_path}")
        return 1 if rep.failed else 0
    except (ManifestError, engine.EngineError, OSError) as e:
        print("Error:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
