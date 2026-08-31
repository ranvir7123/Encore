"""Task 12: `encore` CLI entry point (pyproject.toml: encore = "encore.cli:main").

Four subcommands, argparse-based:
  encore eval       --seeds 100,101,102 --customers 500   -> runs the matrix, writes runs/eval.json
  encore report                                            -> reads runs/eval.json, writes runs/scoreboard.html
  encore parse-eval                                        -> keyword vs haiku vs sonnet accuracy on data/reply_eval.jsonl
  encore demo       --n 3 --timeout 300 --dry-run          -> Task 11's Razorpay demo slice
"""
import argparse
import functools
import os
from pathlib import Path

from dotenv import load_dotenv

from encore.demo import run_demo_slice
from encore.evaluate import run_matrix
from encore.parser import evaluate as parser_evaluate
from encore.parser import parse_keyword, parse_llm
from encore.report import write_scoreboard


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


def cmd_demo(args: argparse.Namespace) -> None:
    if not args.dry_run:
        load_dotenv()  # RazorpayClient reads RAZORPAY_KEY_ID/SECRET from the environment
    run_demo_slice(n=args.n, timeout_s=args.timeout_s, dry_run=args.dry_run)


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
    p_demo.add_argument("--dry-run", action="store_true",
                        help="exercise the full code path against SimulatedRail -- no network")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
