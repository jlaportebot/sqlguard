"""Tests for sqlguard.cli module."""

import json
import os
import tempfile

import pytest
from sqlguard.cli import main
from sqlguard.schema import Schema, Table, Column


class TestCLI:
    """Tests for CLI commands."""

    def _write_schema_file(self, tmpdir: str, schema: Schema) -> str:
        """Write a schema to a Python file that can be loaded by the CLI."""
        path = os.path.join(tmpdir, f"{schema.name}_schema.py")
        # Generate a Python file that creates the schema
        lines = [
            "from sqlguard.schema import Schema, Table, Column",
            "",
            "schema = Schema(",
            f'    "{schema.name}",',
            "    [",
        ]
        for table in schema.tables:
            lines.append("        Table(")
            lines.append(f'            "{table.name}",')
            lines.append("            [")
            for col in table.columns:
                lines.append("                Column(")
                lines.append(f'                    "{col.name}",')
                lines.append(f'                    "{col.base_type.value}",')
                lines.append(f"                    nullable={col.nullable},")
                lines.append(f"                    primary_key={col.primary_key},")
                lines.append(f"                    unique={col.unique},")
                if col.default is not None:
                    lines.append(f'                    default="{col.default}",')
                if col.references is not None:
                    lines.append(f'                    references="{col.references}",')
                lines.append("                ),")
            lines.append("            ],")
            lines.append("        ),")
        lines.append("    ],")
        lines.append(")")
        content = "\n".join(lines)
        with open(path, "w") as f:
            f.write(content)
        return path

    def _write_sql_file(self, tmpdir: str, sql: str, name: str = "query.sql") -> str:
        path = os.path.join(tmpdir, name)
        with open(path, "w") as f:
            f.write(sql)
        return path

    def test_lint_clean_file(self, tmp_path):
        sql = "SELECT id, name FROM users WHERE active = true;\n"
        sql_path = self._write_sql_file(str(tmp_path), sql)
        result = main(["lint", sql_path])
        assert result == 0

    def test_lint_select_star(self, tmp_path):
        sql = "SELECT * FROM users;\n"
        sql_path = self._write_sql_file(str(tmp_path), sql)
        result = main(["lint", sql_path])
        assert result == 1  # Errors found

    def test_lint_json_output(self, tmp_path):
        sql = "SELECT * FROM users;\n"
        sql_path = self._write_sql_file(str(tmp_path), sql)
        # Capture stdout by running main
        result = main(["lint", sql_path, "--json"])
        # The result should be 1 (error found), and JSON was output

    def test_diff_no_changes(self, tmp_path):
        schema = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        path = self._write_schema_file(str(tmp_path), schema)
        result = main(["diff", path, path])
        assert result == 0  # No breaking changes

    def test_diff_with_changes(self, tmp_path):
        old_schema = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        new_schema = Schema("v2", [Table("users", [
            Column("id", "integer", primary_key=True),
            Column("name", "varchar", nullable=False),  # NOT NULL without default — breaking
        ])])
        old_path = self._write_schema_file(str(tmp_path), old_schema)
        new_path = self._write_schema_file(str(tmp_path), new_schema)
        result = main(["diff", old_path, new_path])
        assert result == 1  # Breaking changes

    def test_diff_json_output(self, tmp_path):
        old_schema = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        new_schema = Schema("v2", [Table("users", [Column("id", "integer", primary_key=True), Column("name", "varchar")])])
        old_path = self._write_schema_file(str(tmp_path), old_schema)
        new_path = self._write_schema_file(str(tmp_path), new_schema)
        result = main(["diff", old_path, new_path, "--json"])
        assert result == 0

    def test_migrate(self, tmp_path):
        old_schema = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        new_schema = Schema("v2", [Table("users", [Column("id", "integer", primary_key=True), Column("name", "varchar")])])
        old_path = self._write_schema_file(str(tmp_path), old_schema)
        new_path = self._write_schema_file(str(tmp_path), new_schema)
        result = main(["migrate", old_path, new_path, "--dialect", "postgresql"])
        assert result == 0

    def test_migrate_down(self, tmp_path):
        old_schema = Schema("v1", [Table("users", [Column("id", "integer", primary_key=True)])])
        new_schema = Schema("v2", [Table("users", [Column("id", "integer", primary_key=True), Column("name", "varchar")])])
        old_path = self._write_schema_file(str(tmp_path), old_schema)
        new_path = self._write_schema_file(str(tmp_path), new_schema)
        result = main(["migrate", old_path, new_path, "--direction", "down"])
        assert result == 0

    def test_validate_clean(self, tmp_path):
        schema = Schema("my_app", [Table("users", [Column("id", "integer", primary_key=True), Column("name", "varchar")])])
        schema_path = self._write_schema_file(str(tmp_path), schema)
        sql_path = self._write_sql_file(str(tmp_path), "SELECT id, name FROM users;")
        result = main(["validate", sql_path, "--schema", schema_path])
        assert result == 0

    def test_render(self, tmp_path):
        schema = Schema("my_app", [Table("users", [Column("id", "integer", primary_key=True), Column("name", "varchar", nullable=False)])])
        schema_path = self._write_schema_file(str(tmp_path), schema)
        result = main(["render", schema_path, "--dialect", "postgresql"])
        assert result == 0

    def test_render_specific_table(self, tmp_path):
        schema = Schema("my_app", [
            Table("users", [Column("id", "integer", primary_key=True)]),
            Table("posts", [Column("id", "integer", primary_key=True)]),
        ])
        schema_path = self._write_schema_file(str(tmp_path), schema)
        result = main(["render", schema_path, "--table", "users"])
        assert result == 0

    def test_render_nonexistent_table(self, tmp_path):
        schema = Schema("my_app", [Table("users", [Column("id", "integer", primary_key=True)])])
        schema_path = self._write_schema_file(str(tmp_path), schema)
        result = main(["render", schema_path, "--table", "nonexistent"])
        assert result == 1

    def test_no_command(self):
        result = main([])
        assert result == 0

    def test_nonexistent_file(self, tmp_path):
        result = main(["lint", "/nonexistent/file.sql"])
        assert result == 1

    def test_validate_nonexistent_schema(self, tmp_path):
        sql_path = self._write_sql_file(str(tmp_path), "SELECT 1;")
        result = main(["validate", sql_path, "--schema", "/nonexistent/schema.py"])
        assert result == 1
