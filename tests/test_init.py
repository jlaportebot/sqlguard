"""Tests for sqlguard.__init__ module."""

import sqlguard


class TestImports:
    """Test that all public API imports work correctly."""

    def test_schema_imports(self):
        assert sqlguard.Schema is not None
        assert sqlguard.Table is not None
        assert sqlguard.Column is not None
        assert sqlguard.ForeignKey is not None
        assert sqlguard.Index is not None
        assert sqlguard.CheckConstraint is not None
        assert sqlguard.UniqueConstraint is not None

    def test_diff_imports(self):
        assert sqlguard.SchemaDiff is not None
        assert sqlguard.SchemaDiffer is not None
        assert sqlguard.ChangeType is not None
        assert sqlguard.Change is not None

    def test_migration_imports(self):
        assert sqlguard.MigrationGenerator is not None
        assert sqlguard.Migration is not None
        assert sqlguard.MigrationStep is not None

    def test_linter_imports(self):
        assert sqlguard.SQLLinter is not None
        assert sqlguard.LintIssue is not None
        assert sqlguard.LintRule is not None
        assert sqlguard.Severity is not None

    def test_validator_imports(self):
        assert sqlguard.QueryValidator is not None
        assert sqlguard.ValidationError is not None

    def test_dialect_imports(self):
        assert sqlguard.Dialect is not None
        assert sqlguard.PostgresqlDialect is not None
        assert sqlguard.MysqlDialect is not None
        assert sqlguard.SqliteDialect is not None

    def test_version(self):
        assert sqlguard.__version__ == "0.1.0"
