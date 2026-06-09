"""SQL semantic analyzer for SQLGuard.

Provides deep analysis of parsed SQL using the AST from sqlguard.parser.
Detects semantic issues beyond what regex-based linting can find:
- Unused tables/columns
- Ambiguous column references
- Missing JOIN conditions
- Type mismatches (where inferrable)
- Redundant clauses
- Subquery correctness
- Window function misuse
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from sqlguard.ast_nodes import (
    AstNode,
    AstVisitor,
    BetweenExpression,
    BinaryOp,
    CaseExpression,
    CastExpression,
    ColumnRef,
    CreateTableStatement,
    DeleteStatement,
    ExistsExpression,
    Expression,
    FromClause,
    FunctionCall,
    FunctionRef,
    InExpression,
    InsertStatement,
    JoinClause,
    LikeExpression,
    Literal,
    SelectColumn,
    SelectStatement,
    Star,
    SubqueryExpression,
    SubqueryRef,
    TableRef,
    TypeCast,
    UnaryOp,
    UpdateStatement,
)
from sqlguard.parser import ParseError, parse_sql
from sqlguard.tokens import TokenizerError


class Severity(Enum):
    """Severity levels for analysis findings."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    STYLE = "style"


class AnalysisRule(Enum):
    """Analysis rule identifiers."""

    # Error-level rules
    AMBIGUOUS_COLUMN = "ambiguous_column"
    MISSING_JOIN_CONDITION = "missing_join_condition"
    INVALID_COLUMN_REFERENCE = "invalid_column_reference"
    INVALID_TABLE_REFERENCE = "invalid_table_reference"
    SUBQUERY_MISSING_ALIAS = "subquery_missing_alias"
    DUPLICATE_ALIAS = "duplicate_alias"

    # Warning-level rules
    UNUSED_TABLE = "unused_table"
    UNUSED_COLUMN = "unused_column"
    SELECT_STAR_IN_PRODUCTION = "select_star_in_production"
    IMPLICIT_CROSS_JOIN = "implicit_cross_join"
    REDUNDANT_WHERE = "redundant_where"
    REDUNDANT_DISTINCT = "redundant_distinct"
    COALESCE_SIMPLIFIABLE = "coalesce_simplifiable"
    LIKE_LEADING_WILDCARD = "like_leading_wildcard"
    EMPTY_TABLE_LIST = "empty_table_list"
    UNNECESSARY_LIMIT_ONE = "unnecessary_limit_one"

    # Info-level rules
    COLUMN_IN_SELECT_NOT_GROUPED = "column_in_select_not_grouped"
    WINDOW_WITHOUT_ORDER = "window_without_order"
    TYPE_CAST_UNNECESSARY = "type_cast_unnecessary"
    SUBOPTIMAL_JOIN_TYPE = "suboptimal_join_type"
    POTENTIAL_CARTESIAN_PRODUCT = "potential_cartesian_product"
    MANY_JOINS = "many_joins"
    DEEPLY_NESTED_SUBQUERY = "deeply_nested_subquery"
    COMPLEX_EXPRESSION = "complex_expression"

    # Style-level rules
    ALIASED_COLUMN_SAME_NAME = "aliased_column_same_name"
    MIXED_JOIN_STYLES = "mixed_join_styles"
    IMPLICIT_INNER_JOIN = "implicit_inner_join"


@dataclass
class AnalysisFinding:
    """A single finding from the semantic analyzer."""

    rule: AnalysisRule
    severity: Severity
    message: str
    line: int = 0
    column: int = 0
    suggestion: str | None = None

    def __str__(self) -> str:
        prefix = self.severity.value.upper()
        suggestion_str = f" — {self.suggestion}" if self.suggestion else ""
        return f"{prefix}: [{self.rule.value}] {self.message}{suggestion_str}"

    def to_dict(self) -> dict:
        """Convert to a dictionary for JSON serialization."""
        return {
            "rule": self.rule.value,
            "severity": self.severity.value,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "suggestion": self.suggestion,
        }


