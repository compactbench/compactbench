# 03. Database Schema List

## 1. Database choice

Use **PostgreSQL** as the primary relational database.

Use:
- `uuid` primary keys
- `jsonb` for structured benchmark/method/scoring payloads
- UTC timestamps
- soft delete only where necessary
- immutable version rows for benchmark/scoring artifacts

Do not store large raw transcripts directly in hot tables if they will frequently exceed practical row size. Store large bodies in object storage and keep metadata/refs in DB.

## 2. Global conventions

Common columns for most tables:
- `id uuid pk`
- `created_at timestamptz not null`
- `updated_at timestamptz not null`

Recommended shared patterns:
- `status` for lifecycle
- `version` or `version_label` where mutability matters
- `metadata jsonb` for extensible non-critical data
- unique partial indexes where publication/ownership constraints require them

## 3. Identity and access domain

## 3.1 `users`
Purpose:
- platform user record

Columns:
- `id`
- `email` (unique)
- `display_name`
- `avatar_url nullable`
- `auth_provider` (`internal`, `google`, `github`, etc.)
- `auth_provider_user_id nullable`
- `email_verified_at nullable`
- `status` (`active`, `suspended`, `pending`)
- `default_team_id nullable`
- `last_seen_at nullable`
- `created_at`
- `updated_at`

Indexes:
- unique on `email`
- index on `auth_provider, auth_provider_user_id`

## 3.2 `teams`
Purpose:
- billing and ownership boundary

Columns:
- `id`
- `name`
- `slug` (unique)
- `owner_user_id`
- `plan_code`
- `status` (`active`, `past_due`, `suspended`)
- `settings jsonb`
- `created_at`
- `updated_at`

Indexes:
- unique on `slug`
- index on `owner_user_id`

## 3.3 `team_members`
Purpose:
- membership mapping

Columns:
- `id`
- `team_id`
- `user_id`
- `role` (`owner`, `admin`, `member`, `viewer`)
- `joined_at`
- `invited_by_user_id nullable`
- `status` (`active`, `invited`, `revoked`)

Indexes:
- unique on `team_id, user_id`
- index on `user_id`

## 3.4 `team_invites`
Purpose:
- invite workflow

Columns:
- `id`
- `team_id`
- `email`
- `role`
- `invite_token_hash`
- `expires_at`
- `accepted_at nullable`
- `revoked_at nullable`
- `created_by_user_id`
- `created_at`

Indexes:
- unique on `team_id, email, accepted_at is null` (implemented as partial unique)
- index on `expires_at`

## 4. Project and billing domain

## 4.1 `projects`
Purpose:
- main organizational container

Columns:
- `id`
- `team_id`
- `name`
- `slug`
- `description nullable`
- `visibility` (`private`, `team`, `public`)
- `status` (`active`, `archived`)
- `settings jsonb`
- `created_by_user_id`
- `created_at`
- `updated_at`

Indexes:
- unique on `team_id, slug`
- index on `team_id`

## 4.2 `billing_accounts`
Purpose:
- Stripe or billing provider linkage

Columns:
- `id`
- `team_id`
- `provider` (`stripe`)
- `provider_customer_id`
- `provider_subscription_id nullable`
- `plan_code`
- `billing_status`
- `current_period_end nullable`
- `metadata jsonb`
- `created_at`
- `updated_at`

Indexes:
- unique on `provider, provider_customer_id`
- unique on `team_id`

## 4.3 `usage_ledger`
Purpose:
- run and quota accounting

Columns:
- `id`
- `team_id`
- `project_id nullable`
- `usage_type` (`run_created`, `case_executed`, `model_tokens`, `export_generated`, etc.)
- `quantity numeric`
- `unit`
- `reference_type`
- `reference_id`
- `occurred_at`
- `metadata jsonb`

Indexes:
- index on `team_id, occurred_at`
- index on `reference_type, reference_id`

## 5. Benchmark catalog domain

## 5.1 `benchmark_suites`
Purpose:
- top-level suite catalog

