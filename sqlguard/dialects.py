"""Dialect-specific SQL rendering for SQLGuard.

Provides base Dialect class and PostgreSQL, MySQL, SQLite implementations
that know how to render column types, constraints, and DDL statements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlguard.schema import CheckConstraint, Column, ColumnType, ForeignKey, Index, UniqueConstraint


class Dialect(ABC):
    """Abstract base class for SQL dialect rendering."""

    name: str = "generic"

    @abstractmethod
    def render_column_type(self, column: Column) -> str:
        """Render the SQL type string for a column."""
        ...

    @abstractmethod
    def render_column_constraints(self, column: Column) -> str:
        """Render the inline constraints for a column (NOT NULL, DEFAULT, etc.)."""
        ...

    @abstractmethod
    def render_column_definition(self, column: Column) -> str:
        """Render a full column definition (type + constraints)."""
        ...

    @abstractmethod
    def render_foreign_key(self, fk: ForeignKey, table_name: str) -> str:
        """Render a foreign key constraint as ALTER TABLE."""
        ...

    @abstractmethod
    def render_index(self, index: Index) -> str:
        """Render a CREATE INDEX statement."""
        ...

    @abstractmethod
    def render_check(self, check: CheckConstraint) -> str:
        """Render a CHECK constraint as ALTER TABLE."""
        ...

    @abstractmethod
    def render_unique_constraint(self, uc: UniqueConstraint) -> str:
        """Render a UNIQUE constraint as ALTER TABLE."""
        ...

    def render_add_column(self, table_name: str, column: Column) -> str:
        """Render ALTER TABLE ADD COLUMN."""
        col_def = self.render_column_definition(column)
        return f"ALTER TABLE {table_name} ADD COLUMN {col_def};"

    def render_drop_column(self, table_name: str, column_name: str) -> str:
        """Render ALTER TABLE DROP COLUMN."""
        return f"ALTER TABLE {table_name} DROP COLUMN {column_name};"

    def render_alter_column_type(self, table_name: str, column: Column) -> str:
        """Render ALTER TABLE ALTER COLUMN TYPE."""
        type_str = self.render_column_type(column)
        return f"ALTER TABLE {table_name} ALTER COLUMN {column.name} TYPE {type_str};"

    def render_alter_column_nullability(
        self, table_name: str, column_name: str, nullable: bool
    ) -> str:
        """Render ALTER TABLE to change nullability."""
        if nullable:
            return f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP NOT NULL;"
        else:
            return f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET NOT NULL;"

    def render_alter_column_default(
        self, table_name: str, column_name: str, default: str | None
    ) -> str:
        """Render ALTER TABLE to set or drop a default."""
        if default is not None:
            return f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET DEFAULT {default};"
        else:
            return f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP DEFAULT;"

    def render_drop_table(self, table_name: str) -> str:
        """Render DROP TABLE."""
        return f"DROP TABLE {table_name};"

    def render_create_table(self, table_name: str, columns: list[Column]) -> str:
        """Render CREATE TABLE."""
        col_defs = []
        for col in columns:
            col_defs.append(f"  {self.render_column_definition(col)}")

        # Add table-level constraints
        pks = [c for c in columns if c.primary_key]
        if len(pks) > 1:
            pk_names = ", ".join(c.name for c in pks)
            col_defs.append(f"  PRIMARY KEY ({pk_names})")

        body = ",\n".join(col_defs)
        return f"CREATE TABLE {table_name} (\n{body}\n);"

    def render_drop_foreign_key(self, fk_name: str, table_name: str) -> str:
        """Render ALTER TABLE DROP CONSTRAINT for a foreign key."""
        return f"ALTER TABLE {table_name} DROP CONSTRAINT {fk_name};"

    def render_drop_index(self, index_name: str) -> str:
        """Render DROP INDEX."""
        return f"DROP INDEX {index_name};"

    def render_drop_check(self, check_name: str, table_name: str) -> str:
        """Render ALTER TABLE DROP CONSTRAINT for a check."""
        return f"ALTER TABLE {table_name} DROP CONSTRAINT {check_name};"

    def render_drop_unique_constraint(self, constraint_name: str, table_name: str) -> str:
        """Render ALTER TABLE DROP CONSTRAINT for a unique constraint."""
        return f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name};"


class PostgresqlDialect(Dialect):
    """PostgreSQL-specific SQL rendering."""

    name = "postgresql"

    TYPE_MAP: dict[ColumnType, str] = {
        ColumnType.SMALLINT: "SMALLINT",
        ColumnType.INTEGER: "INTEGER",
        ColumnType.BIGINT: "BIGINT",
        ColumnType.SERIAL: "SERIAL",
        ColumnType.BIGSERIAL: "BIGSERIAL",
        ColumnType.DECIMAL: "DECIMAL",
        ColumnType.NUMERIC: "NUMERIC",
        ColumnType.REAL: "REAL",
        ColumnType.DOUBLE_PRECISION: "DOUBLE PRECISION",
        ColumnType.CHAR: "CHAR",
        ColumnType.VARCHAR: "VARCHAR",
        ColumnType.TEXT: "TEXT",
        ColumnType.BYTEA: "BYTEA",
        ColumnType.BLOB: "BYTEA",
        ColumnType.DATE: "DATE",
        ColumnType.TIME: "TIME",
        ColumnType.TIMESTAMP: "TIMESTAMP",
        ColumnType.TIMESTAMPTZ: "TIMESTAMPTZ",
        ColumnType.INTERVAL: "INTERVAL",
        ColumnType.BOOLEAN: "BOOLEAN",
        ColumnType.JSON: "JSON",
        ColumnType.JSONB: "JSONB",
        ColumnType.UUID: "UUID",
        ColumnType.INET: "INET",
        ColumnType.CIDR: "CIDR",
        ColumnType.MACADDR: "MACADDR",
        ColumnType.ARRAY: "ARRAY",
        ColumnType.CUSTOM: "TEXT",
    }

    def render_column_type(self, column: Column) -> str:
        base = self.TYPE_MAP.get(column.base_type, "TEXT")
        if column.type_params:
            return f"{base}({column.type_params})"
        if column.base_type == ColumnType.VARCHAR and not column.type_params:
            return "VARCHAR(255)"
        if column.base_type == ColumnType.DECIMAL and not column.type_params:
            return "DECIMAL(10,2)"
        if column.base_type == ColumnType.ARRAY and column.type_params:
            return f"{column.type_params}[]"
        return base

    def render_column_constraints(self, column: Column) -> str:
        parts: list[str] = []
        if not column.nullable:
            parts.append("NOT NULL")
        if column.default is not None:
            parts.append(f"DEFAULT {column.default}")
        if column.unique and not column.primary_key:
            parts.append("UNIQUE")
        if column.references and column.reference_table:
            ref = f"{column.reference_table}({column.reference_column or 'id'})"
            parts.append(f"REFERENCES {ref}")
        return " ".join(parts)

    def render_column_definition(self, column: Column) -> str:
        type_str = self.render_column_type(column)
        constraints = self.render_column_constraints(column)
        parts: list[str] = [column.name, type_str]
        if column.primary_key:
            if column.auto_increment or column.base_type in (
                ColumnType.SERIAL,
                ColumnType.BIGSERIAL,
            ):
                parts.append("PRIMARY KEY")
            else:
                parts.append("PRIMARY KEY")
        if constraints:
            parts.append(constraints)
        return " ".join(parts)

    def render_foreign_key(self, fk: ForeignKey, table_name: str) -> str:
        cols = ", ".join(fk.columns)
        ref_cols = ", ".join(fk.reference_columns)
        sql = f"ALTER TABLE {table_name} ADD CONSTRAINT {fk.name} FOREIGN KEY ({cols}) REFERENCES {fk.reference_table}({ref_cols})"
        if fk.on_delete != "NO ACTION":
            sql += f" ON DELETE {fk.on_delete}"
        if fk.on_update != "NO ACTION":
            sql += f" ON UPDATE {fk.on_update}"
        if fk.deferrable:
            sql += " DEFERRABLE"
            if fk.initially_deferred:
                sql += " INITIALLY DEFERRED"
        return sql + ";"

    def render_index(self, index: Index) -> str:
        unique = "UNIQUE " if index.unique else ""
        method = f" USING {index.method}" if index.method else ""
        cols = ", ".join(index.columns)
        return f"CREATE {unique}INDEX {index.name} ON {index.table}{method} ({cols});"

    def render_check(self, check: CheckConstraint) -> str:
        return f"ALTER TABLE {check.table} ADD CONSTRAINT {check.name} CHECK ({check.expression});"

    def render_unique_constraint(self, uc: UniqueConstraint) -> str:
        cols = ", ".join(uc.columns)
        return f"ALTER TABLE {uc.table} ADD CONSTRAINT {uc.name} UNIQUE ({cols});"

    def render_alter_column_type(self, table_name: str, column: Column) -> str:
        type_str = self.render_column_type(column)
        return f"ALTER TABLE {table_name} ALTER COLUMN {column.name} TYPE {type_str} USING {column.name}::{type_str};"

    def render_drop_foreign_key(self, fk_name: str, table_name: str) -> str:
        return f"ALTER TABLE {table_name} DROP CONSTRAINT {fk_name};"


class MysqlDialect(Dialect):
    """MySQL-specific SQL rendering."""

    name = "mysql"

    TYPE_MAP: dict[ColumnType, str] = {
        ColumnType.SMALLINT: "SMALLINT",
        ColumnType.INTEGER: "INT",
        ColumnType.BIGINT: "BIGINT",
        ColumnType.SERIAL: "INT AUTO_INCREMENT",
        ColumnType.BIGSERIAL: "BIGINT AUTO_INCREMENT",
        ColumnType.DECIMAL: "DECIMAL",
        ColumnType.NUMERIC: "DECIMAL",
        ColumnType.REAL: "FLOAT",
        ColumnType.DOUBLE_PRECISION: "DOUBLE",
        ColumnType.CHAR: "CHAR",
        ColumnType.VARCHAR: "VARCHAR",
        ColumnType.TEXT: "TEXT",
        ColumnType.BYTEA: "BLOB",
        ColumnType.BLOB: "BLOB",
        ColumnType.DATE: "DATE",
        ColumnType.TIME: "TIME",
        ColumnType.TIMESTAMP: "TIMESTAMP",
        ColumnType.TIMESTAMPTZ: "TIMESTAMP",
        ColumnType.INTERVAL: "TEXT",  # MySQL has no INTERVAL type
        ColumnType.BOOLEAN: "BOOLEAN",
        ColumnType.JSON: "JSON",
        ColumnType.JSONB: "JSON",
        ColumnType.UUID: "CHAR(36)",
        ColumnType.INET: "VARCHAR(45)",
        ColumnType.CIDR: "VARCHAR(45)",
        ColumnType.MACADDR: "VARCHAR(17)",
        ColumnType.ARRAY: "JSON",
        ColumnType.CUSTOM: "TEXT",
    }

    def render_column_type(self, column: Column) -> str:
        base = self.TYPE_MAP.get(column.base_type, "TEXT")
        if column.type_params:
            return f"{base}({column.type_params})"
        if column.base_type == ColumnType.VARCHAR and not column.type_params:
            return "VARCHAR(255)"
        if column.base_type == ColumnType.DECIMAL and not column.type_params:
            return "DECIMAL(10,2)"
        return base

    def render_column_constraints(self, column: Column) -> str:
        parts: list[str] = []
        if not column.nullable:
            parts.append("NOT NULL")
        if column.auto_increment:
            parts.append("AUTO_INCREMENT")
        if column.default is not None:
            parts.append(f"DEFAULT {column.default}")
        if column.on_update is not None:
            parts.append(f"ON UPDATE {column.on_update}")
        if column.unique and not column.primary_key:
            parts.append("UNIQUE")
        if column.references and column.reference_table:
            ref = f"{column.reference_table}({column.reference_column or 'id'})"
            parts.append(f"REFERENCES {ref}")
        return " ".join(parts)

    def render_column_definition(self, column: Column) -> str:
        type_str = self.render_column_type(column)
        constraints = self.render_column_constraints(column)
        parts: list[str] = [column.name, type_str]
        if column.primary_key:
            parts.append("PRIMARY KEY")
        if constraints:
            parts.append(constraints)
        return " ".join(parts)

    def render_foreign_key(self, fk: ForeignKey, table_name: str) -> str:
        cols = ", ".join(fk.columns)
        ref_cols = ", ".join(fk.reference_columns)
        sql = f"ALTER TABLE {table_name} ADD CONSTRAINT {fk.name} FOREIGN KEY ({cols}) REFERENCES {fk.reference_table}({ref_cols})"
        if fk.on_delete != "NO ACTION":
            sql += f" ON DELETE {fk.on_delete}"
        if fk.on_update != "NO ACTION":
            sql += f" ON UPDATE {fk.on_update}"
        return sql + ";"

    def render_index(self, index: Index) -> str:
        unique = "UNIQUE " if index.unique else ""
        method = f" USING {index.method}" if index.method else ""
        cols = ", ".join(index.columns)
        return f"CREATE {unique}INDEX {index.name} ON {index.table}{method} ({cols});"

    def render_check(self, check: CheckConstraint) -> str:
        return f"ALTER TABLE {check.table} ADD CONSTRAINT {check.name} CHECK ({check.expression});"

    def render_unique_constraint(self, uc: UniqueConstraint) -> str:
        cols = ", ".join(uc.columns)
        return f"ALTER TABLE {uc.table} ADD CONSTRAINT {uc.name} UNIQUE ({cols});"

    def render_alter_column_type(self, table_name: str, column: Column) -> str:
        type_str = self.render_column_type(column)
        constraints = self.render_column_constraints(column)
        parts = [f"ALTER TABLE {table_name} MODIFY COLUMN {column.name} {type_str}"]
        if constraints:
            parts.append(constraints)
        return " ".join(parts) + ";"

    def render_drop_foreign_key(self, fk_name: str, table_name: str) -> str:
        return f"ALTER TABLE {table_name} DROP FOREIGN KEY {fk_name};"

    def render_drop_index(self, index_name: str) -> str:
        return f"DROP INDEX {index_name} ON TABLE;"

    def render_drop_check(self, check_name: str, table_name: str) -> str:
        return f"ALTER TABLE {table_name} DROP CHECK {check_name};"


class SqliteDialect(Dialect):
    """SQLite-specific SQL rendering."""

    name = "sqlite"

    TYPE_MAP: dict[ColumnType, str] = {
        ColumnType.SMALLINT: "INTEGER",
        ColumnType.INTEGER: "INTEGER",
        ColumnType.BIGINT: "INTEGER",
        ColumnType.SERIAL: "INTEGER",
        ColumnType.BIGSERIAL: "INTEGER",
        ColumnType.DECIMAL: "REAL",
        ColumnType.NUMERIC: "REAL",
        ColumnType.REAL: "REAL",
        ColumnType.DOUBLE_PRECISION: "REAL",
        ColumnType.CHAR: "TEXT",
        ColumnType.VARCHAR: "TEXT",
        ColumnType.TEXT: "TEXT",
        ColumnType.BYTEA: "BLOB",
        ColumnType.BLOB: "BLOB",
        ColumnType.DATE: "TEXT",
        ColumnType.TIME: "TEXT",
        ColumnType.TIMESTAMP: "TEXT",
        ColumnType.TIMESTAMPTZ: "TEXT",
        ColumnType.INTERVAL: "TEXT",
        ColumnType.BOOLEAN: "INTEGER",
        ColumnType.JSON: "TEXT",
        ColumnType.JSONB: "TEXT",
        ColumnType.UUID: "TEXT",
        ColumnType.INET: "TEXT",
        ColumnType.CIDR: "TEXT",
        ColumnType.MACADDR: "TEXT",
        ColumnType.ARRAY: "TEXT",
        ColumnType.CUSTOM: "TEXT",
    }

    def render_column_type(self, column: Column) -> str:
        return self.TYPE_MAP.get(column.base_type, "TEXT")

    def render_column_constraints(self, column: Column) -> str:
        parts: list[str] = []
        if column.primary_key and column.auto_increment:
            parts.append("PRIMARY KEY AUTOINCREMENT")
        elif column.primary_key:
            parts.append("PRIMARY KEY")
        if not column.nullable and not column.primary_key:
            parts.append("NOT NULL")
        if column.default is not None:
            parts.append(f"DEFAULT {column.default}")
        if column.unique and not column.primary_key:
            parts.append("UNIQUE")
        if column.references and column.reference_table:
            ref = f"{column.reference_table}({column.reference_column or 'id'})"
            parts.append(f"REFERENCES {ref}")
        return " ".join(parts)

    def render_column_definition(self, column: Column) -> str:
        type_str = self.render_column_type(column)
        constraints = self.render_column_constraints(column)
        parts: list[str] = [column.name, type_str]
        if constraints:
            parts.append(constraints)
        return " ".join(parts)

    def render_foreign_key(self, fk: ForeignKey, table_name: str) -> str:
        # SQLite doesn't support ALTER TABLE ADD CONSTRAINT
        # Must recreate the table; return a comment explaining this
        cols = ", ".join(fk.columns)
        ref_cols = ", ".join(fk.reference_columns)
        return (
            f"-- SQLite: Cannot add foreign key via ALTER TABLE. "
            f"Recreate table with: FOREIGN KEY ({cols}) REFERENCES {fk.reference_table}({ref_cols})"
        )

    def render_index(self, index: Index) -> str:
        unique = "UNIQUE " if index.unique else ""
        cols = ", ".join(index.columns)
        return f"CREATE {unique}INDEX {index.name} ON {index.table} ({cols});"

    def render_check(self, check: CheckConstraint) -> str:
        return (
            f"-- SQLite: Cannot add CHECK constraint via ALTER TABLE. "
            f"Recreate table with: CHECK ({check.expression})"
        )

    def render_unique_constraint(self, uc: UniqueConstraint) -> str:
        cols = ", ".join(uc.columns)
        return (
            f"-- SQLite: Cannot add UNIQUE constraint via ALTER TABLE. "
            f"Recreate table with: UNIQUE ({cols})"
        )

    def render_add_column(self, table_name: str, column: Column) -> str:
        col_def = self.render_column_definition(column)
        return f"ALTER TABLE {table_name} ADD COLUMN {col_def};"

    def render_drop_column(self, table_name: str, column_name: str) -> str:
        # SQLite 3.35.0+ supports DROP COLUMN
        return f"ALTER TABLE {table_name} DROP COLUMN {column_name};"

    def render_alter_column_type(self, table_name: str, column: Column) -> str:
        # SQLite doesn't support ALTER COLUMN TYPE directly
        type_str = self.render_column_type(column)
        return (
            f"-- SQLite: Cannot alter column type directly. "
            f"Recreate table with {column.name} {type_str}."
        )

    def render_alter_column_nullability(
        self, table_name: str, column_name: str, nullable: bool
    ) -> str:
        action = "DROP NOT NULL" if nullable else "SET NOT NULL"
        return (
            f"-- SQLite: Cannot {action} via ALTER TABLE. "
            f"Recreate table to change nullability of {column_name}."
        )


def get_dialect(name: str) -> Dialect:
    """Get a dialect instance by name."""
    dialects = {
        "postgresql": PostgresqlDialect,
        "postgres": PostgresqlDialect,
        "pg": PostgresqlDialect,
        "mysql": MysqlDialect,
        "mariadb": MysqlDialect,
        "sqlite": SqliteDialect,
    }
    normalized = name.strip().lower()
    if normalized not in dialects:
        raise ValueError(
            f"Unknown dialect '{name}'. Supported: {', '.join(sorted(set(dialects.keys())))}"
        )
    return dialects[normalized]()