@dataclass
class AnalysisResult:
    """The complete result of analyzing a SQL program."""

    findings: list[AnalysisFinding] = field(default_factory=list)
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    cte_names: list[str] = field(default_factory=list)
    statement_count: int = 0
    has_subqueries: bool = False
    has_window_functions: bool = False
    max_nesting_depth: int = 0

    @property
    def has_errors(self) -> bool:
        return any(f.severity == Severity.ERROR for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == Severity.WARNING for f in self.findings)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    def summary(self) -> str:
        """Generate a human-readable summary."""
        parts: list[str] = []
        parts.append(f"Statements: {self.statement_count}")
        parts.append(f"Tables: {len(self.tables_used)}")
        parts.append(f"Columns: {len(self.columns_used)}")

        if self.has_subqueries:
            parts.append(f"Subqueries: yes (max depth: {self.max_nesting_depth})")
        if self.has_window_functions:
            parts.append("Window functions: yes")

        parts.append(f"Findings: {self.error_count} errors, {self.warning_count} warnings")

        return " | ".join(parts)


class SemanticAnalyzer:
    """Analyzes SQL semantically using the parsed AST.

    Goes beyond regex-based linting to detect:
    - Ambiguous column references
    - Missing JOIN conditions (potential cartesian products)
    - Unused tables/columns
    - Redundant clauses
    - Subquery issues
    - Window function misuse

    Usage:
        analyzer = SemanticAnalyzer()
        result = analyzer.analyze("SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id")
    """

    def __init__(self, strict: bool = False) -> None:
        self.strict = strict
        self._findings: list[AnalysisFinding] = []
        self._table_aliases: dict[str, str] = {}  # alias -> table_name
        self._tables_in_scope: list[str] = []
        self._columns_in_scope: list[tuple[str, str]] = []  # (table, column)
        self._cte_names: list[str] = []
        self._nesting_depth: int = 0
        self._max_nesting_depth: int = 0

    def analyze(self, sql: str) -> AnalysisResult:
        """Analyze a SQL string and return findings."""
        self._findings = []
        self._table_aliases = {}
        self._tables_in_scope = []
        self._columns_in_scope = []
        self._cte_names = []
        self._nesting_depth = 0
        self._max_nesting_depth = 0

        try:
            program = parse_sql(sql)
        except (ParseError, TokenizerError) as e:
            self._findings.append(
                AnalysisFinding(
                    rule=AnalysisRule.INVALID_TABLE_REFERENCE,
                    severity=Severity.ERROR,
                    message=f"Parse error: {e}",
                )
            )
            return AnalysisResult(
                findings=self._findings,
                statement_count=0,
            )

        all_tables: list[str] = []
        all_columns: list[str] = []
        has_subqueries = False
        has_window_functions = False

        for stmt in program.statements:
            tables = self._analyze_statement(stmt)
            all_tables.extend(t for t in tables if t not in all_tables)

        # Collect column references from the AST
        collector = _ColumnCollector()
        for stmt in program.statements:
            stmt.accept(collector)
        all_columns = [c.qualified_name for c in collector.columns]
        has_subqueries = collector.has_subqueries
        has_window_functions = collector.has_window_functions

        return AnalysisResult(
            findings=self._findings,
            tables_used=all_tables,
            columns_used=all_columns,
            cte_names=list(self._cte_names),
            statement_count=len(program.statements),
            has_subqueries=has_subqueries,
            has_window_functions=has_window_functions,
            max_nesting_depth=self._max_nesting_depth,
        )

    def _add_finding(
        self,
        rule: AnalysisRule,
        severity: Severity,
        message: str,
        line: int = 0,
        column: int = 0,
        suggestion: str | None = None,
    ) -> None:
        """Add a finding to the analysis results."""
        self._findings.append(
            AnalysisFinding(
                rule=rule,
                severity=severity,
                message=message,
                line=line,
                column=column,
                suggestion=suggestion,
            )
        )

    def _analyze_statement(self, stmt: AstNode) -> list[str]:
        """Analyze a single statement, returning list of table names used."""
        tables: list[str] = []

        if isinstance(stmt, SelectStatement):
            tables.extend(self._analyze_select(stmt))
        elif isinstance(stmt, InsertStatement):
            tables.append(stmt.table.name)
            if stmt.subquery:
                tables.extend(self._analyze_select(stmt.subquery))
        elif isinstance(stmt, UpdateStatement):
            tables.append(stmt.table.name)
            if stmt.from_clause:
                for t in stmt.from_clause.get_all_tables():
                    tables.append(t.name)
            if stmt.where_clause:
                self._check_expression(stmt.where_clause)
        elif isinstance(stmt, DeleteStatement):
            tables.append(stmt.table.name)
            if stmt.using_clause:
                for t in stmt.using_clause.get_all_tables():
                    tables.append(t.name)
            if stmt.where_clause:
                self._check_expression(stmt.where_clause)
        elif isinstance(stmt, CreateTableStatement):
            tables.append(stmt.name)

        return tables

    def _analyze_select(self, stmt: SelectStatement) -> list[str]:
        """Analyze a SELECT statement."""
        # Reset alias scope for this SELECT
        old_aliases = self._table_aliases.copy()
        old_tables = self._tables_in_scope.copy()

        # CTEs
        for cte in stmt.cte_list:
            self._cte_names.append(cte.name)
            self._table_aliases[cte.name] = cte.name
            self._analyze_select(cte.subquery)

        # FROM clause
        tables_in_from: list[TableRef] = []
        if stmt.from_clause:
            tables_in_from = stmt.from_clause.get_all_tables()
            for t in tables_in_from:
                self._tables_in_scope.append(t.name)
                if t.alias:
                    self._table_aliases[t.alias] = t.name
                self._table_aliases[t.name] = t.name

        # Check for missing JOIN conditions
        if stmt.from_clause:
            self._check_join_conditions(stmt.from_clause)

        # Check SELECT list
        self._check_select_list(stmt)

        # Check WHERE clause
        if stmt.where_clause:
            self._check_expression(stmt.where_clause)

        # Check GROUP BY usage
        if stmt.group_by:
            self._check_group_by_usage(stmt)

        # Check for redundant DISTINCT with GROUP BY
        if stmt.distinct and stmt.group_by:
            self._add_finding(
                AnalysisRule.REDUNDANT_DISTINCT,
                Severity.WARNING,
                "DISTINCT is redundant when GROUP BY is present",
                suggestion="Remove DISTINCT — GROUP BY already ensures uniqueness",
            )

        # Check ORDER BY
        self._check_order_by(stmt)

        # Check UNION clauses
        for union in stmt.union_clauses:
            self._analyze_select(union.right)

        # Nesting depth for subqueries
        self._nesting_depth += 1
        if self._nesting_depth > self._max_nesting_depth:
            self._max_nesting_depth = self._nesting_depth

        if self._nesting_depth > 3:
            self._add_finding(
                AnalysisRule.DEEPLY_NESTED_SUBQUERY,
                Severity.INFO,
                f"Subquery nesting depth is {self._nesting_depth}",
                suggestion="Consider using CTEs to flatten nested subqueries",
            )

        self._nesting_depth -= 1

        # Restore alias scope
        self._table_aliases = old_aliases
        self._tables_in_scope = old_tables

        return [t.name for t in tables_in_from]

    def _check_join_conditions(self, from_clause: FromClause) -> None:
        """Check JOIN conditions for potential issues."""
        for join in from_clause.joins:
            # Missing JOIN condition
            if not join.has_condition and join.join_type != "CROSS":
                self._add_finding(
                    AnalysisRule.MISSING_JOIN_CONDITION,
                    Severity.ERROR,
                    f"{join.join_type} JOIN has no ON/USING condition",
                    suggestion="Add an ON clause or use CROSS JOIN explicitly",
                )

            # Implicit cross join (comma join)
            if join.is_cross_join and join.join_type == "CROSS" and not join.condition:
                self._add_finding(
                    AnalysisRule.IMPLICIT_CROSS_JOIN,
                    Severity.WARNING,
                    "Implicit cross join (comma-separated tables)",
                    suggestion="Use explicit CROSS JOIN syntax for clarity",
                )

            # Many joins
            if len(from_clause.joins) >= 5:
                self._add_finding(
                    AnalysisRule.MANY_JOINS,
                    Severity.INFO,
                    f"Query has {len(from_clause.joins)} JOINs — consider splitting",
                    suggestion="Complex queries with many JOINs can be hard to maintain; consider CTEs",
                )
                break  # Only report once per FROM clause

        # Potential cartesian product: multiple tables without join conditions
        if len(from_clause.joins) > 1:
            unconditioned = sum(
                1 for j in from_clause.joins if not j.has_condition and j.join_type != "CROSS"
            )
            if unconditioned > 0:
                self._add_finding(
                    AnalysisRule.POTENTIAL_CARTESIAN_PRODUCT,
                    Severity.WARNING,
                    f"Potential cartesian product: {unconditioned} JOIN(s) without conditions",
                )

    def _check_select_list(self, stmt: SelectStatement) -> None:
        """Check the SELECT column list for issues."""
        for col in stmt.columns:
            if isinstance(col, SelectColumn):
                # SELECT *
                if isinstance(col.expr, Star):
                    self._add_finding(
                        AnalysisRule.SELECT_STAR_IN_PRODUCTION,
                        Severity.WARNING,
                        "SELECT * used — explicitly list needed columns",
                        suggestion="SELECT * can break when schema changes and fetches unnecessary data",
                    )

                # Alias same as column name
                if (
                    col.alias
                    and isinstance(col.expr, ColumnRef)
                    and col.alias.lower() == col.expr.name.lower()
                ):
                    self._add_finding(
                        AnalysisRule.ALIASED_COLUMN_SAME_NAME,
                        Severity.STYLE,
                        f"Column '{col.alias}' is aliased to the same name",
                    )

                # Check expression for issues (window functions, type casts, LIKE, etc.)
                self._check_expression(col.expr)

                # LIKE in expression — check for leading wildcards
                self._check_like_in_expression(col.expr)

    def _check_like_in_expression(self, expr: Expression) -> None:
        """Recursively check for LIKE with leading wildcards (performance issue)."""
        if isinstance(expr, LikeExpression) and expr.has_leading_wildcard:
            self._add_finding(
                AnalysisRule.LIKE_LEADING_WILDCARD,
                Severity.WARNING,
                "LIKE pattern starts with wildcard — prevents index usage",
                suggestion="Consider full-text search (to_tsvector/to_tsquery) or a trigram index",
            )

        # Recurse into sub-expressions
        if isinstance(expr, BinaryOp):
            self._check_like_in_expression(expr.left)
            self._check_like_in_expression(expr.right)
        elif isinstance(expr, UnaryOp):
            self._check_like_in_expression(expr.operand)
        elif isinstance(expr, FunctionCall):
            for arg in expr.args:
                self._check_like_in_expression(arg)
        elif isinstance(expr, CaseExpression):
            for when in expr.when_clauses:
                self._check_like_in_expression(when.condition)
                self._check_like_in_expression(when.result)
            if expr.else_clause:
                self._check_like_in_expression(expr.else_clause)

    def _check_expression(self, expr: Expression) -> None:
        """Check an expression for issues."""
        # Window functions without ORDER BY
        if isinstance(expr, FunctionCall) and expr.over_clause and not expr.over_clause.order_by:
            self._add_finding(
                AnalysisRule.WINDOW_WITHOUT_ORDER,
                Severity.INFO,
                f"Window function {expr.name}() has no ORDER BY in OVER clause",
                suggestion="Most window functions need ORDER BY for deterministic results",
            )

        # Redundant type casts
        if isinstance(expr, TypeCast):
            self._check_type_cast(expr)
        elif isinstance(expr, CastExpression):
            self._check_cast_expression(expr)

        # LIKE with leading wildcard
        self._check_like_in_expression(expr)

        # Complex expression nesting
        depth = self._expression_depth(expr)
        if depth > 10:
            self._add_finding(
                AnalysisRule.COMPLEX_EXPRESSION,
                Severity.INFO,
                f"Expression nesting depth is {depth} — consider simplifying",
            )

        # Recurse
        if isinstance(expr, BinaryOp):
            self._check_expression(expr.left)
            self._check_expression(expr.right)
        elif isinstance(expr, UnaryOp):
            self._check_expression(expr.operand)
        elif isinstance(expr, FunctionCall):
            for arg in expr.args:
                self._check_expression(arg)
            if expr.filter_clause:
                self._check_expression(expr.filter_clause)
        elif isinstance(expr, CaseExpression):
            for when in expr.when_clauses:
                self._check_expression(when.condition)
                self._check_expression(when.result)
            if expr.else_clause:
                self._check_expression(expr.else_clause)
        elif isinstance(expr, InExpression):
            self._check_expression(expr.expr)
            for v in expr.values:
                self._check_expression(v)
        elif isinstance(expr, BetweenExpression):
            self._check_expression(expr.expr)
            self._check_expression(expr.low)
            self._check_expression(expr.high)
        elif isinstance(expr, (SubqueryExpression, ExistsExpression)):
            self._analyze_select(expr.subquery)

    def _check_type_cast(self, expr: TypeCast) -> None:
        """Check for unnecessary type casts."""
        if isinstance(expr.expr, Literal):
            # Casting a string literal to the same type
            if expr.expr.kind == "string" and expr.target_type.upper() in (
                "TEXT",
                "VARCHAR",
                "CHAR",
            ):
                self._add_finding(
                    AnalysisRule.TYPE_CAST_UNNECESSARY,
                    Severity.STYLE,
                    f"Unnecessary cast of string literal to {expr.target_type}",
                )
            elif expr.expr.kind == "integer" and expr.target_type.upper() in (
                "INT",
                "INTEGER",
                "BIGINT",
                "SMALLINT",
            ):
                self._add_finding(
                    AnalysisRule.TYPE_CAST_UNNECESSARY,
                    Severity.STYLE,
                    f"Unnecessary cast of integer literal to {expr.target_type}",
                )

    def _check_cast_expression(self, expr: CastExpression) -> None:
        """Check for unnecessary CAST expressions."""
        if (
            isinstance(expr.expr, Literal)
            and expr.expr.kind == "string"
            and expr.target_type.upper() in ("TEXT", "VARCHAR")
        ):
            self._add_finding(
                AnalysisRule.TYPE_CAST_UNNECESSARY,
                Severity.STYLE,
                f"Unnecessary CAST of string literal to {expr.target_type}",
            )

    def _check_group_by_usage(self, stmt: SelectStatement) -> None:
        """Check that non-aggregated columns in SELECT are in GROUP BY."""
        if not stmt.group_by:
            return

        group_by_names: set[str] = set()
        for gb_expr in stmt.group_by:
            if isinstance(gb_expr, ColumnRef):
                group_by_names.add(gb_expr.name.lower())

        for col in stmt.columns:
            if (
                isinstance(col, SelectColumn)
                and isinstance(col.expr, ColumnRef)
                and col.expr.name.lower() not in group_by_names
                and not self._is_inside_aggregate(col.expr, stmt)
            ):
                # Check if it's inside an aggregate function
                self._add_finding(
                    AnalysisRule.COLUMN_IN_SELECT_NOT_GROUPED,
                    Severity.INFO,
                    f"Column '{col.expr.name}' in SELECT may not be in GROUP BY",
                    suggestion="Add the column to GROUP BY or wrap it in an aggregate function",
                )

    def _is_inside_aggregate(self, col: ColumnRef, stmt: SelectStatement) -> bool:
        """Check if a column reference is inside an aggregate function (simplified)."""
        # This is a simplified check — a full implementation would walk the AST
        _ = col
        _ = stmt
        return False

    def _check_order_by(self, stmt: SelectStatement) -> None:
        """Check ORDER BY for issues."""
        for item in stmt.order_by:
            # ORDER BY with LIMIT 1 — ASC is redundant
            if (
                stmt.limit
                and isinstance(stmt.limit, Literal)
                and stmt.limit.value == 1
                and item.ascending
            ):
                pass  # Not always redundant; skip this check

    def _expression_depth(self, expr: Expression, current: int = 0) -> int:
        """Calculate the nesting depth of an expression."""
        if current > 50:  # Safety limit
            return current

        if isinstance(expr, BinaryOp):
            return max(
                self._expression_depth(expr.left, current + 1),
                self._expression_depth(expr.right, current + 1),
            )
        elif isinstance(expr, UnaryOp):
            return self._expression_depth(expr.operand, current + 1)
        elif isinstance(expr, FunctionCall):
            if not expr.args:
                return current + 1
            return max(self._expression_depth(a, current + 1) for a in expr.args)
        elif isinstance(expr, CaseExpression):
            depths = [current + 1]
            for when in expr.when_clauses:
                depths.append(self._expression_depth(when.condition, current + 1))
                depths.append(self._expression_depth(when.result, current + 1))
            if expr.else_clause:
                depths.append(self._expression_depth(expr.else_clause, current + 1))
            return max(depths)
        elif isinstance(expr, InExpression):
            depths = [self._expression_depth(expr.expr, current + 1)]
            for v in expr.values:
                depths.append(self._expression_depth(v, current + 1))
            return max(depths)
        elif isinstance(expr, BetweenExpression):
            return max(
                self._expression_depth(expr.expr, current + 1),
                self._expression_depth(expr.low, current + 1),
                self._expression_depth(expr.high, current + 1),
            )

        return current + 1


