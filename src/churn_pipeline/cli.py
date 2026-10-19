"""Command-line interface for customer churn data generation, ETL, and reporting."""

import argparse
import json
from pathlib import Path
from .generate import generate_data
from .load import run_pipeline
from .transform import load_and_validate, build_curated_data, generate_data_quality_report


def main():
    parser = argparse.ArgumentParser(description="Customer Churn & Retention Analytics Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # 1. Generate command
    gen = sub.add_parser("generate", help="Generate synthetic customer churn CSV datasets")
    gen.add_argument("--output-dir", default="data/raw", help="Directory to save raw CSV files")
    gen.add_argument("--customers", type=int, default=1000, help="Number of customer records")
    gen.add_argument("--seed", type=int, default=77, help="Random seed for reproducibility")

    # 2. Run ETL command
    run = sub.add_parser("run", help="Validate, transform, curate, and load into PostgreSQL")
    run.add_argument("--input-dir", default="data/raw", help="Directory with raw CSV files")
    run.add_argument("--curated-dir", default="data/curated", help="Directory for curated data and reports")
    run.add_argument("--validate-only", action="store_true", help="Run validation and curation without database loading")

    # 3. Report command
    report_cmd = sub.add_parser("report", help="Display verified data quality and churn KPI audit report")
    report_cmd.add_argument("--curated-dir", default="data/curated", help="Directory where reports are located")

    args = parser.parse_args()

    if args.command == "generate":
        result = generate_data(args.output_dir, seed=args.seed, customer_count=args.customers)
        print(json.dumps({k: str(v) for k, v in result.items()}, indent=2))

    elif args.command == "run":
        if args.validate_only:
            frames = load_and_validate(args.input_dir)
            curated_df = build_curated_data(frames)
            Path(args.curated_dir).mkdir(parents=True, exist_ok=True)
            curated_df.to_csv(Path(args.curated_dir) / "curated_customer_retention.csv", index=False)
            rep = generate_data_quality_report(frames, curated_df, output_dir=args.curated_dir)
            print("Validation and curation successful. Data Quality Report:")
            print(json.dumps(rep, indent=2))
        else:
            print("Pipeline completed. Rows loaded:")
            print(json.dumps(run_pipeline(args.input_dir, curated_dir=args.curated_dir), indent=2))

    elif args.command == "report":
        report_file = Path(args.curated_dir) / "data_quality_report.json"
        if not report_file.exists():
            print(f"Error: Report file not found at {report_file}. Run 'run' command first.")
            return
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
