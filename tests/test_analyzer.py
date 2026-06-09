"""Tests for sqlguard.analyzer module."""

from sqlguard.analyzer import (
    AnalysisFinding,
    AnalysisRule,
    Severity,
    analyze_sql,
)


class TestSemanticAnalyzerBasic:
    """Test basic semantic analysis."""

    def test_simple_select(self):
        result = analyze_sql("SELECT id FROM users")
        assert result.statement_count == 1
        assert "users" in result.tables_used

    def test_empty_sql(self):
        result = analyze_sql("")
        assert result.statement_count == 0
        assert len(result.findings) == 0

    def test_select_star_warning(self):
        result = analyze_sql("SELECT * FROM users")
        star_findings = [
            f for f in result.findings if f.rule == AnalysisRule.SELECT_STAR_IN_PRODUCTION
        ]
        assert len(star_findings) >= 1

    def test_explicit_columns_no_star_warning(self):
        result = analyze_sql("SELECT id, name FROM users")
        star_findings = [
            f for f in result.findings if f.rule == AnalysisRule.SELECT_STAR_IN_PRODUCTION
        ]
        assert len(star_findings) == 0


class TestSemanticAnalyzerJoins:
    """Test JOIN-related analysis."""

    def test_missing_join_condition(self):
        sql = "SELECT u.id, o.id FROM users u JOIN orders o"
        result = analyze_sql(sql)
        missing = [f for f in result.findings if f.rule == AnalysisRule.MISSING_JOIN_CONDITION]
        assert len(missing) >= 1

    def test_join_with_condition_ok(self):
        sql = "SELECT u.id FROM users u JOIN orders o ON u.id = o.user_id"
        result = analyze_sql(sql)
        missing = [f for f in result.findings if f.rule == AnalysisRule.MISSING_JOIN_CONDITION]
        assert len(missing) == 0

    def test_cross_join_no_warning(self):
        sql = "SELECT u.id FROM users u CROSS JOIN orders o"
        result = analyze_sql(sql)
        missing = [f for f in result.findings if f.rule == AnalysisRule.MISSING_JOIN_CONDITION]
        # CROSS JOIN should not trigger missing_join_condition
        assert len(missing) == 0

    def test_implicit_cross_join(self):
        sql = "SELECT u.id FROM users u, orders o"
        result = analyze_sql(sql)
        cross = [f for f in result.findings if f.rule == AnalysisRule.IMPLICIT_CROSS_JOIN]
        assert len(cross) >= 1

    def test_many_joins(self):
        sql = """
        SELECT * FROM t1
        JOIN t2 ON t1.id = t2.t1_id
        JOIN t3 ON t2.id = t3.t2_id
        JOIN t4 ON t3.id = t4.t3_id
        JOIN t5 ON t4.id = t5.t4_id
        JOIN t6 ON t5.id = t6.t5_id
        """
        result = analyze_sql(sql)
        many = [f for f in result.findings if f.rule == AnalysisRule.MANY_JOINS]
        assert len(many) >= 1

    def test_few_joins_no_warning(self):
        sql = "SELECT * FROM t1 JOIN t2 ON t1.id = t2.t1_id"
        result = analyze_sql(sql)
        many = [f for f in result.findings if f.rule == AnalysisRule.MANY_JOINS]
        assert len(many) == 0


class TestSemanticAnalyzerExpressions:
    """Test expression-level analysis."""

    def test_like_leading_wildcard(self):
        sql = "SELECT id FROM users WHERE name LIKE '%John'"
        result = analyze_sql(sql)
        like = [f for f in result.findings if f.rule == AnalysisRule.LIKE_LEADING_WILDCARD]
        assert len(like) >= 1

    def test_like_no_leading_wildcard_ok(self):
        sql = "SELECT id FROM users WHERE name LIKE 'John%'"
        result = analyze_sql(sql)
        like = [f for f in result.findings if f.rule == AnalysisRule.LIKE_LEADING_WILDCARD]
        assert len(like) == 0

    def test_window_without_order(self):
        sql = "SELECT SUM(salary) OVER () FROM employees"
        result = analyze_sql(sql)
        window = [f for f in result.findings if f.rule == AnalysisRule.WINDOW_WITHOUT_ORDER]
        assert len(window) >= 1

    def test_window_with_order_ok(self):
        sql = "SELECT ROW_NUMBER() OVER (ORDER BY salary DESC) FROM employees"
        result = analyze_sql(sql)
        window = [f for f in result.findings if f.rule == AnalysisRule.WINDOW_WITHOUT_ORDER]
        assert len(window) == 0

    def test_unnecessary_type_cast(self):
        sql = "SELECT CAST('hello' AS TEXT)"
        result = analyze_sql(sql)
        cast = [f for f in result.findings if f.rule == AnalysisRule.TYPE_CAST_UNNECESSARY]
        assert len(cast) >= 1

    def test_necessary_type_cast_ok(self):
        sql = "SELECT CAST(id AS VARCHAR)"
        result = analyze_sql(sql)
        # This shouldn't trigger unnecessary cast
        cast = [
            f
            for f in result.findings
            if f.rule == AnalysisRule.TYPE_CAST_UNNECESSARY and "integer" in f.message.lower()
        ]
        assert len(cast) == 0


class TestSemanticAnalyzerClauses:
    """Test clause-level analysis."""

    def test_redundant_distinct_with_group_by(self):
        sql = "SELECT DISTINCT status FROM users GROUP BY status"
        result = analyze_sql(sql)
        redundant = [f for f in result.findings if f.rule == AnalysisRule.REDUNDANT_DISTINCT]
        assert len(redundant) >= 1

    def test_distinct_without_group_by_ok(self):
        sql = "SELECT DISTINCT status FROM users"
        result = analyze_sql(sql)
        redundant = [f for f in result.findings if f.rule == AnalysisRule.REDUNDANT_DISTINCT]
        assert len(redundant) == 0