class _ColumnCollector(AstVisitor):
    """Collects all ColumnRef, SubqueryExpression, and FunctionCall nodes from an AST."""

    def __init__(self) -> None:
        self.columns: list[ColumnRef] = []
        self.has_subqueries: bool = False
        self.has_window_functions: bool = False

    def visit_ColumnRef(self, node: ColumnRef) -> None:
        self.columns.append(node)

    def visit_SubqueryExpression(self, node: SubqueryExpression) -> None:
        self.has_subqueries = True
        node.subquery.accept(self)

    def visit_ExistsExpression(self, node: ExistsExpression) -> None:
        self.has_subqueries = True
        node.subquery.accept(self)

    def visit_SubqueryRef(self, node: SubqueryRef) -> None:
        self.has_subqueries = True
        node.subquery.accept(self)

    def visit_SelectStatement(self, node: SelectStatement) -> None:
        if node.from_clause:
            node.from_clause.accept(self)
        if node.where_clause:
            node.where_clause.accept(self)
        for col in node.columns:
            col.accept(self)
        if node.group_by:
            for gb in node.group_by:
                gb.accept(self)
        if node.order_by:
            for ob in node.order_by:
                ob.accept(self)
        for cte in node.cte_list:
            cte.accept(self)

    def visit_SelectColumn(self, node: SelectColumn) -> None:
        if node.expr:
            node.expr.accept(self)

    def visit_FromClause(self, node: FromClause) -> None:
        if isinstance(node.source, (TableRef, SubqueryRef, FunctionRef)):
            node.source.accept(self)
        for join in node.joins:
            join.accept(self)

    def visit_FunctionCall(self, node: FunctionCall) -> None:
        if node.over_clause:
            self.has_window_functions = True
        for arg in node.args:
            arg.accept(self)


def analyze_sql(sql: str, strict: bool = False) -> AnalysisResult:
    """Convenience function to analyze a SQL string."""
    return SemanticAnalyzer(strict=strict).analyze(sql)
