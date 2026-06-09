"""SQL linter for SQLGuard.

Detects unsafe patterns, style issues, and potential bugs in SQL queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    """Lint issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    STYLE = "style"


class LintRule(Enum):
    """All lint rules implemented by SQLGuard."""

    # Safety rules
    SELECT_STAR = "select_star"
    MISSING_WHERE_DELETE = "missing_where_delete"
    MISSING_WHERE_UPDATE = "missing_where_update"
    SQL_INJECTION_RISK = "sql_injection_risk"
    DANGEROUS_TRUNCATE = "dangerous_truncate"

    # Style rules
    IMPLICIT_JOIN = "implicit_join"
    TABLE_ALIAS_STAR = "table_alias_star"
    INEFFICIENT_COUNT = "inefficient_count"
    SUBQUERY_IN_SELECT = "subquery_in_select"
    NOT_NULL_WITH_DEFAULT = "not_null_with_default"
    MISSING_TABLE_ALIAS = "missing_table_alias"
    ORDINAL_POSITION_ORDER_BY = "ordinal_position_order_by"
    DUPLICATE_WHERE_CONDITION = "duplicate_where_condition"
    CASE_INSIDE_ORDER_BY = "case_inside_order_by"
    STRING_CONCAT_IN_WHERE = "string_concat_in_where"
    LIKE_PREFIX_WILDCARD = "like_prefix_wildcard"
    OR_IN_SELECT = "or_in_select"
    EXPENSIVE_IS_NULL_CHECK = "expensive_is_null_check"
    CARTESIAN_JOIN = "cartesian_join"
    FUNCTION_ON_INDEXED_COL = "function_on_indexed_col"
    EXPLICIT_COLUMN_LIST = "explicit_column_list"
    SCHEMA_PREFIX_MISSING = "schema_prefix_missing"
    SEMICOLON_MISSING = "semicolon_missing"


@dataclass
class LintIssue:
    """A single lint issue found in a SQL query."""

    rule: LintRule
    severity: Severity
    message: str
    line: int = 1
    column: int = 0
    sql: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        prefix = f"[{self.severity.value}]"
        location = f"line {self.line}" if self.line else ""
        parts = [prefix, self.rule.value, location, "—", self.message]
        if self.suggestion:
            parts.append(f"(suggestion: {self.suggestion})")
        return " ".join(parts)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "rule": self.rule.value,
            "severity": self.severity.value,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "suggestion": self.suggestion,
        }


