"""Schema definitions for SQLGuard.

Provides Python classes to define database schemas: Schema, Table, Column,
ForeignKey, Index, CheckConstraint, and UniqueConstraint.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ColumnType(Enum):
    """Supported SQL column types across dialects."""

    # Integer types
    SMALLINT = "smallint"
    INTEGER = "integer"
    BIGINT = "bigint"
    SERIAL = "serial"
    BIGSERIAL = "bigserial"

    # Numeric types
    DECIMAL = "decimal"
    NUMERIC = "numeric"
    REAL = "real"
    DOUBLE_PRECISION = "double_precision"

    # String types
    CHAR = "char"
    VARCHAR = "varchar"
    TEXT = "text"

    # Binary
    BYTEA = "bytea"
    BLOB = "blob"

    # Date/Time
    DATE = "date"
    TIME = "time"
    TIMESTAMP = "timestamp"
    TIMESTAMPTZ = "timestamptz"
    INTERVAL = "interval"

    # Boolean
    BOOLEAN = "boolean"

    # JSON
    JSON = "json"
    JSONB = "jsonb"

    # UUID
    UUID = "uuid"

    # Network
    INET = "inet"
    CIDR = "cidr"
    MACADDR = "macaddr"

    # Array (PostgreSQL)
    ARRAY = "array"

    # Custom/fallback
    CUSTOM = "custom"

    @classmethod
    def from_string(cls, type_str: str) -> ColumnType:
        """Parse a string into a ColumnType enum value."""
        normalized = type_str.strip().lower().replace(" ", "_")
        # Handle common aliases
        aliases = {
            "int": cls.INTEGER,
            "int2": cls.SMALLINT,
            "int4": cls.INTEGER,
            "int8": cls.BIGINT,
            "float": cls.REAL,
            "float4": cls.REAL,
            "float8": cls.DOUBLE_PRECISION,
            "double": cls.DOUBLE_PRECISION,
            "numeric": cls.NUMERIC,
            "number": cls.NUMERIC,
            "string": cls.VARCHAR,
            "str": cls.VARCHAR,
            "bool": cls.BOOLEAN,
            "datetime": cls.TIMESTAMP,
            "timestamp_with_timezone": cls.TIMESTAMPTZ,
            "timestamp_tz": cls.TIMESTAMPTZ,
            "binary": cls.BYTEA,
            "varbinary": cls.BLOB,
            "tinyint": cls.SMALLINT,
            "mediumint": cls.INTEGER,
            "longtext": cls.TEXT,
            "mediumtext": cls.TEXT,
            "tinytext": cls.TEXT,
            "char": cls.CHAR,
            "nchar": cls.CHAR,
            "nvarchar": cls.VARCHAR,
            "clob": cls.TEXT,
            "money": cls.DECIMAL,
            "smallserial": cls.SERIAL,
        }
        if normalized in aliases:
            return aliases[normalized]

        # Handle type strings with parameters like varchar(255), decimal(10,2)
        base_type = normalized.split("(")[0].split("[")[0]
        for member in cls:
            if member.value == base_type:
                return member

        # Fallback to custom
        return cls.CUSTOM


@dataclass
class Column:
    """Represents a database column with full type and constraint information."""

    name: str
    type: str | ColumnType
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False
    unique: bool = False
    references: str | None = None  # "table.column" format
    check: str | None = None
    type_params: str | None = None  # e.g., "255" for varchar(255)
    comment: str | None = None
    auto_increment: bool = False
    on_update: str | None = None  # MySQL ON UPDATE

    def __post_init__(self) -> None:
        if isinstance(self.type, str):
            self.type = ColumnType.from_string(self.type)

    @property
    def base_type(self) -> ColumnType:
        """Return the ColumnType enum value."""
        return self.type if isinstance(self.type, ColumnType) else ColumnType.from_string(self.type)

    @property
    def type_string(self) -> str:
        """Return the SQL type string, including parameters."""
        base = self.base_type.value
        if self.type_params:
            return f"{base}({self.type_params})"
        # Add default params for types that commonly need them
        if self.base_type == ColumnType.VARCHAR and not self.type_params:
            return f"{base}(255)"
        if self.base_type == ColumnType.DECIMAL and not self.type_params:
            return f"{base}(10,2)"
        return base

    @property
    def reference_table(self) -> str | None:
        """Extract the table name from a foreign key reference."""
        if not self.references:
            return None
        return self.references.split(".")[0]

    @property
    def reference_column(self) -> str | None:
        """Extract the column name from a foreign key reference."""
        if not self.references:
            return None
        parts = self.references.split(".")
        return parts[1] if len(parts) > 1 else "id"

    def is_breaking_change_from(self, old: Column) -> tuple[bool, str]:
        """Check if changing from `old` to this column is a breaking change.

        Returns (is_breaking, description).
        """
        changes: list[str] = []
        breaking = False

        # Type change
        if self.base_type != old.base_type:
            # Some type changes are safe (widening)
            safe_widenings = {
                (ColumnType.SMALLINT, ColumnType.INTEGER),
                (ColumnType.SMALLINT, ColumnType.BIGINT),
                (ColumnType.INTEGER, ColumnType.BIGINT),
                (ColumnType.REAL, ColumnType.DOUBLE_PRECISION),
                (ColumnType.CHAR, ColumnType.VARCHAR),
                (ColumnType.CHAR, ColumnType.TEXT),
                (ColumnType.VARCHAR, ColumnType.TEXT),
                (ColumnType.JSON, ColumnType.JSONB),
                (ColumnType.TIMESTAMP, ColumnType.TIMESTAMPTZ),
            }
            if (old.base_type, self.base_type) in safe_widenings:
                changes.append(f"type widened from {old.base_type.value} to {self.base_type.value}")
            else:
                breaking = True
                changes.append(f"type changed from {old.base_type.value} to {self.base_type.value}")

        # Nullable -> NOT NULL (breaking)
        if old.nullable and not self.nullable:
            breaking = True
            changes.append("changed from nullable to NOT NULL (may fail on existing NULL rows)")

        # NOT NULL -> nullable (safe)
        if not old.nullable and self.nullable:
            changes.append("changed from NOT NULL to nullable")

        # Default added or changed
        if self.default != old.default:
            if old.default is None and self.default is not None:
                changes.append(f"default added: {self.default}")
            elif old.default is not None and self.default is None:
                breaking = True
                changes.append("default removed")
            else:
                changes.append(f"default changed from {old.default} to {self.default}")

        # Primary key change
        if self.primary_key != old.primary_key:
            breaking = True
            changes.append("primary key constraint changed")

        # Unique constraint change
        if self.unique and not old.unique:
            breaking = True
            changes.append("UNIQUE constraint added (may fail on duplicate rows)")
        if not self.unique and old.unique:
            changes.append("UNIQUE constraint removed")

        # Foreign key change
        if self.references != old.references:
            if old.references is None and self.references is not None:
                changes.append(f"foreign key added: {self.references}")
            elif old.references is not None and self.references is None:
                breaking = True
                changes.append("foreign key removed")
            else:
                changes.append(f"foreign key changed from {old.references} to {self.references}")

        description = "; ".join(changes) if changes else "no changes"
        return breaking, description

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Column):
            return NotImplemented
        return (
            self.name == other.name
            and self.base_type == other.base_type
            and self.nullable == other.nullable
            and self.default == other.default
            and self.primary_key == other.primary_key
            and self.unique == other.unique
            and self.references == other.references
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.name,
                self.base_type,
                self.nullable,
                self.default,
                self.primary_key,
                self.unique,
                self.references,
            )
        )


@dataclass
class ForeignKey:
    """Represents a table-level foreign key constraint."""

    name: str
    columns: list[str]
    reference_table: str
    reference_columns: list[str]
    on_delete: str = "NO ACTION"
    on_update: str = "NO ACTION"
    deferrable: bool = False
    initially_deferred: bool = False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ForeignKey):
            return NotImplemented
        return (
            self.columns == other.columns
            and self.reference_table == other.reference_table
            and self.reference_columns == other.reference_columns
        )

    def __hash__(self) -> int:
        return hash((tuple(self.columns), self.reference_table, tuple(self.reference_columns)))


@dataclass
class Index:
    """Represents a database index."""

    name: str
    table: str
    columns: list[str]
    unique: bool = False
    method: str | None = None  # btree, hash, gin, gist, etc.

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Index):
            return NotImplemented
        return (
            self.table == other.table
            and self.columns == other.columns
            and self.unique == other.unique
        )

    def __hash__(self) -> int:
        return hash((self.table, tuple(self.columns), self.unique))


@dataclass
class CheckConstraint:
    """Represents a CHECK constraint."""

    name: str
    table: str
    expression: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CheckConstraint):
            return NotImplemented
        return self.expression == other.expression and self.table == other.table

    def __hash__(self) -> int:
        return hash((self.table, self.expression))


@dataclass
class UniqueConstraint:
    """Represents a table-level UNIQUE constraint (composite)."""

    name: str
    table: str
    columns: list[str]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UniqueConstraint):
            return NotImplemented
        return self.table == other.table and self.columns == other.columns

    def __hash__(self) -> int:
        return hash((self.table, tuple(self.columns)))


@dataclass
class Table:
    """Represents a database table with columns, constraints, and indexes."""

    name: str
    columns: list[Column] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    checks: list[CheckConstraint] = field(default_factory=list)
    unique_constraints: list[UniqueConstraint] = field(default_factory=list)
    comment: str | None = None

    def get_column(self, name: str) -> Column | None:
        """Get a column by name (case-insensitive)."""
        name_lower = name.lower()
        for col in self.columns:
            if col.name.lower() == name_lower:
                return col
        return None

    @property
    def primary_key_columns(self) -> list[Column]:
        """Return all columns that are part of the primary key."""
        return [col for col in self.columns if col.primary_key]

    @property
    def column_names(self) -> list[str]:
        """Return a list of column names."""
        return [col.name for col in self.columns]

    def add_column(self, column: Column) -> None:
        """Add a column to the table."""
        if self.get_column(column.name) is not None:
            raise ValueError(f"Column '{column.name}' already exists in table '{self.name}'")
        self.columns.append(column)

    def remove_column(self, name: str) -> Column:
        """Remove a column by name and return it."""
        col = self.get_column(name)
        if col is None:
            raise ValueError(f"Column '{name}' not found in table '{self.name}'")
        self.columns.remove(col)
        return col

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Table):
            return NotImplemented
        return self.name.lower() == other.name.lower()

    def __hash__(self) -> int:
        return hash(self.name.lower())


@dataclass
class Schema:
    """Represents a complete database schema with tables and metadata."""

    name: str
    tables: list[Table] = field(default_factory=list)
    version: str | None = None
    description: str | None = None

    def get_table(self, name: str) -> Table | None:
        """Get a table by name (case-insensitive)."""
        name_lower = name.lower()
        for table in self.tables:
            if table.name.lower() == name_lower:
                return table
        return None

    @property
    def table_names(self) -> list[str]:
        """Return a list of table names."""
        return [t.name for t in self.tables]

    def add_table(self, table: Table) -> None:
        """Add a table to the schema."""
        if self.get_table(table.name) is not None:
            raise ValueError(f"Table '{table.name}' already exists in schema '{self.name}'")
        self.tables.append(table)

    def remove_table(self, name: str) -> Table:
        """Remove a table by name and return it."""
        table = self.get_table(name)
        if table is None:
            raise ValueError(f"Table '{name}' not found in schema '{self.name}'")
        self.tables.remove(table)
        return table

    def all_columns(self) -> dict[str, dict[str, Column]]:
        """Return a nested dict: {table_name: {column_name: Column}}."""
        result: dict[str, dict[str, Column]] = {}
        for table in self.tables:
            result[table.name] = {col.name: col for col in table.columns}
        return result

    def all_foreign_keys(self) -> list[ForeignKey]:
        """Return all foreign keys across all tables."""
        fks: list[ForeignKey] = []
        for table in self.tables:
            fks.extend(table.foreign_keys)
            # Also include column-level foreign keys
            for col in table.columns:
                if col.references and col.reference_table:
                    fk = ForeignKey(
                        name=f"fk_{table.name}_{col.name}",
                        columns=[col.name],
                        reference_table=col.reference_table,
                        reference_columns=[col.reference_column or "id"],
                    )
                    fks.append(fk)
        return fks

    def all_indexes(self) -> list[Index]:
        """Return all indexes across all tables."""
        result: list[Index] = []
        for table in self.tables:
            result.extend(table.indexes)
        return result

    def copy(self) -> Schema:
        """Return a deep copy of this schema."""
        return copy.deepcopy(self)

    def validate(self) -> list[str]:
        """Validate schema consistency and return a list of issues."""
        issues: list[str] = []
        table_names_lower = {t.name.lower() for t in self.tables}

        for table in self.tables:
            # Check for duplicate column names
            col_names: set[str] = set()
            for col in table.columns:
                col_lower = col.name.lower()
                if col_lower in col_names:
                    issues.append(f"Table '{table.name}': duplicate column '{col.name}'")
                col_names.add(col_lower)

            # Check foreign key references exist
            for col in table.columns:
                if col.references and col.reference_table:
                    if col.reference_table.lower() not in table_names_lower:
                        issues.append(
                            f"Table '{table.name}', column '{col.name}': "
                            f"references non-existent table '{col.reference_table}'"
                        )
                    else:
                        ref_table = self.get_table(col.reference_table)
                        if (
                            ref_table
                            and col.reference_column
                            and ref_table.get_column(col.reference_column) is None
                        ):
                            issues.append(
                                f"Table '{table.name}', column '{col.name}': "
                                f"references non-existent column '{col.reference_column}' "
                                f"in table '{col.reference_table}'"
                            )

            # Check table-level foreign keys
            for fk in table.foreign_keys:
                if fk.reference_table.lower() not in table_names_lower:
                    issues.append(
                        f"Table '{table.name}', FK '{fk.name}': "
                        f"references non-existent table '{fk.reference_table}'"
                    )

            # Check indexes reference valid columns
            for idx in table.indexes:
                for col_name in idx.columns:
                    if table.get_column(col_name) is None:
                        issues.append(
                            f"Table '{table.name}', index '{idx.name}': "
                            f"references non-existent column '{col_name}'"
                        )

            # Check unique constraints reference valid columns
            for uc in table.unique_constraints:
                for col_name in uc.columns:
                    if table.get_column(col_name) is None:
                        issues.append(
                            f"Table '{table.name}', unique constraint '{uc.name}': "
                            f"references non-existent column '{col_name}'"
                        )

            # Check at least one primary key
            if not table.primary_key_columns and table.columns:
                issues.append(f"Table '{table.name}': no primary key defined")

        return issues

    def to_dict(self) -> dict[str, Any]:
        """Serialize schema to a dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tables": [
                {
                    "name": t.name,
                    "columns": [
                        {
                            "name": c.name,
                            "type": c.base_type.value,
                            "type_params": c.type_params,
                            "nullable": c.nullable,
                            "default": c.default,
                            "primary_key": c.primary_key,
                            "unique": c.unique,
                            "references": c.references,
                            "check": c.check,
                            "auto_increment": c.auto_increment,
                        }
                        for c in t.columns
                    ],
                    "foreign_keys": [
                        {
                            "name": fk.name,
                            "columns": fk.columns,
                            "reference_table": fk.reference_table,
                            "reference_columns": fk.reference_columns,
                            "on_delete": fk.on_delete,
                            "on_update": fk.on_update,
                        }
                        for fk in t.foreign_keys
                    ],
                    "indexes": [
                        {
                            "name": idx.name,
                            "columns": idx.columns,
                            "unique": idx.unique,
                            "method": idx.method,
                        }
                        for idx in t.indexes
                    ],
                    "checks": [
                        {"name": chk.name, "expression": chk.expression} for chk in t.checks
                    ],
                    "unique_constraints": [
                        {"name": uc.name, "columns": uc.columns} for uc in t.unique_constraints
                    ],
                }
                for t in self.tables
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Schema:
        """Deserialize a schema from a dictionary."""
        tables: list[Table] = []
        for t_data in data.get("tables", []):
            columns: list[Column] = []
            for c_data in t_data.get("columns", []):
                columns.append(
                    Column(
                        name=c_data["name"],
                        type=c_data["type"],
                        type_params=c_data.get("type_params"),
                        nullable=c_data.get("nullable", True),
                        default=c_data.get("default"),
                        primary_key=c_data.get("primary_key", False),
                        unique=c_data.get("unique", False),
                        references=c_data.get("references"),
                        check=c_data.get("check"),
                        auto_increment=c_data.get("auto_increment", False),
                    )
                )

            foreign_keys: list[ForeignKey] = []
            for fk_data in t_data.get("foreign_keys", []):
                foreign_keys.append(
                    ForeignKey(
                        name=fk_data["name"],
                        columns=fk_data["columns"],
                        reference_table=fk_data["reference_table"],
                        reference_columns=fk_data["reference_columns"],
                        on_delete=fk_data.get("on_delete", "NO ACTION"),
                        on_update=fk_data.get("on_update", "NO ACTION"),
                    )
                )

            indexes: list[Index] = []
            for idx_data in t_data.get("indexes", []):
                indexes.append(
                    Index(
                        name=idx_data["name"],
                        table=t_data["name"],
                        columns=idx_data["columns"],
                        unique=idx_data.get("unique", False),
                        method=idx_data.get("method"),
                    )
                )

            checks: list[CheckConstraint] = []
            for chk_data in t_data.get("checks", []):
                checks.append(
                    CheckConstraint(
                        name=chk_data["name"],
                        table=t_data["name"],
                        expression=chk_data["expression"],
                    )
                )

            unique_constraints: list[UniqueConstraint] = []
            for uc_data in t_data.get("unique_constraints", []):
                unique_constraints.append(
                    UniqueConstraint(
                        name=uc_data["name"],
                        table=t_data["name"],
                        columns=uc_data["columns"],
                    )
                )

            tables.append(
                Table(
                    name=t_data["name"],
                    columns=columns,
                    foreign_keys=foreign_keys,
                    indexes=indexes,
                    checks=checks,
                    unique_constraints=unique_constraints,
                )
            )

        return cls(
            name=data["name"],
            tables=tables,
            version=data.get("version"),
            description=data.get("description"),
        )
