"""Tests for sqlguard.linter module."""

import pytest
from sqlguard.linter import SQLLinter, LintIssue, LintRule, Severity


class TestSQLLinter:
    """Tests for SQL linter."""

    def setup_method(self):
        self.linter = SQLLinter()

    # --- SELECT * ---

    def test_select_star_detected(self):
        issues = self.linter.lint("SELECT * FROM users;")
        star_issues = [i for i in issues if i.rule == LintRule.SELECT_STAR]
        assert len(star_issues) >= 1

    def test_select_explicit_columns_ok(self):
        issues = self.linter.lint("SELECT id, name FROM users;")
        star_issues = [i for i in issues if i.rule == LintRule.SELECT_STAR]
        assert len(star_issues) == 0

    def test_select_count_star_ok(self):
        issues = self.linter.lint("SELECT COUNT(*) FROM users;")
        star_issues = [i for i in issues if i.rule == LintRule.SELECT_STAR]
        assert len(star_issues) == 0

    # --- DELETE without WHERE ---

    def test_delete_without_where(self):
        issues = self.linter.lint("DELETE FROM users;")
        delete_issues = [i for i in issues if i.rule == LintRule.MISSING_WHERE_DELETE]
        assert len(delete_issues) >= 1
        assert delete_issues[0].severity == Severity.ERROR

    def test_delete_with_where_ok(self):
        issues = self.linter.lint("DELETE FROM users WHERE id = 1;")
        delete_issues = [i for i in issues if i.rule == LintRule.MISSING_WHERE_DELETE]
        assert len(delete_issues) == 0

    # --- UPDATE without WHERE ---

    def test_update_without_where(self):
        issues = self.linter.lint("UPDATE users SET name = 'test';")
        update_issues = [i for i in issues if i.rule == LintRule.MISSING_WHERE_UPDATE]
        assert len(update_issues) >= 1
        assert update_issues[0].severity == Severity.ERROR

    def test_update_with_where_ok(self):
        issues = self.linter.lint("UPDATE users SET name = 'test' WHERE id = 1;")
        update_issues = [i for i in issues if i.rule == LintRule.MISSING_WHERE_UPDATE]
        assert len(update_issues) == 0

    # --- SQL injection ---

    def test_sql_injection_string_concat(self):
        issues = self.linter.lint("SELECT * FROM users WHERE id = " + "'1' + user_input")
        injection_issues = [i for i in issues if i.rule == LintRule.SQL_INJECTION_RISK]
        assert len(injection_issues) >= 1

    def test_sql_injection_f_string(self):
        issues = self.linter.lint("SELECT * FROM users WHERE name = f'{name}'")
        injection_issues = [i for i in issues if i.rule == LintRule.SQL_INJECTION_RISK]
        assert len(injection_issues) >= 1

    def test_sql_injection_format(self):
        issues = self.linter.lint("SELECT * FROM users WHERE name = '{}'.format(name)")
        injection_issues = [i for i in issues if i.rule == LintRule.SQL_INJECTION_RISK]
        assert len(injection_issues) >= 1

    def test_safe_parameterized_query(self):
        issues = self.linter.lint("SELECT * FROM users WHERE id = ?")
        injection_issues = [i for i in issues if i.rule == LintRule.SQL_INJECTION_RISK]
        assert len(injection_issues) == 0

    # --- TRUNCATE ---

    def test_truncate_detected(self):
        issues = self.linter.lint("TRUNCATE TABLE users;")
        truncate_issues = [i for i in issues if i.rule == LintRule.DANGEROUS_TRUNCATE]
        assert len(truncate_issues) >= 1

    # --- Implicit join ---

    def test_implicit_join(self):
        issues = self.linter.lint("SELECT * FROM users, posts WHERE users.id = posts.user_id;")
        implicit_issues = [i for i in issues if i.rule == LintRule.IMPLICIT_JOIN]
        assert len(implicit_issues) >= 1

    def test_explicit_join_ok(self):
        issues = self.linter.lint("SELECT * FROM users JOIN posts ON users.id = posts.user_id;")
        implicit_issues = [i for i in issues if i.rule == LintRule.IMPLICIT_JOIN]
        assert len(implicit_issues) == 0

    # --- LIKE with leading wildcard ---

    def test_like_leading_wildcard(self):
        issues = self.linter.lint("SELECT * FROM users WHERE name LIKE '%son';")
        like_issues = [i for i in issues if i.rule == LintRule.LIKE_PREFIX_WILDCARD]
        assert len(like_issues) >= 1

    def test_like_trailing_wildcard_ok(self):
        issues = self.linter.lint("SELECT * FROM users WHERE name LIKE 'son%';")
        like_issues = [i for i in issues if i.rule == LintRule.LIKE_PREFIX_WILDCARD]
        assert len(like_issues) == 0

    # --- CROSS JOIN ---

    def test_cross_join(self):
        issues = self.linter.lint("SELECT * FROM users CROSS JOIN posts;")
        cross_issues = [i for i in issues if i.rule == LintRule.CARTESIAN_JOIN]
        assert len(cross_issues) >= 1

    # --- Function on indexed column ---

    def test_function_on_column_in_where(self):
        issues = self.linter.lint("SELECT * FROM users WHERE LOWER(name) = 'john';")
        func_issues = [i for i in issues if i.rule == LintRule.FUNCTION_ON_INDEXED_COL]
        assert len(func_issues) >= 1

    def test_direct_comparison_ok(self):
        issues = self.linter.lint("SELECT * FROM users WHERE name = LOWER('JOHN');")
        func_issues = [i for i in issues if i.rule == LintRule.FUNCTION_ON_INDEXED_COL]
        assert len(func_issues) == 0

    # --- INSERT without column list ---

    def test_insert_without_columns(self):
        issues = self.linter.lint("INSERT INTO users VALUES (1, 'John');")
        insert_issues = [i for i in issues if i.rule == LintRule.EXPLICIT_COLUMN_LIST]
        assert len(insert_issues) >= 1

    def test_insert_with_columns_ok(self):
        issues = self.linter.lint("INSERT INTO users (id, name) VALUES (1, 'John');")
        insert_issues = [i for i in issues if i.rule == LintRule.EXPLICIT_COLUMN_LIST]
        assert len(insert_issues) == 0

    # --- Ordinal ORDER BY ---

    def test_ordinal_order_by(self):
        issues = self.linter.lint("SELECT id, name FROM users ORDER BY 1, 2;")
        ordinal_issues = [i for i in issues if i.rule == LintRule.ORDINAL_POSITION_ORDER_BY]
        assert len(ordinal_issues) >= 1

    # --- Semicolon (strict mode) ---

    def test_missing_semicolon_strict(self):
        linter = SQLLinter(strict=True)
        issues = linter.lint("SELECT id FROM users")
        semi_issues = [i for i in issues if i.rule == LintRule.SEMICOLON_MISSING]
        assert len(semi_issues) >= 1

    def test_missing_semicolon_not_strict(self):
        issues = self.linter.lint("SELECT id FROM users")
        semi_issues = [i for i in issues if i.rule == LintRule.SEMICOLON_MISSING]
        assert len(semi_issues) == 0

    # --- Ignore rules ---

    def test_ignore_rules(self):
        linter = SQLLinter(ignore_rules=[LintRule.SELECT_STAR])
        issues = linter.lint("SELECT * FROM users;")
        star_issues = [i for i in issues if i.rule == LintRule.SELECT_STAR]
        assert len(star_issues) == 0

    # --- Only rules ---

    def test_only_rules(self):
        linter = SQLLinter(only_rules=[LintRule.SELECT_STAR])
        issues = linter.lint("SELECT * FROM users;")
        assert all(i.rule == LintRule.SELECT_STAR for i in issues)

    # --- LintIssue ---

    def test_lint_issue_str(self):
        issue = LintIssue(
            rule=LintRule.SELECT_STAR,
            severity=Severity.WARNING,
            message="SELECT * used",
            line=3,
            suggestion="List columns explicitly",
        )
        s = str(issue)
        assert "[warning]" in s
        assert "select_star" in s
        assert "line 3" in s

    def test_lint_issue_to_dict(self):
        issue = LintIssue(
            rule=LintRule.SELECT_STAR,
            severity=Severity.WARNING,
            message="SELECT * used",
            line=1,
        )
        d = issue.to_dict()
        assert d["rule"] == "select_star"
        assert d["severity"] == "warning"
        assert d["message"] == "SELECT * used"

    # --- Multiple issues ---

    def test_multiple_issues(self):
        sql = "SELECT * FROM users, posts DELETE FROM users;"
        issues = self.linter.lint(sql)
        rules = {i.rule for i in issues}
        assert LintRule.SELECT_STAR in rules
        # Implicit join or other rules may also fire

    # --- Clean query ---

    def test_clean_query(self):
        sql = "SELECT id, name FROM users WHERE active = true ORDER BY name;"
        issues = self.linter.lint(sql)
        assert len(issues) == 0 or all(
            i.rule not in (
                LintRule.SELECT_STAR,
                LintRule.MISSING_WHERE_DELETE,
                LintRule.MISSING_WHERE_UPDATE,
                LintRule.SQL_INJECTION_RISK,
                LintRule.DANGEROUS_TRUNCATE,
                LintRule.IMPLICIT_JOIN,
            )
            for i in issues
        )