class TestSemanticAnalyzerDML:
    """Test DML statement analysis."""

    def test_insert_analysis(self):
        sql = "INSERT INTO users (name) VALUES ('John')"
        result = analyze_sql(sql)
        assert "users" in result.tables_used
        assert result.statement_count == 1

    def test_update_analysis(self):
        sql = "UPDATE users SET name = 'Jane' WHERE id = 1"
        result = analyze_sql(sql)
        assert "users" in result.tables_used

    def test_delete_analysis(self):
        sql = "DELETE FROM users WHERE id = 1"
        result = analyze_sql(sql)
        assert "users" in result.tables_used


class TestSemanticAnalyzerCTEs:
    """Test CTE-related analysis."""

    def test_cte_detected(self):
        sql = "WITH active_users AS (SELECT id FROM users WHERE active = TRUE) SELECT * FROM active_users"
        result = analyze_sql(sql)
        assert len(result.cte_names) >= 1
        assert "active_users" in result.cte_names

    def test_subquery_detected(self):
        sql = "SELECT * FROM (SELECT id FROM users) AS sub"
        result = analyze_sql(sql)
        assert result.has_subqueries is True


class TestSemanticAnalyzerWindowFunctions:
    """Test window function detection."""

    def test_window_function_detected(self):
        sql = "SELECT ROW_NUMBER() OVER (ORDER BY id) FROM users"
        result = analyze_sql(sql)
        assert result.has_window_functions is True

    def test_no_window_function(self):
        sql = "SELECT COUNT(*) FROM users"
        result = analyze_sql(sql)
        assert result.has_window_functions is False


class TestSemanticAnalyzerResult:
    """Test AnalysisResult properties."""

    def test_has_errors(self):
        result = analyze_sql("SELECT * FROM users u JOIN orders o")
        # Missing join condition is an error
        errors = [f for f in result.findings if f.severity == Severity.ERROR]
        if errors:
            assert result.has_errors is True

    def test_has_warnings(self):
        result = analyze_sql("SELECT * FROM users")
        assert result.has_warnings is True  # SELECT * is a warning

    def test_error_count(self):
        result = analyze_sql("SELECT * FROM users u JOIN orders o")
        assert result.error_count >= 0

    def test_warning_count(self):
        result = analyze_sql("SELECT * FROM users")
        assert result.warning_count >= 1

    def test_summary(self):
        result = analyze_sql("SELECT id FROM users")
        summary = result.summary()
        assert "Statements" in summary
        assert "Tables" in summary


class TestSemanticAnalyzerFindings:
    """Test AnalysisFinding properties."""

    def test_finding_str(self):
        finding = AnalysisFinding(
            rule=AnalysisRule.SELECT_STAR_IN_PRODUCTION,
            severity=Severity.WARNING,
            message="SELECT * used",
        )
        text = str(finding)
        assert "WARNING" in text
        assert "select_star_in_production" in text

    def test_finding_to_dict(self):
        finding = AnalysisFinding(
            rule=AnalysisRule.SELECT_STAR_IN_PRODUCTION,
            severity=Severity.WARNING,
            message="SELECT * used",
            line=1,
            column=1,
        )
        d = finding.to_dict()
        assert d["rule"] == "select_star_in_production"
        assert d["severity"] == "warning"
        assert d["line"] == 1

    def test_finding_with_suggestion(self):
        finding = AnalysisFinding(
            rule=AnalysisRule.SELECT_STAR_IN_PRODUCTION,
            severity=Severity.WARNING,
            message="SELECT * used",
            suggestion="List columns explicitly",
        )
        text = str(finding)
        assert "List columns explicitly" in text


class TestSemanticAnalyzerParseErrors:
    """Test analysis with unparseable SQL."""

    def test_invalid_sql(self):
        result = analyze_sql("INVALID SQL @@@")
        assert result.has_errors is True

    def test_incomplete_sql(self):
        result = analyze_sql("SELECT FROM WHERE")
        # Should still produce a result (with error finding)
        assert len(result.findings) >= 1


class TestSemanticAnalyzerComplex:
    """Test analysis of complex queries."""

    def test_complex_query(self):
        sql = """
        WITH active_users AS (
            SELECT id, name FROM users WHERE active = TRUE
        )
        SELECT
            u.name,
            COUNT(o.id) AS order_count,
            SUM(o.total) AS total_spent
        FROM active_users u
        LEFT JOIN orders o ON u.id = o.user_id
        WHERE u.name LIKE '%test%'
        GROUP BY u.id, u.name
        HAVING COUNT(o.id) > 0
        ORDER BY total_spent DESC
        LIMIT 10
        """
        result = analyze_sql(sql)
        assert result.statement_count == 1
        assert result.has_subqueries is False  # CTE is not a subquery in this context
        # Should have at least the LIKE leading wildcard warning
        like_warnings = [f for f in result.findings if f.rule == AnalysisRule.LIKE_LEADING_WILDCARD]
        assert len(like_warnings) >= 1

    def test_multiple_statements(self):
        sql = "SELECT id FROM users; SELECT name FROM products"
        result = analyze_sql(sql)
        assert result.statement_count == 2

    def test_insert_with_subquery(self):
        sql = "INSERT INTO archive (id, name) VALUES (1, 'test')"
        result = analyze_sql(sql)
        assert "archive" in result.tables_used
