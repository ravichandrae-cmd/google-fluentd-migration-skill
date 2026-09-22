---
name: google-fluentd-migration-skill
description: Agent skill that orchestrates the end-to-end migration lifecycle from google-fluentd to OSS Fluentd with shared context persistence, two approval gates, and deep v1 syntax modernization.
---
# Google Fluentd to OSS Fluentd Migration Skill

## Agent-Driven Orchestration Architecture

This skill provides an **agent-driven, state-machine migration workflow** that eliminates manual per-stage script execution while strictly enforcing safety boundaries and approval gates.

```
+-------------------------------------------------------------------------+
| User: Inputs Target VM once (VM Name, GCP Project, Zone)                |
+-------------------------------------------------------------------------+
                                     │
                                     ▼
+-------------------------------------------------------------------------+
| PHASE 1: Automated Pre-Flight Pipeline (Stages 1 - 4)                   |
|   • Stage 1 (Discovery): Inspects remote VM, services, users, paths     |
|   • Stage 2 (Assessment): Analyzes AST, plugins, compatibility items    |
|   • Stage 3 (Generation): Converts configs to v1, isolates proprietary  |
|   • Stage 4 (Validation): Validates behavior, runs remote dry-run       |
|   • Context State: Persists discovered runtime into migration_context   |
+-------------------------------------------------------------------------+
                                     │
                                     ▼
         🛑 APPROVAL GATE 1: Compatibility Review & Scope Approval
         (Agent presents discovered apps, compatibility findings,
          and awaits user approval on scope)
                                     │
                             [User Approves Scope]
                                     ▼
+-------------------------------------------------------------------------+
| Internal Scoped Preparation & Live Validation (Between Gate 1 & Gate 2) |
|   • Generates minimal known-good master config (@include conf.d/*.conf) |
|   • Executes non-intrusive remote fluentd --dry-run validation          |
|   • Builds 6-step cutover execution plan, diffs, and canary payload     |
+-------------------------------------------------------------------------+
                                     │
                                     ▼
         🛑 APPROVAL GATE 2: Live Cutover Authorization Gate
         (Agent presents planned 6-step actions, config diff,
          dry-run proof, rollback snapshot, and awaits explicit approval)
                                     │
                           [User Approves Cutover]
                                     ▼
+-------------------------------------------------------------------------+
| PHASE 3: Stage 5 Controlled Cutover & Verification                      |
|   • Step 1: Pre-cutover snapshot backup in /var/backups/                |
|   • Step 2: Deactivate app in legacy agent (.disabled) & reload         |
|   • Step 3: Verify stationary offset (1s window) & copy .pos state      |
|   • Step 4: Deploy minimal master config & app config to conf.d/        |
|   • Step 5: Start & validate OSS Fluentd service                        |
|   • Step 6: Inject canary log & verify arrival in Cloud Logging         |
+-------------------------------------------------------------------------+
                                     │
                                     ▼
+-------------------------------------------------------------------------+
| Migration Complete: migration_execution_report.md generated             |
+-------------------------------------------------------------------------+
```

---

## Shared Migration Context (`migration_context.json`)

All stage results, discovered paths, daemon user/group, application catalog, and execution states are preserved in a **client-generic schema**:

