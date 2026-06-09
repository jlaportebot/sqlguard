"""SQL query validator for SQLGuard.

Validates SQL queries against a schema to find issues like:
- References to non-existent tables or columns
- Type mismatches in comparisons
- Ambiguous column references
- Invalid ORDER BY references
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlguard.schema import Schema


@dataclass
class ValidationError:
    """A validation error found in a SQL query."""

    message: str
    table: str | None = None
    column: str | None = None
    line: int = 1
    severity: str = "error"  # error, warning

    def __str__(self) -> str:
        location = ""
        if self.table:
            location = f" in table '{self.table}'"
        if self.column:
            location = f" column '{self.column}'" + location.replace(" in ", " in table ")
        return f"[{self.severity}] Line {self.line}: {self.message}{location}"

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "table": self.table,
            "column": self.column,
            "line": self.line,
            "severity": self.severity,
        }


class QueryValidator:
    """Validates SQL queries against a schema definition."""

    def __init__(self, schema: Schema) -> None:
        self.schema = schema

    def validate(self, sql: str) -> list[ValidationError]:
        """Validate a SQL query against the schema.

        Checks for:
        - References to non-existent tables
        - References to non-existent columns
        - Ambiguous column references
        - Type mismatches in WHERE clauses (basic)
        """
        errors: list[ValidationError] = []

        sql_stripped = sql.strip()
        if not sql_stripped:
            return errors

        # Normalize SQL
        sql_upper_clean = re.sub(r"'[^']*'", "''", sql_stripped).upper()

        # Extract referenced tables and columns
        tables_referenced = self._extract_tables(sql_upper_clean)
        columns_referenced = self._extract_columns(sql_upper_clean)

        # Track table aliases
        aliases = self._extract_aliases(sql_upper_clean)

        # Build alias-to-table mapping
        alias_map: dict[str, str] = {}
        for alias, table_name in aliases.items():
            alias_map[alias.lower()] = table_name.lower()

        # Validate table references
        schema_table_names = {t.name.lower() for t in self.schema.tables}
        for table_ref in tables_referenced:
            ref_lower = table_ref.lower()
            # Check if it's an alias
            if ref_lower in alias_map:
                actual_table = alias_map[ref_lower]
                if actual_table not in schema_table_names:
                    errors.append(
                        ValidationError(
                            message=f"Table '{table_ref}' (aliased from '{actual_table}') does not exist in schema",
                            table=actual_table,
                            severity="error",
                        )
                    )
            elif ref_lower not in schema_table_names:
                # Could be a subquery alias, skip those
                if not re.search(r"\bAS\s+" + re.escape(table_ref) + r"\b", sql_upper_clean):
                    errors.append(
                        ValidationError(
                            message=f"Table '{table_ref}' does not exist in schema",
                            table=table_ref,
                            severity="error",
                        )
                    )

        # Validate column references
        for col_ref in columns_referenced:
            col_name = col_ref
            table_name: str | None = None

            # Handle table.column notation
            if "." in col_ref:
                parts = col_ref.split(".", 1)
                table_name = parts[0]
                col_name = parts[1]

                # Resolve alias
                if table_name.lower() in alias_map:
                    table_name = alias_map[table_name.lower()]

            # Check column existence
            if table_name:
                table_obj = self.schema.get_table(table_name)
                if (
                    table_obj
                    and table_name.lower() in schema_table_names
                    and table_obj.get_column(col_name) is None
                    and not re.match(
                        r"(?:COUNT|SUM|AVG|MIN|MAX|COALESCE|NULLIF|CAST|EXTRACT|ROW_NUMBER|RANK|DENSE_RANK|LEAD|LAG|FIRST_VALUE|LAST_VALUE|NTH_VALUE|OVER|PARTITION)",
                        col_name,
                        re.IGNORECASE,
                    )
                ):
                    errors.append(
                        ValidationError(
                            message=f"Column '{col_name}' does not exist in table '{table_name}'",
                            table=table_name,
                            column=col_name,
                            severity="error",
                        )
                    )
            else:
                # Ambiguous reference check — is the column in multiple tables?
                tables_with_col: list[str] = []
                for table in self.schema.tables:
                    if table.get_column(col_name) is not None:
                        tables_with_col.append(table.name)

                if len(tables_with_col) == 0 and tables_referenced:
                    # Column doesn't exist in any referenced table
                    # But only flag if we found tables in the query
                    in_referenced = False
                    for t_ref in tables_referenced:
                        t_name = alias_map.get(t_ref.lower(), t_ref.lower())
                        t_obj = self.schema.get_table(t_name)
                        if t_obj and t_obj.get_column(col_name) is not None:
                            in_referenced = True
                            break

                    if not in_referenced and not self._is_keyword_or_function(col_name):
                        errors.append(
                            ValidationError(
                                message=f"Column '{col_name}' does not exist in any referenced table",
                                column=col_name,
                                severity="error",
                            )
                        )
                elif len(tables_with_col) > 1 and len(tables_referenced) > 1:
                    # Column exists in multiple tables — ambiguous
                    matching = [
                        t
                        for t in tables_with_col
                        if t.lower()
                        in {alias_map.get(r.lower(), r.lower()) for r in tables_referenced}
                    ]
                    if len(matching) > 1:
                        errors.append(
                            ValidationError(
                                message=f"Column '{col_name}' is ambiguous — exists in tables: {', '.join(matching)}",
                                column=col_name,
                                severity="warning",
                            )
                        )

        # Validate JOIN conditions
        join_errors = self._validate_joins(sql_upper_clean, alias_map)
        errors.extend(join_errors)

        # Validate ORDER BY references
        order_errors = self._validate_order_by(sql_upper_clean, alias_map)
        errors.extend(order_errors)

        # Validate GROUP BY references
        group_errors = self._validate_group_by(sql_upper_clean, alias_map)
        errors.extend(group_errors)

        return errors

    def _is_keyword_or_function(self, name: str) -> bool:
        """Check if a name is a SQL keyword or function (not a column)."""
        sql_keywords = {
            "SELECT",
            "FROM",
            "WHERE",
            "AND",
            "OR",
            "NOT",
            "IN",
            "IS",
            "NULL",
            "TRUE",
            "FALSE",
            "AS",
            "ON",
            "JOIN",
            "LEFT",
            "RIGHT",
            "INNER",
            "OUTER",
            "CROSS",
            "FULL",
            "GROUP",
            "ORDER",
            "BY",
            "HAVING",
            "LIMIT",
            "OFFSET",
            "UNION",
            "ALL",
            "DISTINCT",
            "EXISTS",
            "BETWEEN",
            "LIKE",
            "CASE",
            "WHEN",
            "THEN",
            "ELSE",
            "END",
            "ASC",
            "DESC",
            "INSERT",
            "INTO",
            "VALUES",
            "UPDATE",
            "SET",
            "DELETE",
            "CREATE",
            "DROP",
            "ALTER",
            "TABLE",
            "INDEX",
            "VIEW",
            "PRIMARY",
            "KEY",
            "FOREIGN",
            "REFERENCES",
            "CONSTRAINT",
            "DEFAULT",
            "CHECK",
            "UNIQUE",
            "AUTO_INCREMENT",
            "SERIAL",
            "RETURNING",
            "COUNT",
            "SUM",
            "AVG",
            "MIN",
            "MAX",
            "COALESCE",
            "NULLIF",
            "CAST",
            "EXTRACT",
            "ROW_NUMBER",
            "RANK",
            "DENSE_RANK",
            "LEAD",
            "LAG",
            "OVER",
            "PARTITION",
            "NOW",
            "CURRENT_DATE",
            "CURRENT_TIME",
            "CURRENT_TIMESTAMP",
            "WINDOW",
            "RECURSIVE",
            "WITH",
            "IF",
            "IIF",
            "TOTAL",
            "GROUP_CONCAT",
            "STRING_AGG",
            "ARRAY_AGG",
            "BOOL_AND",
            "BOOL_OR",
            "EVERY",
            "SOME",
            "ANY",
        }
        return name.upper() in sql_keywords

    def _extract_tables(self, sql_upper: str) -> list[str]:
        """Extract table names from FROM and JOIN clauses."""
        tables: list[str] = []

        # FROM clause
        from_pattern = r"\bFROM\s+(\w+)"
        for match in re.finditer(from_pattern, sql_upper):
            name = match.group(1)
            if not self._is_keyword_or_function(name):
                tables.append(name)

        # JOIN clauses
        join_pattern = r"\b(?:INNER|LEFT|RIGHT|FULL|CROSS)?\s*JOIN\s+(\w+)"
        for match in re.finditer(join_pattern, sql_upper):
            name = match.group(1)
            if not self._is_keyword_or_function(name):
                tables.append(name)

        # INSERT INTO
        insert_pattern = r"\bINSERT\s+INTO\s+(\w+)"
        for match in re.finditer(insert_pattern, sql_upper):
            tables.append(match.group(1))

        # UPDATE
        update_pattern = r"\bUPDATE\s+(\w+)"
        for match in re.finditer(update_pattern, sql_upper):
            tables.append(match.group(1))

        # DELETE FROM
        delete_pattern = r"\bDELETE\s+FROM\s+(\w+)"
        for match in re.finditer(delete_pattern, sql_upper):
            tables.append(match.group(1))

        return tables

    def _extract_columns(self, sql_upper: str) -> list[str]:
        """Extract column references from the query."""
        columns: list[str] = []

        # table.column notation
        dot_pattern = r"(\w+)\.(\w+)"
        for match in re.finditer(dot_pattern, sql_upper):
            table_part = match.group(1)
            col_part = match.group(2)
            if not self._is_keyword_or_function(col_part):
                columns.append(f"{table_part}.{col_part}")

        # Standalone columns in SELECT (before FROM)
        select_match = re.search(r"\bSELECT\s+(.*?)\bFROM\b", sql_upper, re.DOTALL)
        if select_match:
            select_clause = select_match.group(1)
            # Split by comma and extract column names
            parts = re.split(r",", select_clause)
            for part in parts:
                part = part.strip()
                # Skip aggregates, functions, *, and aliases
                if part in ("*",) or re.match(r"(?:COUNT|SUM|AVG|MIN|MAX)\s*\(", part):
                    continue
                # Skip expressions with parentheses (function calls)
                if "(" in part and ")" in part:
                    continue
                # Extract the last word (after AS if aliased)
                alias_split = re.split(r"\bAS\b", part, flags=re.IGNORECASE)
                col_name = alias_split[0].strip().split()[-1] if alias_split[0].strip() else ""
                if col_name and not self._is_keyword_or_function(col_name) and "." not in col_name:
                    columns.append(col_name)

        # Columns in WHERE clause
        where_match = re.search(
            r"\bWHERE\s+(.+?)(?:\bGROUP\b|\bORDER\b|\bHAVING\b|\bLIMIT\b|;|$)", sql_upper, re.DOTALL
        )
        if where_match:
            where_clause = where_match.group(1)
            # Extract column names from comparisons: col = value, col > value, etc.
            comp_pattern = r"(\w+)\s*(?:=|!=|<>|>|<|>=|<=|LIKE|IN|IS|BETWEEN)"
            for match in re.finditer(comp_pattern, where_clause):
                name = match.group(1)
                if not self._is_keyword_or_function(name) and "." not in name:
                    columns.append(name)

        return columns

    def _extract_aliases(self, sql_upper: str) -> dict[str, str]:
        """Extract table aliases from the query."""
        aliases: dict[str, str] = {}

        # Pattern: FROM table alias or FROM table AS alias
        from_alias_pattern = r"\bFROM\s+(\w+)\s+(?:AS\s+)?(\w+)"
        for match in re.finditer(from_alias_pattern, sql_upper):
            table_name = match.group(1)
            alias = match.group(2)
            if not self._is_keyword_or_function(alias) and alias.upper() not in (
                "WHERE",
                "JOIN",
                "INNER",
                "LEFT",
                "RIGHT",
                "CROSS",
                "FULL",
                "ON",
                "SET",
                "GROUP",
                "ORDER",
                "HAVING",
                "LIMIT",
                "UNION",
            ):
                aliases[alias] = table_name

        # Pattern: JOIN table alias or JOIN table AS alias
        join_alias_pattern = r"\bJOIN\s+(\w+)\s+(?:AS\s+)?(\w+)\s+ON\b"
        for match in re.finditer(join_alias_pattern, sql_upper):
            table_name = match.group(1)
            alias = match.group(2)
            if not self._is_keyword_or_function(alias):
                aliases[alias] = table_name

        return aliases

    def _validate_joins(self, sql_upper: str, alias_map: dict[str, str]) -> list[ValidationError]:
        """Validate JOIN ON conditions reference valid columns."""
        errors: list[ValidationError] = []

        # Extract JOIN ... ON conditions
        join_pattern = r"\\bJOIN\\s+(\\w+)\\s+(?:AS\\s+)?(\\w+)?\\s*ON\\s+(\\w+)\\.(\\w+)\\s*=\\s*(\\w+)\\.(\\w+)"
        for match in re.finditer(join_pattern, sql_upper):
            _ = match.group(1)
            _ = match.group(2)
            left_alias = match.group(3)
            left_col = match.group(4)
            right_alias = match.group(5)
            right_col = match.group(6)

            # Resolve aliases
            actual_left = alias_map.get(left_alias.lower(), left_alias.lower())
            actual_right = alias_map.get(right_alias.lower(), right_alias.lower())

            # Validate left side
            left_table = self.schema.get_table(actual_left)
            if left_table and left_table.get_column(left_col) is None:
                errors.append(
                    ValidationError(
                        message=f"JOIN condition references non-existent column '{left_col}' in table '{actual_left}'",
                        table=actual_left,
                        column=left_col,
                        severity="error",
                    )
                )

            # Validate right side
            right_table = self.schema.get_table(actual_right)
            if right_table and right_table.get_column(right_col) is None:
                errors.append(
                    ValidationError(
                        message=f"JOIN condition references non-existent column '{right_col}' in table '{actual_right}'",
                        table=actual_right,
                        column=right_col,
                        severity="error",
                    )
                )

        return errors

    def _validate_order_by(
        self, sql_upper: str, alias_map: dict[str, str]
    ) -> list[ValidationError]:
        """Validate ORDER BY references."""
        errors: list[ValidationError] = []

        order_match = re.search(
            r"\bORDER\s+BY\s+(.+?)(?:\bLIMIT\b|\bOFFSET\b|;|$)", sql_upper, re.DOTALL
        )
        if order_match:
            order_clause = order_match.group(1).strip()
            parts = [p.strip() for p in order_clause.split(",")]

            for part in parts:
                # Remove ASC/DESC
                col_ref = re.sub(r"\b(ASC|DESC)\b", "", part, flags=re.IGNORECASE).strip()
                if not col_ref or col_ref.isdigit():
                    continue  # Ordinal or empty

                if "." in col_ref:
                    table_part, col_name = col_ref.split(".", 1)
                    actual_table = alias_map.get(table_part.lower(), table_part.lower())
                    table_obj = self.schema.get_table(actual_table)
                    if table_obj and table_obj.get_column(col_name) is None:
                        errors.append(
                            ValidationError(
                                message=f"ORDER BY references non-existent column '{col_name}' in table '{actual_table}'",
                                table=actual_table,
                                column=col_name,
                                severity="error",
                            )
                        )

        return errors

    def _validate_group_by(
        self, sql_upper: str, alias_map: dict[str, str]
    ) -> list[ValidationError]:
        """Validate GROUP BY references."""
        errors: list[ValidationError] = []

        group_match = re.search(
            r"\bGROUP\s+BY\s+(.+?)(?:\bHAVING\b|\bORDER\b|\bLIMIT\b|;|$)", sql_upper, re.DOTALL
        )
        if group_match:
            group_clause = group_match.group(1).strip()
            parts = [p.strip() for p in group_clause.split(",")]

            for part in parts:
                col_ref = part.strip()
                if not col_ref or col_ref.isdigit():
                    continue

                if "." in col_ref:
                    table_part, col_name = col_ref.split(".", 1)
                    actual_table = alias_map.get(table_part.lower(), table_part.lower())
                    table_obj = self.schema.get_table(actual_table)
                    if table_obj and table_obj.get_column(col_name) is None:
                        errors.append(
                            ValidationError(
                                message=f"GROUP BY references non-existent column '{col_name}' in table '{actual_table}'",
                                table=actual_table,
                                column=col_name,
                                severity="error",
                            )
                        )

        return errors
