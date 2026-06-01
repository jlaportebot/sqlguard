"""Schema diffing engine for SQLGuard.

Compares two Schema objects and produces a SchemaDiff containing all changes,
categorized as breaking or safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sqlguard.schema import Schema, Table, Column, ForeignKey, Index, CheckConstraint, UniqueConstraint


class ChangeType(Enum):
    """Categories of schema changes."""

    # Table-level changes
    TABLE_ADDED = "table_added"
    TABLE_REMOVED = "table_removed"
    TABLE_RENAMED = "table_renamed"

    # Column-level changes
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_TYPE_CHANGED = "column_type_changed"
    COLUMN_NULLABILITY_CHANGED = "column_nullability_changed"
    COLUMN_DEFAULT_CHANGED = "column_default_changed"
    COLUMN_PRIMARY_KEY_CHANGED = "column_primary_key_changed"
    COLUMN_UNIQUE_CHANGED = "column_unique_changed"
    COLUMN_FOREIGN_KEY_CHANGED = "column_foreign_key_changed"
    COLUMN_AUTO_INCREMENT_CHANGED = "column_auto_increment_changed"

    # Constraint changes
    FOREIGN_KEY_ADDED = "foreign_key_added"
    FOREIGN_KEY_REMOVED = "foreign_key_removed"
    FOREIGN_KEY_CHANGED = "foreign_key_changed"

    # Index changes
    INDEX_ADDED = "index_added"
    INDEX_REMOVED = "index_removed"
    INDEX_CHANGED = "index_changed"

    # Check constraint changes
    CHECK_ADDED = "check_added"
    CHECK_REMOVED = "check_removed"

    # Unique constraint changes
    UNIQUE_CONSTRAINT_ADDED = "unique_constraint_added"
    UNIQUE_CONSTRAINT_REMOVED = "unique_constraint_removed"


@dataclass
class Change:
    """A single schema change with metadata."""

    change_type: ChangeType
    table: str
    column: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    breaking: bool = False
    description: str = ""

    def __str__(self) -> str:
        prefix = "⚠️  BREAKING" if self.breaking else "✅ SAFE"
        location = f"{self.table}.{self.column}" if self.column else self.table
        return f"{prefix}: [{self.change_type.value}] {location} — {self.description}"

    @property
    def is_breaking(self) -> bool:
        return self.breaking


@dataclass
class SchemaDiff:
    """Result of comparing two schemas."""

    old_schema: str  # Schema name
    new_schema: str  # Schema name
    changes: list[Change] = field(default_factory=list)

    @property
    def breaking_changes(self) -> list[Change]:
        """Return only breaking changes."""
        return [c for c in self.changes if c.breaking]

    @property
    def safe_changes(self) -> list[Change]:
        """Return only safe (non-breaking) changes."""
        return [c for c in self.changes if not c.breaking]

    @property
    def has_breaking_changes(self) -> bool:
        """Whether any breaking changes exist."""
        return any(c.breaking for c in self.changes)

    @property
    def tables_added(self) -> list[Change]:
        return [c for c in self.changes if c.change_type == ChangeType.TABLE_ADDED]

    @property
    def tables_removed(self) -> list[Change]:
        return [c for c in self.changes if c.change_type == ChangeType.TABLE_REMOVED]

    @property
    def columns_added(self) -> list[Change]:
        return [c for c in self.changes if c.change_type == ChangeType.COLUMN_ADDED]

    @property
    def columns_removed(self) -> list[Change]:
        return [c for c in self.changes if c.change_type == ChangeType.COLUMN_REMOVED]

    def summary(self) -> str:
        """Return a human-readable summary of the diff."""
        lines: list[str] = []
        lines.append(f"Schema diff: {self.old_schema} → {self.new_schema}")
        lines.append(f"Total changes: {len(self.changes)}")
        lines.append(f"Breaking: {len(self.breaking_changes)}, Safe: {len(self.safe_changes)}")
        lines.append("")

        if self.breaking_changes:
            lines.append("⚠️  BREAKING CHANGES:")
            for c in self.breaking_changes:
                lines.append(f"  {c}")
            lines.append("")

        if self.safe_changes:
            lines.append("✅ SAFE CHANGES:")
            for c in self.safe_changes:
                lines.append(f"  {c}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize the diff to a dictionary."""
        return {
            "old_schema": self.old_schema,
            "new_schema": self.new_schema,
            "changes": [
                {
                    "type": c.change_type.value,
                    "table": c.table,
                    "column": c.column,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "breaking": c.breaking,
                    "description": c.description,
                }
                for c in self.changes
            ],
        }


