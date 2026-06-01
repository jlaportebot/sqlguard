"""SQLGuard — Schema validation, migration generation, and query safety for Python SQL projects."""

from sqlguard.schema import Schema, Table, Column, ForeignKey, Index, CheckConstraint, UniqueConstraint
from sqlguard.diff import SchemaDiff, SchemaDiffer, ChangeType, Change
from sqlguard.migration import MigrationGenerator, Migration, MigrationStep
from sqlguard.linter import SQLLinter, LintIssue, LintRule, Severity
from sqlguard.validator import QueryValidator, ValidationError
from sqlguard.dialects import Dialect, PostgresqlDialect, MysqlDialect, SqliteDialect

__version__ = "0.1.0"
__all__ = [
    "Schema",
    "Table",
    "Column",
    "ForeignKey",
    "Index",
    "CheckConstraint",
    "UniqueConstraint",
    "SchemaDiff",
    "SchemaDiffer",
    "ChangeType",
    "Change",
    "MigrationGenerator",
    "Migration",
    "MigrationStep",
    "SQLLinter",
    "LintIssue",
    "LintRule",
    "Severity",
    "QueryValidator",
    "ValidationError",
    "Dialect",
    "PostgresqlDialect",
    "MysqlDialect",
    "SqliteDialect",
]