Columns:
- `id`
- `suite_key` (stable machine key)
- `name`
- `description`
- `category`
- `difficulty` (`easy`, `medium`, `hard`, `elite`)
- `visibility` (`public`, `private`, `hidden_ranked`, `internal_shadow`)
- `status` (`draft`, `active`, `retired`)
- `default_case_count`
- `settings jsonb`
- `created_at`
- `updated_at`

Indexes:
- unique on `suite_key`

## 5.2 `benchmark_suite_versions`
Purpose:
- immutable suite versions

Columns:
- `id`
- `benchmark_suite_id`
- `version_label`
- `status` (`draft`, `published`, `retired`)
- `generation_policy jsonb`
- `scoring_profile_id`
- `leaderboard_eligible boolean`
- `published_at nullable`
- `created_at`

Indexes:
- unique on `benchmark_suite_id, version_label`
- index on `benchmark_suite_id, status`

## 5.3 `benchmark_templates`
Purpose:
- template identity row

Columns:
- `id`
- `template_key`
- `family` (`decision_override`, `entity_confusion`, etc.)
- `name`
- `description`
- `visibility`
- `status`
- `created_at`
- `updated_at`

Indexes:
- unique on `template_key`
- index on `family`

## 5.4 `benchmark_template_versions`
Purpose:
- immutable template definitions

Columns:
- `id`
- `benchmark_template_id`
- `version_label`
- `definition jsonb`
- `variable_schema jsonb`
- `generation_policy jsonb`
- `difficulty_policy jsonb`
- `is_hidden boolean`
- `created_at`
- `published_at nullable`

Indexes:
- unique on `benchmark_template_id, version_label`
- index on `is_hidden`

## 5.5 `suite_template_assignments`
Purpose:
- composition of suite versions from template versions

Columns:
- `id`
- `benchmark_suite_version_id`
- `benchmark_template_version_id`
- `weight numeric`
- `min_count nullable`
- `max_count nullable`
- `settings jsonb`

Indexes:
- unique on `benchmark_suite_version_id, benchmark_template_version_id`
- index on `benchmark_suite_version_id`

## 5.6 `seed_sets`
Purpose:
- reproducible run seed groups

Columns:
- `id`
- `benchmark_suite_version_id`
- `seed_group_key`
- `seed_values jsonb`
- `status` (`active`, `retired`)
- `created_at`

Indexes:
- unique on `benchmark_suite_version_id, seed_group_key`

## 6. Method configuration domain

## 6.1 `compaction_methods`
Purpose:
- user-owned methods

Columns:
- `id`
- `project_id`
- `name`
- `slug`
- `method_type` (`built_in`, `external_callback`)
- `version_label`
- `description nullable`
- `is_public boolean`
- `publication_status` (`private`, `queued`, `published`, `rejected`)
- `config jsonb`
- `built_in_key nullable`
- `endpoint_url nullable`
- `timeout_ms nullable`
- `created_by_user_id`
- `created_at`
- `updated_at`

Indexes:
- unique on `project_id, slug`
- index on `project_id`
- index on `method_type`

## 6.2 `compaction_method_secrets`
Purpose:
- encrypted secret material for callback auth

Columns:
- `id`
- `compaction_method_id`
- `secret_type` (`bearer_token`, `signature_secret`, etc.)
- `encrypted_value`
- `key_version`
- `created_at`
- `rotated_at nullable`

Indexes:
- unique on `compaction_method_id, secret_type`

## 6.3 `compaction_method_verifications`
Purpose:
- endpoint verification and health history

Columns:
- `id`
- `compaction_method_id`
- `verification_type` (`ping`, `dry_run`, `schema_check`)
- `status` (`passed`, `failed`)
- `status_code nullable`
- `latency_ms nullable`
- `error_summary nullable`
- `verified_at`
- `details jsonb`

Indexes:
- index on `compaction_method_id, verified_at desc`

## 6.4 `callback_invocations`
Purpose:
- detailed callback execution log

Columns:
- `id`
- `compaction_method_id`
- `run_case_cycle_id`
- `request_artifact_id`
- `response_artifact_id nullable`
- `status`
- `status_code nullable`
- `latency_ms nullable`
- `error_code nullable`
- `error_summary nullable`
- `invoked_at`