class SchemaDiffer:
    """Compares two Schema objects and produces a SchemaDiff."""

    def diff(self, old: Schema, new: Schema) -> SchemaDiff:
        """Compare old and new schemas and return the diff."""
        result = SchemaDiff(old_schema=old.name, new_schema=new.name)

        # Build lookup maps (case-insensitive)
        old_tables = {t.name.lower(): t for t in old.tables}
        new_tables = {t.name.lower(): t for t in new.tables}

        old_names = set(old_tables.keys())
        new_names = set(new_tables.keys())

        # Tables added
        for name in sorted(new_names - old_names):
            result.changes.append(
                Change(
                    change_type=ChangeType.TABLE_ADDED,
                    table=new_tables[name].name,
                    new_value=new_tables[name].name,
                    breaking=False,
                    description=f"table '{new_tables[name].name}' added",
                )
            )

        # Tables removed
        for name in sorted(old_names - new_names):
            result.changes.append(
                Change(
                    change_type=ChangeType.TABLE_REMOVED,
                    table=old_tables[name].name,
                    old_value=old_tables[name].name,
                    breaking=True,
                    description=f"table '{old_tables[name].name}' removed — all data will be lost",
                )
            )

        # Tables in both — compare columns
        for name in sorted(old_names & new_names):
            old_table = old_tables[name]
            new_table = new_tables[name]
            self._diff_table(old_table, new_table, result)

        return result

    def _diff_table(self, old: Table, new: Table, result: SchemaDiff) -> None:
        """Compare two tables and add changes to the result."""
        # Build column lookup maps (case-insensitive)
        old_cols = {c.name.lower(): c for c in old.columns}
        new_cols = {c.name.lower(): c for c in new.columns}

        old_col_names = set(old_cols.keys())
        new_col_names = set(new_cols.keys())

        # Columns added
        for name in sorted(new_col_names - old_col_names):
            col = new_cols[name]
            # Adding a nullable column with a default is safe
            # Adding a NOT NULL column without default is breaking
            is_breaking = not col.nullable and col.default is None and not col.auto_increment
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_ADDED,
                    table=new.name,
                    column=col.name,
                    new_value=col.type_string,
                    breaking=is_breaking,
                    description=(
                        f"column '{col.name}' added ({col.type_string}, "
                        f"{'NOT NULL without default' if is_breaking else 'nullable or has default'})"
                    ),
                )
            )

        # Columns removed
        for name in sorted(old_col_names - new_col_names):
            col = old_cols[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_REMOVED,
                    table=old.name,
                    column=col.name,
                    old_value=col.type_string,
                    breaking=True,
                    description=f"column '{col.name}' removed — data will be lost",
                )
            )

        # Columns in both — compare properties
        for name in sorted(old_col_names & new_col_names):
            old_col = old_cols[name]
            new_col = new_cols[name]
            self._diff_column(old.name, old_col, new_col, result)

        # Compare foreign keys
        self._diff_foreign_keys(old, new, result)

        # Compare indexes
        self._diff_indexes(old, new, result)

        # Compare check constraints
        self._diff_checks(old, new, result)

        # Compare unique constraints
        self._diff_unique_constraints(old, new, result)

    def _diff_column(self, table: str, old: Column, new: Column, result: SchemaDiff) -> None:
        """Compare two columns and add changes to the result."""
        is_breaking, description = new.is_breaking_change_from(old)
        if description == "no changes":
            return

        # Determine the specific change types
        if old.base_type != new.base_type:
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_TYPE_CHANGED,
                    table=table,
                    column=new.name,
                    old_value=old.base_type.value,
                    new_value=new.base_type.value,
                    breaking=is_breaking,
                    description=description,
                )
            )
            # Reset and check other changes individually
            is_breaking, description = new.is_breaking_change_from(old)
            # Remove the type change part from description
            type_desc = f"type {'widened' if not is_breaking else 'changed'} from {old.base_type.value} to {new.base_type.value}"
            remaining = description.replace(type_desc, "").strip("; ").strip()

        if old.nullable != new.nullable:
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_NULLABILITY_CHANGED,
                    table=table,
                    column=new.name,
                    old_value="nullable" if old.nullable else "NOT NULL",
                    new_value="nullable" if new.nullable else "NOT NULL",
                    breaking=not new.nullable,  # nullable -> NOT NULL is breaking
                    description=f"{'nullable' if old.nullable else 'NOT NULL'} → {'nullable' if new.nullable else 'NOT NULL'}",
                )
            )

        if old.default != new.default:
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_DEFAULT_CHANGED,
                    table=table,
                    column=new.name,
                    old_value=old.default,
                    new_value=new.default,
                    breaking=old.default is not None and new.default is None,  # Removing default is breaking
                    description=f"default changed from {old.default!r} to {new.default!r}",
                )
            )

        if old.primary_key != new.primary_key:
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_PRIMARY_KEY_CHANGED,
                    table=table,
                    column=new.name,
                    old_value=str(old.primary_key),
                    new_value=str(new.primary_key),
                    breaking=True,
                    description=f"primary key changed from {old.primary_key} to {new.primary_key}",
                )
            )

        if old.unique != new.unique:
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_UNIQUE_CHANGED,
                    table=table,
                    column=new.name,
                    old_value=str(old.unique),
                    new_value=str(new.unique),
                    breaking=new.unique,  # Adding unique is breaking
                    description=f"unique changed from {old.unique} to {new.unique}",
                )
            )

        if old.references != new.references:
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_FOREIGN_KEY_CHANGED,
                    table=table,
                    column=new.name,
                    old_value=old.references,
                    new_value=new.references,
                    breaking=old.references is not None and new.references is None,
                    description=f"foreign key changed from {old.references!r} to {new.references!r}",
                )
            )

        if old.auto_increment != new.auto_increment:
            result.changes.append(
                Change(
                    change_type=ChangeType.COLUMN_AUTO_INCREMENT_CHANGED,
                    table=table,
                    column=new.name,
                    old_value=str(old.auto_increment),
                    new_value=str(new.auto_increment),
                    breaking=False,
                    description=f"auto_increment changed from {old.auto_increment} to {new.auto_increment}",
                )
            )

    def _diff_foreign_keys(self, old: Table, new: Table, result: SchemaDiff) -> None:
        """Compare foreign keys between two tables."""
        old_fks = {fk.name.lower(): fk for fk in old.foreign_keys}
        new_fks = {fk.name.lower(): fk for fk in new.foreign_keys}

        old_fk_names = set(old_fks.keys())
        new_fk_names = set(new_fks.keys())

        for name in sorted(new_fk_names - old_fk_names):
            fk = new_fks[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.FOREIGN_KEY_ADDED,
                    table=new.name,
                    new_value=f"{fk.columns} → {fk.reference_table}.{fk.reference_columns}",
                    breaking=False,
                    description=f"foreign key '{fk.name}' added: {fk.columns} → {fk.reference_table}.{fk.reference_columns}",
                )
            )

        for name in sorted(old_fk_names - new_fk_names):
            fk = old_fks[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.FOREIGN_KEY_REMOVED,
                    table=old.name,
                    old_value=f"{fk.columns} → {fk.reference_table}.{fk.reference_columns}",
                    breaking=True,
                    description=f"foreign key '{fk.name}' removed",
                )
            )

        for name in sorted(old_fk_names & new_fk_names):
            old_fk = old_fks[name]
            new_fk = new_fks[name]
            if (old_fk.columns != new_fk.columns or
                old_fk.reference_table != new_fk.reference_table or
                old_fk.reference_columns != new_fk.reference_columns or
                old_fk.on_delete != new_fk.on_delete or
                old_fk.on_update != new_fk.on_update):
                result.changes.append(
                    Change(
                        change_type=ChangeType.FOREIGN_KEY_CHANGED,
                        table=old.name,
                        old_value=f"{old_fk.columns} → {old_fk.reference_table}.{old_fk.reference_columns}",
                        new_value=f"{new_fk.columns} → {new_fk.reference_table}.{new_fk.reference_columns}",
                        breaking=True,
                        description=f"foreign key '{old_fk.name}' changed",
                    )
                )

    def _diff_indexes(self, old: Table, new: Table, result: SchemaDiff) -> None:
        """Compare indexes between two tables."""
        old_idxs = {idx.name.lower(): idx for idx in old.indexes}
        new_idxs = {idx.name.lower(): idx for idx in new.indexes}

        old_idx_names = set(old_idxs.keys())
        new_idx_names = set(new_idxs.keys())

        for name in sorted(new_idx_names - old_idx_names):
            idx = new_idxs[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.INDEX_ADDED,
                    table=new.name,
                    new_value=idx.name,
                    breaking=False,
                    description=f"index '{idx.name}' added on ({', '.join(idx.columns)})",
                )
            )

        for name in sorted(old_idx_names - new_idx_names):
            idx = old_idxs[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.INDEX_REMOVED,
                    table=old.name,
                    old_value=idx.name,
                    breaking=True,
                    description=f"index '{idx.name}' removed",
                )
            )

        for name in sorted(old_idx_names & new_idx_names):
            old_idx = old_idxs[name]
            new_idx = new_idxs[name]
            if (old_idx.columns != new_idx.columns or
                old_idx.unique != new_idx.unique or
                old_idx.method != new_idx.method):
                result.changes.append(
                    Change(
                        change_type=ChangeType.INDEX_CHANGED,
                        table=old.name,
                        old_value=old_idx.name,
                        new_value=new_idx.name,
                        breaking=True,
                        description=f"index '{old_idx.name}' changed",
                    )
                )

    def _diff_checks(self, old: Table, new: Table, result: SchemaDiff) -> None:
        """Compare check constraints between two tables."""
        old_checks = {chk.name.lower(): chk for chk in old.checks}
        new_checks = {chk.name.lower(): chk for chk in new.checks}

        old_check_names = set(old_checks.keys())
        new_check_names = set(new_checks.keys())

        for name in sorted(new_check_names - old_check_names):
            chk = new_checks[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.CHECK_ADDED,
                    table=new.name,
                    new_value=chk.expression,
                    breaking=True,  # Adding a check is potentially breaking
                    description=f"check constraint '{chk.name}' added: {chk.expression}",
                )
            )

        for name in sorted(old_check_names - new_check_names):
            chk = old_checks[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.CHECK_REMOVED,
                    table=old.name,
                    old_value=chk.expression,
                    breaking=False,
                    description=f"check constraint '{chk.name}' removed",
                )
            )

    def _diff_unique_constraints(self, old: Table, new: Table, result: SchemaDiff) -> None:
        """Compare unique constraints between two tables."""
        old_ucs = {uc.name.lower(): uc for uc in old.unique_constraints}
        new_ucs = {uc.name.lower(): uc for uc in new.unique_constraints}

        old_uc_names = set(old_ucs.keys())
        new_uc_names = set(new_ucs.keys())

        for name in sorted(new_uc_names - old_uc_names):
            uc = new_ucs[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.UNIQUE_CONSTRAINT_ADDED,
                    table=new.name,
                    new_value=str(uc.columns),
                    breaking=True,
                    description=f"unique constraint '{uc.name}' added on ({', '.join(uc.columns)})",
                )
            )

        for name in sorted(old_uc_names - new_uc_names):
            uc = old_ucs[name]
            result.changes.append(
                Change(
                    change_type=ChangeType.UNIQUE_CONSTRAINT_REMOVED,
                    table=old.name,
                    old_value=str(uc.columns),
                    breaking=False,
                    description=f"unique constraint '{uc.name}' removed",
                )
            )
