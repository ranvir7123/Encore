"""Task 12: `encore` CLI entry point (pyproject.toml: encore = "encore.cli:main").

Five subcommands, argparse-based:
  encore eval       --seeds 100,101,102 --customers 500   -> runs the matrix, writes runs/eval.json
  encore report                                            -> reads runs/eval.json, writes runs/scoreboard.html
  encore parse-eval                                        -> keyword vs haiku vs sonnet accuracy on data/reply_eval.jsonl
  encore demo       --n 3 --timeout 300 --dry-run          -> Task 11's Razorpay demo slice
  encore web                                               -> writes web/data/*.json + web/py/*.py
"""
import argparse
import functools
import glob
import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

from encore.audit import AuditLog
from encore.demo import run_demo_slice
from encore.evaluate import run_matrix
from encore.parser import evaluate as parser_evaluate
from encore.parser import parse_keyword, parse_llm
from encore.report import write_scoreboard
from encore.webdata import build_cliff, build_results
from encore.webhtml import render_page


def cmd_eval(args: argparse.Namespace) -> None:
    seeds = [int(s) for s in args.seeds.split(",")]
    out_dir = Path(args.out_dir)
    results = run_matrix(seeds=seeds, out_dir=out_dir, n_customers=args.customers)
    print(f"Ran {len(results)} regime/policy cells over seeds {seeds}, "
          f"{args.customers} customers each.")
    print(f"Wrote {out_dir / 'eval.json'}")


def cmd_report(args: argparse.Namespace) -> None:
    out_path = write_scoreboard(
        eval_path=Path(args.eval_path), out_path=Path(args.out_path),
        audit_dir=Path(args.audit_dir),
    )
    print(f"Wrote {out_path}")


def cmd_parse_eval(args: argparse.Namespace) -> None:
    load_dotenv()  # picks up ANTHROPIC_API_KEY from .env if present, same as demo.py does for Razorpay
    eval_path = Path(args.eval_path)
    keyword_result = parser_evaluate(parse_keyword, eval_path)
    print(f"keyword       : accuracy_kind={keyword_result['accuracy_kind']:.3f} "
          f"accuracy_full={keyword_result['accuracy_full']:.3f} (n={keyword_result['n']})")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set -- skipping claude-haiku-4-5 and "
              "claude-sonnet-5 scoring, printing keyword-only accuracy above.")
        return

    for model in ("claude-haiku-4-5", "claude-sonnet-5"):
        result = parser_evaluate(functools.partial(parse_llm, model=model), eval_path)
        print(f"{model:14s}: accuracy_kind={result['accuracy_kind']:.3f} "
              f"accuracy_full={result['accuracy_full']:.3f} (n={result['n']})")


# The modules Pyodide fetches and imports at runtime (Tier A). Every one of
# them imports only the standard library plus its siblings here -- that is what
# makes the browser tier possible at all, so the list is deliberately explicit
# rather than a glob over src/encore: adding model.py to it would silently drag
# scikit-learn into the page and break the deploy at load time, not at build.
TIER_A_MODULES = ["__init__", "domain", "wall", "audit", "simulator", "policies", "scheduler"]

# The cliff chart is about the held-out distribution shift specifically.
CLIFF_REGIME = "r1_shifted"
CLIFF_POLICIES = ["encore_learned", "random_in_horizon"]


def _read_executions(audit_dir: Path, regime: str, policy: str) -> list[dict]:
    """All execution records for one regime/policy, across every seed's audit
    log. Returns [] when nothing matches, so a partial runs/ directory produces
    an empty chart with a visible provenance line rather than a crash."""
    records: list[dict] = []
    pattern = str(audit_dir / f"{regime}__{policy}__s*_audit.jsonl")
    for path in sorted(glob.glob(pattern)):
        records.extend(AuditLog(Path(path)).read_all())
    return records