class SQLLinter:
    """Lints SQL queries for unsafe patterns and style issues."""

    def __init__(
        self,
        *,
        strict: bool = False,
        ignore_rules: list[LintRule] | None = None,
        only_rules: list[LintRule] | None = None,
    ) -> None:
        self.strict = strict
        self.ignore_rules = set(ignore_rules) if ignore_rules else set()
        self.only_rules = set(only_rules) if only_rules else None

    def lint(self, sql: str) -> list[LintIssue]:
        """Lint a SQL string and return all issues found."""
        issues: list[LintIssue] = []
        lines = sql.split("\n")

        # Normalize for matching
        sql_upper = sql.upper().strip()
        # Remove string literals to avoid false positives
        sql_no_strings = re.sub(r"'[^']*'", "''", sql)
        sql_no_strings_upper = sql_no_strings.upper()

        # Run all rules
        rule_methods = [
            self._check_select_star,
            self._check_missing_where_delete,
            self._check_missing_where_update,
            self._check_sql_injection_risk,
            self._check_dangerous_truncate,
            self._check_implicit_join,
            self._check_table_alias_star,
            self._check_inefficient_count,
            self._check_subquery_in_select,
            self._check_missing_table_alias,
            self._check_ordinal_order_by,
            self._check_duplicate_where,
            self._check_like_prefix_wildcard,
            self._check_cartesian_join,
            self._check_function_on_indexed_col,
            self._check_explicit_column_list,
            self._check_semicolon_missing,
        ]

        for rule_method in rule_methods:
            rule_issues = rule_method(sql, sql_upper, sql_no_strings, sql_no_strings_upper, lines)
            for issue in rule_issues:
                if self._should_include(issue.rule):
                    issues.append(issue)

        return issues

    def lint_file(self, path: str) -> list[LintIssue]:
        """Lint a SQL file."""
        with open(path) as f:
            sql = f.read()
        return self.lint(sql)

    def _should_include(self, rule: LintRule) -> bool:
        """Check if a rule should be included in results."""
        return rule not in self.ignore_rules and (not self.only_rules or rule in self.only_rules)

    def _find_line_number(self, lines: list[str], pattern: str, start: int = 0) -> int:
        """Find the line number where a pattern appears."""
        pattern_upper = pattern.upper()
        for i, line in enumerate(lines):
            if i < start:
                continue
            if pattern_upper in line.upper():
                return i + 1
        return 1

    def _check_select_star(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for SELECT * usage."""
        issues: list[LintIssue] = []
        # Match SELECT * but not SELECT COUNT(*)
        pattern = r"\bSELECT\s+\*\s+FROM\b"
        for match in re.finditer(pattern, sql_clean_upper):
            line_num = sql_clean_upper[: match.start()].count("\n") + 1
            issues.append(
                LintIssue(
                    rule=LintRule.SELECT_STAR,
                    severity=Severity.WARNING,
                    message="SELECT * used — explicitly list needed columns for clarity and performance",
                    line=line_num,
                    suggestion="Replace * with explicit column list",
                )
            )
        return issues

    def _check_missing_where_delete(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for DELETE without WHERE clause."""
        issues: list[LintIssue] = []
        # Match DELETE FROM without WHERE
        pattern = r"\bDELETE\s+FROM\s+\w+\s*;?\s*$"
        if re.search(pattern, sql_clean_upper.strip(), re.MULTILINE):
            line_num = self._find_line_number(lines, "DELETE")
            issues.append(
                LintIssue(
                    rule=LintRule.MISSING_WHERE_DELETE,
                    severity=Severity.ERROR,
                    message="DELETE without WHERE clause — will delete all rows",
                    line=line_num,
                    suggestion="Add a WHERE clause to limit deletion scope",
                )
            )
        # Also check multi-statement DELETE without WHERE
        if re.search(
            r"\\bDELETE\\s+FROM\\s+\\w+\\s*$", sql_clean_upper.strip(), re.MULTILINE
        ) and not re.search(r"\\bWHERE\\b", sql_clean_upper):
            line_num = self._find_line_number(lines, "DELETE")
            issues.append(
                LintIssue(
                    rule=LintRule.MISSING_WHERE_DELETE,
                    severity=Severity.ERROR,
                    message="DELETE without WHERE clause — will delete all rows",
                    line=line_num,
                    suggestion="Add a WHERE clause to limit deletion scope",
                )
            )
        return issues

    def _check_missing_where_update(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for UPDATE without WHERE clause."""
        issues: list[LintIssue] = []
        if re.search(r"\\bUPDATE\\s+\\w+\\s+SET\\b", sql_clean_upper) and not re.search(
            r"\\bWHERE\\b", sql_clean_upper
        ):
            line_num = self._find_line_number(lines, "UPDATE")
            issues.append(
                LintIssue(
                    rule=LintRule.MISSING_WHERE_UPDATE,
                    severity=Severity.ERROR,
                    message="UPDATE without WHERE clause — will update all rows",
                    line=line_num,
                    suggestion="Add a WHERE clause to limit update scope",
                )
            )
        return issues

    def _check_sql_injection_risk(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for potential SQL injection patterns."""
        issues: list[LintIssue] = []
        # Check for string concatenation in WHERE clauses
        # Pattern: WHERE col = '...' + variable or WHERE col = "..." + variable
        concat_patterns = [
            r"['\"]\s*\+\s*\w+",  # string + variable
            r"\w+\s*\+\s*['\"]",  # variable + string
            r"f['\"].*\{.*\}.*['\"]",  # Python f-string in SQL
            r"\.format\(",  # .format() call
            r"\.join\(",  # .join() call
            r"%\s*\(\w+\)",  # % formatting
            r"%s",  # Python %s placeholder (without proper escaping)
        ]
        for pattern in concat_patterns:
            if re.search(pattern, sql):
                line_num = 1
                for i, line in enumerate(lines):
                    if re.search(pattern, line):
                        line_num = i + 1
                        break
                issues.append(
                    LintIssue(
                        rule=LintRule.SQL_INJECTION_RISK,
                        severity=Severity.ERROR,
                        message="Potential SQL injection — string concatenation or formatting detected in query",
                        line=line_num,
                        suggestion="Use parameterized queries with placeholders (?) instead of string concatenation",
                    )
                )
                break  # Only report once

        # Check for EXECUTE IMMEDIATE or similar dynamic SQL patterns
        dynamic_patterns = [
            r"\bEXECUTE\s+IMMEDIATE\b",
            r"\bEXEC\s*\(",
            r"\bsp_executesql\b",
        ]
        for pattern in dynamic_patterns:
            if re.search(pattern, sql_clean_upper):
                line_num = self._find_line_number(lines, "EXECUTE")
                issues.append(
                    LintIssue(
                        rule=LintRule.SQL_INJECTION_RISK,
                        severity=Severity.ERROR,
                        message="Dynamic SQL detected — ensure inputs are parameterized",
                        line=line_num,
                        suggestion="Use parameterized queries instead of dynamic SQL when possible",
                    )
                )
                break

        return issues

    def _check_dangerous_truncate(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for TRUNCATE TABLE statements."""
        issues: list[LintIssue] = []
        if re.search(r"\bTRUNCATE\s+TABLE?\b", sql_clean_upper):
            line_num = self._find_line_number(lines, "TRUNCATE")
            issues.append(
                LintIssue(
                    rule=LintRule.DANGEROUS_TRUNCATE,
                    severity=Severity.WARNING,
                    message="TRUNCATE TABLE — this cannot be rolled back in some databases and resets auto-increment",
                    line=line_num,
                    suggestion="Consider DELETE with WHERE if you need rollbacks or finer control",
                )
            )
        return issues

    def _check_implicit_join(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for implicit join syntax (comma-separated tables in FROM)."""
        issues: list[LintIssue] = []
        # Match FROM table1, table2 (implicit cross join)
        from_match = re.search(
            r"\bFROM\s+(.+?)(?:\bWHERE\b|\bGROUP\b|\bORDER\b|\bHAVING\b|\bLIMIT\b|$)",
            sql_clean_upper,
            re.DOTALL,
        )
        if from_match:
            from_clause = from_match.group(1).strip()
            # Check for comma-separated tables (no JOIN keyword)
            if "," in from_clause and "JOIN" not in sql_clean_upper:
                line_num = self._find_line_number(lines, "FROM")
                issues.append(
                    LintIssue(
                        rule=LintRule.IMPLICIT_JOIN,
                        severity=Severity.WARNING,
                        message="Implicit join (comma-separated FROM) — use explicit JOIN syntax for clarity",
                        line=line_num,
                        suggestion="Replace comma-separated tables with explicit JOIN ... ON syntax",
                    )
                )
        return issues

    def _check_table_alias_star(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for table.* usage (slightly better than * but still broad)."""
        issues: list[LintIssue] = []
        pattern = r"\b\w+\.\*\b"
        if re.search(pattern, sql_clean_upper):
            line_num = 1
            for i, line in enumerate(lines):
                if re.search(pattern, line.upper()):
                    line_num = i + 1
                    break
            issues.append(
                LintIssue(
                    rule=LintRule.TABLE_ALIAS_STAR,
                    severity=Severity.INFO,
                    message="table.* used — consider listing specific columns for clarity",
                    line=line_num,
                    suggestion="Replace table.* with table.col1, table.col2, ...",
                )
            )
        return issues

    def _check_inefficient_count(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for COUNT(*) when EXISTS would be more efficient."""
        issues: list[LintIssue] = []
        # Check for patterns like: SELECT COUNT(*) FROM ... WHERE ... used for existence check
        # This is a heuristic — we flag SELECT COUNT(*) in subqueries used in IF/EXISTS contexts
        if re.search(r"\\bSELECT\\s+COUNT\\s*\\(\\s*\\*\\s*\\)", sql_clean_upper) and re.search(
            r"\\(\\s*SELECT\\s+COUNT\\s*\\(\\s*\\*\\s*\\)", sql_clean_upper, re.IGNORECASE
        ):
            # Only flag in subquery contexts
            line_num = self._find_line_number(lines, "COUNT")
            issues.append(
                LintIssue(
                    rule=LintRule.INEFFICIENT_COUNT,
                    severity=Severity.INFO,
                    message="COUNT(*) in subquery — EXISTS is typically more efficient for existence checks",
                    line=line_num,
                    suggestion="Consider using EXISTS (SELECT 1 FROM ...) instead of COUNT(*) > 0",
                )
            )
        return issues

    def _check_subquery_in_select(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for correlated subqueries in SELECT clause."""
        issues: list[LintIssue] = []
        # Match SELECT (SELECT ...) — scalar subquery
        pattern = r"\bSELECT\s+.*\(SELECT\b"
        if re.search(pattern, sql_clean_upper, re.DOTALL):
            line_num = self._find_line_number(lines, "SELECT")
            issues.append(
                LintIssue(
                    rule=LintRule.SUBQUERY_IN_SELECT,
                    severity=Severity.WARNING,
                    message="Scalar subquery in SELECT clause — can be slow for large result sets",
                    line=line_num,
                    suggestion="Consider using a JOIN or lateral join instead",
                )
            )
        return issues

    def _check_missing_table_alias(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for multi-table queries without table aliases."""
        issues: list[LintIssue] = []
        # Count JOIN occurrences
        join_count = len(re.findall(r"\bJOIN\b", sql_clean_upper))
        if join_count >= 2:
            # Check if aliases are used (AS keyword or simple alias after table name)
            # Look for table names followed by aliases
            has_aliases = bool(re.search(r"\bJOIN\s+\w+\s+\w+\s+ON\b", sql_clean_upper))
            if not has_aliases:
                line_num = self._find_line_number(lines, "JOIN")
                issues.append(
                    LintIssue(
                        rule=LintRule.MISSING_TABLE_ALIAS,
                        severity=Severity.STYLE,
                        message="Multi-table query without table aliases — aliases improve readability",
                        line=line_num,
                        suggestion="Add short aliases to each table (e.g., users u, orders o)",
                    )
                )
        return issues

    def _check_ordinal_order_by(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for ordinal position in ORDER BY (e.g., ORDER BY 1, 2)."""
        issues: list[LintIssue] = []
        order_match = re.search(
            r"\bORDER\s+BY\s+(.+?)(?:\bLIMIT\b|\bOFFSET\b|;|$)", sql_clean_upper, re.DOTALL
        )
        if order_match:
            order_clause = order_match.group(1).strip()
            # Check for bare integers
            if re.search(r"\b\d+\b", order_clause):
                # Make sure these are ordinal references, not part of column names
                ordinal_pattern = r"(?:^|,)\s*(\d+)\s*(?:,|$|\bASC\b|\bDESC\b)"
                if re.search(ordinal_pattern, order_clause):
                    line_num = self._find_line_number(lines, "ORDER BY")
                    issues.append(
                        LintIssue(
                            rule=LintRule.ORDINAL_POSITION_ORDER_BY,
                            severity=Severity.WARNING,
                            message="ORDER BY with ordinal position — fragile if column order changes",
                            line=line_num,
                            suggestion="Use column names or aliases instead of ordinal positions",
                        )
                    )
        return issues

    def _check_duplicate_where(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for duplicate conditions in WHERE clause."""
        issues: list[LintIssue] = []
        where_match = re.search(
            r"\bWHERE\s+(.+?)(?:\bGROUP\b|\bORDER\b|\bHAVING\b|\bLIMIT\b|;|$)",
            sql_clean_upper,
            re.DOTALL,
        )
        if where_match:
            where_clause = where_match.group(1).strip()
            # Split by AND/OR and check for duplicates
            conditions = re.split(r"\b(?:AND|OR)\b", where_clause)
            conditions = [c.strip() for c in conditions if c.strip()]
            seen: set[str] = set()
            for cond in conditions:
                cond_normalized = re.sub(r"\s+", " ", cond.strip())
                if cond_normalized in seen:
                    line_num = self._find_line_number(lines, "WHERE")
                    issues.append(
                        LintIssue(
                            rule=LintRule.DUPLICATE_WHERE_CONDITION,
                            severity=Severity.WARNING,
                            message=f"Duplicate WHERE condition detected: {cond_normalized[:50]}",
                            line=line_num,
                            suggestion="Remove duplicate conditions from WHERE clause",
                        )
                    )
                    break
                seen.add(cond_normalized)
        return issues

    def _check_like_prefix_wildcard(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for LIKE patterns starting with wildcard (prevents index usage)."""
        issues: list[LintIssue] = []
        # Match LIKE '%...' or LIKE '%...%'
        # Restore original SQL for string matching since we stripped strings
        like_pattern = r"LIKE\s+['\"]%[^'\"]*['\"]"
        for match in re.finditer(like_pattern, sql, re.IGNORECASE):
            line_num = sql[: match.start()].count("\n") + 1
            issues.append(
                LintIssue(
                    rule=LintRule.LIKE_PREFIX_WILDCARD,
                    severity=Severity.WARNING,
                    message="LIKE with leading wildcard — prevents index usage, causing full table scan",
                    line=line_num,
                    suggestion="Avoid leading '%' in LIKE patterns if possible, or use full-text search",
                )
            )
        return issues

    def _check_cartesian_join(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for CROSS JOIN or Cartesian product patterns."""
        issues: list[LintIssue] = []
        if re.search(r"\bCROSS\s+JOIN\b", sql_clean_upper):
            line_num = self._find_line_number(lines, "CROSS JOIN")
            issues.append(
                LintIssue(
                    rule=LintRule.CARTESIAN_JOIN,
                    severity=Severity.WARNING,
                    message="CROSS JOIN detected — produces Cartesian product which can be very expensive",
                    line=line_num,
                    suggestion="Ensure CROSS JOIN is intentional; consider INNER JOIN with ON clause",
                )
            )
        return issues

    def _check_function_on_indexed_col(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for functions applied to columns in WHERE clauses (prevents index usage)."""
        issues: list[LintIssue] = []
        # Common patterns: LOWER(col), UPPER(col), DATE(col), YEAR(col)
        func_patterns = [
            r"\b(?:LOWER|UPPER|TRIM|LTRIM|RTRIM|LENGTH|SUBSTR|SUBSTRING|DATE|YEAR|MONTH|DAY|HOUR|COALESCE|CAST)\s*\(\s*(\w+)\s*\)",
        ]
        # Only flag if the function call is in a WHERE clause
        where_match = re.search(
            r"\bWHERE\b(.+?)(?:\bGROUP\b|\bORDER\b|\bHAVING\b|\bLIMIT\b|;|$)",
            sql_clean_upper,
            re.DOTALL,
        )
        if where_match:
            where_clause = where_match.group(1)
            for pattern in func_patterns:
                matches = re.finditer(pattern, where_clause, re.IGNORECASE)
                for match in matches:
                    col_name = match.group(1)
                    # Skip if it's a literal value, not a column
                    if col_name.upper() not in (
                        "NULL",
                        "TRUE",
                        "FALSE",
                        "CURRENT_DATE",
                        "CURRENT_TIMESTAMP",
                    ):
                        line_num = self._find_line_number(lines, "WHERE")
                        issues.append(
                            LintIssue(
                                rule=LintRule.FUNCTION_ON_INDEXED_COL,
                                severity=Severity.INFO,
                                message=f"Function applied to column '{col_name}' in WHERE — prevents index usage",
                                line=line_num,
                                suggestion="Rewrite to use the column directly (e.g., col = LOWER(value) instead of LOWER(col) = value)",
                            )
                        )
                        break  # Only report once per rule
        return issues

    def _check_explicit_column_list(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for INSERT without explicit column list."""
        issues: list[LintIssue] = []
        insert_pattern = r"\bINSERT\s+INTO\s+(\w+)\s+VALUES\s*\("
        if re.search(insert_pattern, sql_clean_upper):
            line_num = self._find_line_number(lines, "INSERT")
            issues.append(
                LintIssue(
                    rule=LintRule.EXPLICIT_COLUMN_LIST,
                    severity=Severity.WARNING,
                    message="INSERT without column list — fragile if table schema changes",
                    line=line_num,
                    suggestion="Add explicit column list: INSERT INTO table (col1, col2) VALUES (...)",
                )
            )
        return issues

    def _check_semicolon_missing(
        self, sql: str, sql_upper: str, sql_clean: str, sql_clean_upper: str, lines: list[str]
    ) -> list[LintIssue]:
        """Check for missing semicolons at end of statements."""
        issues: list[LintIssue] = []
        # Only check in strict mode
        if not self.strict:
            return issues

        stripped = sql.strip()
        if stripped and not stripped.endswith(";"):
            issues.append(
                LintIssue(
                    rule=LintRule.SEMICOLON_MISSING,
                    severity=Severity.STYLE,
                    message="Statement missing terminating semicolon",
                    line=len(lines),
                    suggestion="Add semicolon at end of statement",
                )
            )
        return issues