Indexes:
- index on `compaction_method_id, invoked_at desc`
- index on `run_case_cycle_id`

## 7. Experiment execution domain

## 7.1 `experiment_runs`
Purpose:
- top-level run metadata

Columns:
- `id`
- `project_id`
- `benchmark_suite_version_id`
- `seed_set_id`
- `compaction_method_id`
- `target_model_key`
- `target_model_version nullable`
- `execution_mode` (`full_context`, `compacted_only`, `compacted_plus_recent`)
- `drift_cycle_count`
- `status` (`queued`, `running`, `partial_failed`, `completed`, `failed`, `cancelled`)
- `leaderboard_submission_requested boolean`
- `leaderboard_status` (`not_requested`, `pending`, `eligible`, `published`, `rejected`)
- `requested_by_user_id`
- `started_at nullable`
- `completed_at nullable`
- `summary jsonb`
- `created_at`
- `updated_at`

Indexes:
- index on `project_id, created_at desc`
- index on `status`
- index on `leaderboard_status`

## 7.2 `run_cases`
Purpose:
- one row per run x generated case

Columns:
- `id`
- `experiment_run_id`
- `case_slot`
- `benchmark_template_version_id`
- `seed_value`
- `test_case_artifact_id`
- `ground_truth_artifact_id`
- `status`
- `aggregate_score numeric nullable`
- `failure_reason nullable`
- `created_at`
- `updated_at`

Indexes:
- unique on `experiment_run_id, case_slot`
- index on `experiment_run_id`

## 7.3 `run_case_cycles`
Purpose:
- one row per case x cycle

Columns:
- `id`
- `run_case_id`
- `cycle_number`
- `status`
- `baseline_context_artifact_id nullable`
- `compaction_artifact_id nullable`
- `model_response_artifact_id nullable`
- `scorecard_id nullable`
- `latency_ms nullable`
- `cost_estimate_usd nullable`
- `created_at`
- `updated_at`

Indexes:
- unique on `run_case_id, cycle_number`
- index on `run_case_id`

## 7.4 `job_attempts`
Purpose:
- execution observability and retry history

Columns:
- `id`
- `job_type`
- `reference_type`
- `reference_id`
- `attempt_number`
- `worker_key`
- `status`
- `started_at`
- `finished_at nullable`
- `error_code nullable`
- `error_summary nullable`
- `details jsonb`

Indexes:
- index on `reference_type, reference_id`
- index on `job_type, started_at desc`

## 8. Evaluation and scoring domain

## 8.1 `evaluation_profiles`
Purpose:
- scorer config identity

Columns:
- `id`
- `profile_key`
- `name`
- `description`
- `version_label`
- `definition jsonb`
- `status`
- `created_at`
- `published_at nullable`

Indexes:
- unique on `profile_key, version_label`

## 8.2 `evaluation_items`
Purpose:
- generated prompt/task definitions per case

Columns:
- `id`
- `run_case_id`
- `cycle_number`
- `item_key`
- `item_type` (`fact_recall`, `constraint_recall`, `planning`, etc.)
- `prompt_artifact_id`
- `expected_definition jsonb`
- `created_at`

Indexes:
- index on `run_case_id, cycle_number`
- unique on `run_case_id, cycle_number, item_key`

## 8.3 `evaluation_results`
Purpose:
- one row per evaluated item

Columns:
- `id`
- `run_case_cycle_id`
- `evaluation_item_id`
- `response_artifact_id`
- `passed boolean`
- `score numeric`
- `check_type`
- `details jsonb`
- `latency_ms nullable`
- `created_at`

Indexes:
- index on `run_case_cycle_id`
- index on `evaluation_item_id`

## 8.4 `scorecards`
Purpose:
- aggregated case-cycle scores

Columns:
- `id`
- `run_case_cycle_id`
- `metrics jsonb`
- `overall_score numeric`
- `contradiction_rate numeric`
- `compression_ratio numeric`
- `drift_delta nullable`
- `created_at`

Indexes:
- unique on `run_case_cycle_id`

## 8.5 `run_scorecards`
Purpose:
- run-level aggregate results