```json
{
  "version": "1.0",
  "last_updated": "2026-08-31T10:00:00Z",
  "target": {
    "vm_name": "target-vm-name",
    "project_id": "target-gcp-project",
    "zone": "target-zone",
    "connectivity_verified": true
  },
  "runtime_environment": {
    "oss_service_name": "fluentd",
    "daemon_user": "_fluentd",
    "daemon_group": "_fluentd",
    "oss_config_dir": "/etc/fluent",
    "oss_include_dir": "/etc/fluent/conf.d",
    "oss_pos_dir": "/var/lib/fluentd/pos",
    "oss_buffer_dir": "/var/log/fluentd/buffers",
    "legacy_service_name": "google-fluentd",
    "legacy_config_dir": "/etc/google-fluentd",
    "legacy_pos_dir": "/var/lib/google-fluentd/pos"
  },
  "discovered_applications": [
    {
      "filename": "app.conf",
      "rel_path": "config.d/app.conf",
      "source_type": "tail",
      "tag": "app.log",
      "pos_file": "app.pos",
      "log_path": "/var/log/app.log",
      "has_dedicated_match": true,
      "migration_readiness": "READY"
    }
  ],
  "compatibility_assessment": {
    "resolved_directives": ["analyze_config", "add_insert_ids"],
    "hard_blockers": [],
    "required_plugins": ["fluent-plugin-google-cloud"]
  },
  "selected_migration_scope": {
    "application_conf": "config.d/app.conf",
    "scoped_master_conf": "/tmp/fluentd_scoped_master.conf",
    "dry_run_verified": true,
    "canary_info": { ... }
  },
  "stage_status": {
    "stage1_discovery": "COMPLETED",
    "stage2_assessment": "COMPLETED",
    "stage3_config_generation": "COMPLETED",
    "stage4_pre_validation": "COMPLETED",
    "gate1_scope_approval": "APPROVED",
    "gate2_cutover_approval": "PENDING",
    "stage5_cutover": "PENDING"
  },
  "artifacts": {
    "staged_configs_dir": "./staged_configs",
    "generated_configs_dir": "./generated_oss_configs",
    "assessment_report": "./migration_assessment.md",
    "config_generation_report": "./config_generation_report.md",
    "compatibility_review_items": "./compatibility_review_items.md",
    "pre_migration_validation_report": "./pre_migration_validation_report.md",
    "migration_execution_report": "./migration_execution_report.md"
  }
}
```

---

## Orchestrator Operations & CLI Interface

The migration orchestrator provides a unified entry point `scripts/orchestrate_migration.py`:

### 1. Run Phase 1 Automated Pipeline (Stages 1 – 4)
Executes discovery, assessment, v1 config generation, and pre-migration validation, then halts at Gate 1:
```bash
python3 ./scripts/orchestrate_migration.py \
    --vm <VM_NAME> \
    --project <PROJECT_ID> \
    --zone <ZONE> \
    --action auto-pipeline
```

### 2. Approve Gate 1 & Run Internal Staging
Approves scope, generates conflict-free master config, performs live remote dry-run, and presents Gate 2:
```bash
python3 ./scripts/orchestrate_migration.py \
    --action approve-scope \
    --app "config.d/<APP_CONF_NAME>"
```

### 3. Approve Gate 2 & Execute Cutover (Stage 5)
Performs rollback snapshot, legacy deactivation, position-state transfer, config deployment, service start, and canary verification in Cloud Logging:
```bash
python3 ./scripts/orchestrate_migration.py \
    --action execute-cutover
```

### 4. Check Migration State & Artifacts
```bash
python3 ./scripts/orchestrate_migration.py --action status
```

---

## Stage 3 Deep Syntax Modernization Rules (CRITICAL)

When the orchestrator (`scripts/generate_oss_config.py`) converts legacy v0.12 configurations to upstream v1 in Stage 3, it **MUST strictly apply the following 10 syntax translation rules** to prevent silent data loss and fatal daemon startup crashes:

### Rule A: Do Not Mix v0.12 and v1 Syntax
Never mix flat v0.12 parameters with nested v1 directives within the same plugin block. Keep `@type google_cloud` at the top of `<match>` before `<buffer>`.

### Rule B: Output Plugin `<buffer>` Migration
Flat buffer parameters inside `<match>` MUST be moved into a nested `<buffer>` directive:
- `buffer_type file` -> `@type file`
- `buffer_path <path>` -> `path <path>`
- `buffer_chunk_limit <size>` -> `chunk_limit_size <size>`
- `flush_interval <sec>` -> `flush_interval <sec>` (inside `<buffer>`)
- `retry_limit <count>` -> `retry_max_times <count>`
- `disable_retry_limit true/false` -> `retry_forever true/false`
- `retry_wait <sec>` -> `retry_wait <sec>` (inside `<buffer>`)
- `max_retry_wait <sec>` -> `retry_max_interval <sec>`
- `num_threads <count>` -> `flush_thread_count <count>`
- `partial_success` -> **REMOVE** (permanently enabled in v1)