def cmd_web(args: argparse.Namespace) -> None:
    eval_path = Path(args.eval_path)
    if not eval_path.exists():
        raise SystemExit(
            f"{eval_path} not found -- run `encore eval --seeds {args.seeds} "
            f"--customers {args.customers}` first. runs/ is gitignored scratch, so a "
            "fresh clone or worktree has none of it."
        )
    seeds = [int(s) for s in args.seeds.split(",")]
    eval_dict = json.loads(eval_path.read_text(encoding="utf-8"))

    out_dir = Path(args.out_dir)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    results = build_results(eval_dict, seeds=seeds, customers=args.customers)
    (data_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    audit_dir = Path(args.audit_dir)
    executions = {p: _read_executions(audit_dir, CLIFF_REGIME, p) for p in CLIFF_POLICIES}
    cliff = build_cliff(executions, regime=CLIFF_REGIME, seeds=seeds, customers=args.customers)
    (data_dir / "cliff.json").write_text(
        json.dumps(cliff, indent=2, ensure_ascii=False), encoding="utf-8")

    # index.html is RENDERED from a hand-written template rather than hand-written
    # itself. Tier B has to be complete before any JavaScript runs (spec section 3),
    # which means the cliff chart's ~120 numbers live in the markup -- and hand-
    # transcribing them is exactly the failure the spec calls a transcription bug.
    # The template holds all the prose and structure; only measured values are
    # substituted, and an unfilled marker raises rather than shipping "{{CELLS}}".
    template_path = Path(args.template)
    if template_path.exists():
        page = render_page(
            template_path.read_text(encoding="utf-8"),
            results, cliff, test_count=args.test_count,
        )
        (out_dir / "index.html").write_text(page, encoding="utf-8")
        print(f"Wrote {out_dir / 'index.html'} from {template_path}")

    # Copy the live modules next to the page so the deploy is self-contained:
    # the site fetches these over HTTP and writes them into the Pyodide FS, so
    # publishing web/ without them would 404 the whole Tier A panel.
    py_dir = out_dir / "py"
    py_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path(args.src_dir)
    for module in TIER_A_MODULES:
        shutil.copyfile(src_dir / f"{module}.py", py_dir / f"{module}.py")

    print(f"Wrote {data_dir / 'results.json'} ({results['totals']['cells']} cells, "
          f"{results['totals']['compliance_violations']} violations)")
    for policy in CLIFF_POLICIES:
        series = cliff["series"][policy]
        print(f"Wrote cliff series {policy}: {series['total_tried']} retries, "
              f"{series['total_won']} recovered")
    print(f"Copied {len(TIER_A_MODULES)} live modules to {py_dir}")


def cmd_demo(args: argparse.Namespace) -> None:
    if not args.dry_run:
        load_dotenv()  # RazorpayClient reads RAZORPAY_KEY_ID/SECRET from the environment
    run_demo_slice(n=args.n, timeout_s=args.timeout_s, interval_s=args.interval_s,
                   dry_run=args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="encore", description="Encore CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("eval", help="run the regime x policy eval matrix, write runs/eval.json")
    p_eval.add_argument("--seeds", default="100,101,102",
                        help="comma-separated eval seeds (default: 100,101,102)")
    p_eval.add_argument("--customers", type=int, default=500,
                        help="customers per seed (default: 500)")
    p_eval.add_argument("--out-dir", default="runs", help="output directory (default: runs)")
    p_eval.set_defaults(func=cmd_eval)

    p_report = sub.add_parser("report", help="read runs/eval.json, write runs/scoreboard.html")
    p_report.add_argument("--eval-path", default="runs/eval.json")
    p_report.add_argument("--out-path", default="runs/scoreboard.html")
    p_report.add_argument("--audit-dir", default="runs")
    p_report.set_defaults(func=cmd_report)

    p_parse_eval = sub.add_parser(
        "parse-eval", help="score keyword vs claude-haiku-4-5 vs claude-sonnet-5 on data/reply_eval.jsonl")
    p_parse_eval.add_argument("--eval-path", default="data/reply_eval.jsonl")
    p_parse_eval.set_defaults(func=cmd_parse_eval)

    p_demo = sub.add_parser("demo", help="Task 11 Razorpay demo slice")
    p_demo.add_argument("--n", type=int, default=3, help="number of soft-decline failures (default: 3)")
    p_demo.add_argument("--timeout", type=int, default=300, dest="timeout_s",
                        help="poll_until_terminal timeout in seconds (default: 300)")
    p_demo.add_argument("--interval", type=int, default=5, dest="interval_s",
                        help="poll interval in seconds (default: 5)")
    p_demo.add_argument("--dry-run", action="store_true",
                        help="exercise the full code path against SimulatedRail -- no network")
    p_demo.set_defaults(func=cmd_demo)

    p_web = sub.add_parser("web", help="build web/data/*.json and web/py/*.py from runs/")
    p_web.add_argument("--eval-path", default="runs/eval.json")
    p_web.add_argument("--audit-dir", default="runs")
    p_web.add_argument("--out-dir", default="web")
    p_web.add_argument("--src-dir", default="src/encore")
    p_web.add_argument("--seeds", default="100,101,102",
                       help="seeds the eval was run with, for the provenance line")
    p_web.add_argument("--customers", type=int, default=500,
                       help="customers per seed the eval was run with, for the provenance line")
    p_web.add_argument("--template", default="web/index.template.html",
                       help="hand-written page template; measured values are substituted in")
    p_web.add_argument("--test-count", type=int, default=147,
                       help="suite size quoted in the hero (keep in step with `uv run pytest -q`)")
    p_web.set_defaults(func=cmd_web)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
