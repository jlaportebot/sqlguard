"""Command-line interface for SQLGuard.

Usage:
    sqlguard lint <file.sql> [--strict] [--json]
    sqlguard diff <old_schema.py> <new_schema.py> [--json]
    sqlguard migrate <old_schema.py> <new_schema.py> [--dialect postgresql] [--direction up|down]
    sqlguard validate <file.sql> --schema <schema.py> [--json]
    sqlguard render <schema.py> [--dialect postgresql] [--table TABLE]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from sqlguard.dialects import get_dialect
from sqlguard.diff import SchemaDiffer
from sqlguard.linter import Severity, SQLLinter
from sqlguard.migration import MigrationGenerator
from sqlguard.schema import Schema
from sqlguard.validator import QueryValidator


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the SQLGuard CLI."""
    parser = argparse.ArgumentParser(
        prog="sqlguard",
        description="🛡️ SQLGuard — Schema validation, migration generation, and query safety for Python SQL projects",
    )
    parser.add_argument("--version", action="version", version="sqlguard 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # lint subcommand
    lint_parser = subparsers.add_parser("lint", help="Lint SQL files for unsafe patterns")
    lint_parser.add_argument("file", help="SQL file to lint")
    lint_parser.add_argument(
        "--strict", action="store_true", help="Enable strict mode (more rules)"
    )
    lint_parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON"
    )

    # diff subcommand
    diff_parser = subparsers.add_parser("diff", help="Diff two schema files")
    diff_parser.add_argument("old_schema", help="Path to old schema Python file")
    diff_parser.add_argument("new_schema", help="Path to new schema Python file")
    diff_parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON"
    )

    # migrate subcommand
    migrate_parser = subparsers.add_parser(
        "migrate", help="Generate migration SQL from schema diff"
    )
    migrate_parser.add_argument("old_schema", help="Path to old schema Python file")
    migrate_parser.add_argument("new_schema", help="Path to new schema Python file")
    migrate_parser.add_argument(
        "--dialect",
        default="postgresql",
        choices=["postgresql", "mysql", "sqlite", "oracle"],
        help="SQL dialect",
    )
    migrate_parser.add_argument(
        "--direction", default="up", choices=["up", "down"], help="Migration direction"
    )

    # validate subcommand
    validate_parser = subparsers.add_parser("validate", help="Validate SQL against a schema")
    validate_parser.add_argument("file", help="SQL file to validate")
    validate_parser.add_argument(
        "--schema", required=True, dest="schema_file", help="Path to schema Python file"
    )
    validate_parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON"
    )

    # render subcommand
    render_parser = subparsers.add_parser("render", help="Render schema as DDL SQL")
    render_parser.add_argument("schema_file", help="Path to schema Python file")
    render_parser.add_argument(
        "--dialect",
        default="postgresql",
        choices=["postgresql", "mysql", "sqlite", "oracle"],
        help="SQL dialect",
    )
    render_parser.add_argument("--table", help="Only render a specific table")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "lint":
            return _cmd_lint(args)
        elif args.command == "diff":
            return _cmd_diff(args)
        elif args.command == "migrate":
            return _cmd_migrate(args)
        elif args.command == "validate":
            return _cmd_validate(args)
        elif args.command == "render":
            return _cmd_render(args)
        else:
            parser.print_help()
            return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _load_schema_from_file(path: str) -> Schema:
    """Load a Schema object from a Python file.

    The Python file should define a module-level variable `schema` of type Schema.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")

    module_name = file_path.stem
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "schema"):
        raise ValueError(f"Schema file '{path}' must define a module-level 'schema' variable")

    schema_obj = module.schema
    if not isinstance(schema_obj, Schema):
        raise ValueError(
            f"'schema' variable in '{path}' must be a Schema instance, got {type(schema_obj).__name__}"
        )

    return schema_obj


def _cmd_lint(args: argparse.Namespace) -> int:
    """Execute the lint command."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    linter = SQLLinter(strict=args.strict)
    issues = linter.lint_file(args.file)

    if args.json_output:
        output = [issue.to_dict() for issue in issues]
        print(json.dumps(output, indent=2))
    else:
        if not issues:
            print(f"✅ {args.file}: No issues found")
            return 0

        print(f"🔍 Linting {args.file}: {len(issues)} issue(s) found\n")
        for issue in issues:
            print(f"  {issue}")

        # Summary
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warn_count = sum(1 for i in issues if i.severity == Severity.WARNING)
        info_count = sum(1 for i in issues if i.severity in (Severity.INFO, Severity.STYLE))
        print(
            f"\n  Summary: {error_count} error(s), {warn_count} warning(s), {info_count} info/style"
        )

    return 1 if issues else 0


def _cmd_diff(args: argparse.Namespace) -> int:
    """Execute the diff command."""
    old_schema = _load_schema_from_file(args.old_schema)
    new_schema = _load_schema_from_file(args.new_schema)

    differ = SchemaDiffer()
    diff = differ.diff(old_schema, new_schema)

    if args.json_output:
        print(json.dumps(diff.to_dict(), indent=2))
    else:
        print(diff.summary())

    return 1 if diff.has_breaking_changes else 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    """Execute the migrate command."""
    old_schema = _load_schema_from_file(args.old_schema)
    new_schema = _load_schema_from_file(args.new_schema)

    differ = SchemaDiffer()
    diff = differ.diff(old_schema, new_schema)

    generator = MigrationGenerator(dialect=args.dialect)
    migration = generator.generate(diff, old_schema=old_schema, new_schema=new_schema)

    if args.direction == "up":
        print(migration.up_sql)
    else:
        print(migration.down_sql)

    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """Execute the validate command."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    schema = _load_schema_from_file(args.schema_file)

    sql = file_path.read_text()
    validator = QueryValidator(schema)
    errors = validator.validate(sql)

    if args.json_output:
        output = [e.to_dict() for e in errors]
        print(json.dumps(output, indent=2))
    else:
        if not errors:
            print(f"✅ {args.file}: No validation errors")
            return 0

        print(
            f"🔍 Validating {args.file} against schema '{schema.name}': {len(errors)} error(s) found\n"
        )
        for error in errors:
            print(f"  {error}")

    return 1 if errors else 0


def _cmd_render(args: argparse.Namespace) -> int:
    """Execute the render command."""
    schema = _load_schema_from_file(args.schema_file)
    dialect = get_dialect(args.dialect)

    tables = schema.tables
    if args.table:
        table = schema.get_table(args.table)
        if table is None:
            print(f"Error: Table '{args.table}' not found in schema", file=sys.stderr)
            return 1
        tables = [table]

    for table in tables:
        print(dialect.render_create_table(table.name, table.columns))
        print()

        # Render table-level foreign keys
        for fk in table.foreign_keys:
            print(dialect.render_foreign_key(fk, table.name))

        # Render indexes
        for idx in table.indexes:
            print(dialect.render_index(idx))

        # Render check constraints
        for chk in table.checks:
            print(dialect.render_check(chk))

        # Render unique constraints
        for uc in table.unique_constraints:
            print(dialect.render_unique_constraint(uc))

    return 0


if __name__ == "__main__":
    sys.exit(main())
