-- Adds indexes for frequent filters/sorts on auth, history, and audit queries.
-- Safe to run multiple times.

CREATE INDEX IF NOT EXISTS ix_member_list_no ON member (list_no);
CREATE INDEX IF NOT EXISTS ix_member_role ON member (role);

CREATE INDEX IF NOT EXISTS ix_auth_token_member_id ON auth_token (member_id);
CREATE INDEX IF NOT EXISTS ix_auth_token_expires_at ON auth_token (expires_at);

CREATE INDEX IF NOT EXISTS ix_member_season_fee_season_label ON member_season_fee (season_label);

CREATE INDEX IF NOT EXISTS ix_period_season_label ON period (season_label);
CREATE INDEX IF NOT EXISTS ix_period_active ON period (active);

CREATE INDEX IF NOT EXISTS ix_income_income_type ON income (income_type);
CREATE INDEX IF NOT EXISTS ix_income_member_id ON income (member_id);
CREATE INDEX IF NOT EXISTS ix_income_entry_date ON income (entry_date);

CREATE INDEX IF NOT EXISTS ix_expense_category ON expense (category);
CREATE INDEX IF NOT EXISTS ix_expense_entry_date ON expense (entry_date);
CREATE INDEX IF NOT EXISTS ix_expense_created_by_member_id ON expense (created_by_member_id);

CREATE INDEX IF NOT EXISTS ix_audit_log_season_label ON audit_log (season_label);
CREATE INDEX IF NOT EXISTS ix_audit_log_changed_by_member_id ON audit_log (changed_by_member_id);
CREATE INDEX IF NOT EXISTS ix_audit_log_changed_at ON audit_log (changed_at);