Columns:
- `id`
- `experiment_run_id`
- `metrics jsonb`
- `overall_score numeric`
- `leaderboard_projection jsonb`
- `created_at`

Indexes:
- unique on `experiment_run_id`

## 9. Leaderboard domain

## 9.1 `leaderboard_versions`
Purpose:
- versioned ranking spaces

Columns:
- `id`
- `version_key`
- `name`
- `benchmark_suite_version_id`
- `evaluation_profile_id`
- `target_model_key`
- `ranking_policy jsonb`
- `status` (`active`, `retired`)
- `published_at`

Indexes:
- unique on `version_key`

## 9.2 `leaderboard_entries`
Purpose:
- public published rows

Columns:
- `id`
- `leaderboard_version_id`
- `experiment_run_id`
- `compaction_method_id`
- `published_method_name`
- `published_team_name nullable`
- `rank integer nullable`
- `overall_score numeric`
- `elite_score numeric`
- `drift_score numeric`
- `constraint_retention numeric`
- `contradiction_rate numeric`
- `compression_ratio numeric`
- `publication_status`
- `published_at nullable`
- `snapshot jsonb`

Indexes:
- unique on `leaderboard_version_id, experiment_run_id`
- index on `leaderboard_version_id, publication_status, rank`

## 9.3 `leaderboard_audit_events`
Purpose:
- moderation and publication trace

Columns:
- `id`
- `leaderboard_entry_id`
- `event_type`
- `actor_user_id nullable`
- `details jsonb`
- `created_at`

Indexes:
- index on `leaderboard_entry_id`

## 10. Artifact and export domain

## 10.1 `artifacts`
Purpose:
- storage indirection for large bodies

Columns:
- `id`
- `owner_type`
- `owner_id`
- `artifact_type`
- `storage_provider`
- `storage_key`
- `content_hash`
- `content_type`
- `byte_size`
- `is_encrypted boolean`
- `metadata jsonb`
- `created_at`

Indexes:
- index on `owner_type, owner_id`
- unique on `content_hash, storage_key`

## 10.2 `exports`
Purpose:
- generated user-facing reports

Columns:
- `id`
- `experiment_run_id`
- `requested_by_user_id`
- `export_type` (`pdf`, `csv`, `json`)
- `artifact_id`
- `status`
- `created_at`
- `completed_at nullable`

Indexes:
- index on `experiment_run_id`
- index on `requested_by_user_id, created_at desc`

## 11. Audit and admin domain

## 11.1 `audit_logs`
Purpose:
- security and traceability

Columns:
- `id`
- `actor_user_id nullable`
- `team_id nullable`
- `project_id nullable`
- `action`
- `target_type`
- `target_id`
- `ip_address nullable`
- `user_agent nullable`
- `details jsonb`
- `created_at`

Indexes:
- index on `actor_user_id, created_at desc`
- index on `team_id, created_at desc`
- index on `target_type, target_id`

## 11.2 `provider_configs`
Purpose:
- internal provider/model config

Columns:
- `id`
- `provider_key`
- `model_key`
- `status`
- `settings jsonb`
- `rate_limit_policy jsonb`
- `created_at`
- `updated_at`

Indexes:
- unique on `provider_key, model_key`

## 12. Recommended enum catalog

Use either Postgres enums or application-enforced string enums. Keep them centralized.

Key enums:
- team role
- project visibility
- benchmark visibility
- difficulty
- method type
- run status
- leaderboard status
- artifact type
- evaluation item type
- export type

## 13. Retention policy

Do not keep everything forever.

Recommended baseline:
- raw hidden-case artifacts: retain long enough for audit and replay, then archive
- raw model responses: retain according to plan and privacy policy
- leaderboard snapshots: retain permanently
- audit logs: retain permanently or per compliance window
- callback invocation bodies: retain sanitized versions if secrets present

## 14. Final schema verdict

The schema should optimize for four things:

1. strict reproducibility
2. benchmark/method/version traceability
3. artifact indirection for large payloads
4. leaderboard auditability

Do not collapse benchmark, run, score, and publication state into a handful of oversized generic tables. That will become unmaintainable quickly.
