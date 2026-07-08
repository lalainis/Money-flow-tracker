-- Rollback script for 20260708_add_performance_indexes.sql.
-- Drops only indexes introduced by that script.

DROP INDEX IF EXISTS ix_member_list_no;
DROP INDEX IF EXISTS ix_member_role;

DROP INDEX IF EXISTS ix_auth_token_member_id;
DROP INDEX IF EXISTS ix_auth_token_expires_at;

DROP INDEX IF EXISTS ix_member_season_fee_season_label;

DROP INDEX IF EXISTS ix_period_season_label;
DROP INDEX IF EXISTS ix_period_active;

DROP INDEX IF EXISTS ix_income_income_type;
DROP INDEX IF EXISTS ix_income_member_id;
DROP INDEX IF EXISTS ix_income_entry_date;

DROP INDEX IF EXISTS ix_expense_category;
DROP INDEX IF EXISTS ix_expense_entry_date;
DROP INDEX IF EXISTS ix_expense_created_by_member_id;

DROP INDEX IF EXISTS ix_audit_log_season_label;
DROP INDEX IF EXISTS ix_audit_log_changed_by_member_id;
DROP INDEX IF EXISTS ix_audit_log_changed_at;