### Rule C: Input Plugin `<parse>` & Inline Regex Migration
- Flat `format <type>` parameters (`json`, `multiline`, `syslog`, along with `format_firstline`, `format1..N`, `time_format`, `time_key`) MUST be moved into a nested `<parse>` block with `@type <type>`.
- Inline regex formats (`format /<regex>/`) MUST be converted to `<parse>` with `@type regexp` and `expression /<regex>/`.
- Remove `auto_typecast` if used inside a parser plugin (unsupported in v1; causes fatal startup `ConfigError`).

### Rule D: Ruby Time Object Serialization Fix
Raw Ruby `Time` objects used inside `<record>` filters (e.g., `raw_timestamp ${time}`) cause fatal v1 msgpack serialization crashes. Explicitly cast them: `raw_timestamp ${time.to_i}`.

### Rule E: Modern RabbitMQ Erlang Multiline Format
Upgrade legacy RabbitMQ regex parsers to millisecond precision (`%Y-%m-%d %H:%M:%S.%L`) and Erlang PID capture (`<(?<pid>[^>]+)>`).

### Rule F: gRPC Transport & Compression
Add `use_grpc true` and `grpc_compression_algorithm gzip` under `<match **>` output blocks for optimal ingestion throughput into Cloud Logging.

### Rule G: Regex Comment Escaping
In v1, `#` is strictly an inline comment delimiter. Legacy regex like `format1 /^... #(?<pid>\d+) .../` will silently truncate and crash. You MUST escape it: `format1 /^... \#(?<pid>\d+) .../`.

### Rule H: Syslog Port 514 Privilege Separation
Remap privileged `port 514` to unprivileged `port 5140` for non-root `_fluentd` daemon execution.

### Rule I: Position (`.pos`) File Takeover & Offset Continuity
Preserve `.pos` offset state from `/var/lib/google-fluentd/pos/` to `/var/lib/fluentd/pos/` (with `_fluentd` ownership) so historical logs are not double-ingested and active lines are not dropped.

### Rule J: Prometheus Monitoring Crash (`monitoring_type prometheus` -> `opencensus`) & Edge Case Isolation
- Switch `monitoring_type prometheus` to `monitoring_type opencensus` to avoid fatal `prometheus-client >= 0.10.0` `ArgumentError` crashes.
- Safely comment out proprietary Google filters (`analyze_config`, `add_insert_ids`) and unmapped directives inline, and prepend a `# WARNING [MIGRATION EDGE CASE]` header block for developer review.

---

## Safety Guidelines & Operating Rules

1. **Explicit Target VM Binding:** Never access or run commands against any VM other than the explicitly supplied target.
2. **Read-Only Automated Pipeline:** Stages 1 through 4 are strictly non-intrusive. No service state, packages, or live configurations are modified during Phase 1.
3. **Strict Gate Enforcement:**
   - **Gate 1:** Requires approval on compatibility findings and application scope before generating cutover artifacts.
   - **Gate 2:** Requires explicit confirmation of the exact planned diff and execution steps before any service modification.
4. **Position Continuity:** Never copy or advance `.pos` state while the legacy input is active. Legacy app deactivation and stationary verification across a 1-second window are enforced prior to transfer.
5. **Known-Good Minimal Configuration:** Deploys `@include /etc/fluent/conf.d/*.conf` without unnecessary global catch-all `<match **>` blocks or OpenCensus telemetry that could conflict with `google-fluentd`.
6. **Automated Rollback:** Every live cutover creates a timestamped `/var/backups/` snapshot and automatically restores legacy state if service start or canary verification fails.
