# Google Fluentd Migration Skill

An agentic skill to automate discovery, configuration generation, and validation for migrating workloads from Google Fluentd (`v0.12`) to OSS Fluentd (`v1`).

## Contributors & Component Ownership
- **End-to-End VM Orchestration, Discovery & Controlled Cutover Pipeline:** Ravi Chandra Eluri
- **v0.12-to-v1 Syntax Modernization Engine, Breaking-Change Rules & 3P App Test Suite (25 Scenarios):** Kiran Kumar Reddy Kanchani

---

## Scope
This skill provides an end-to-end automated workflow for migrating logging workloads:
- **Discovery**: Analyzes `@include` rules, identifies configurations, extracts logging metadata (format, parse types, buffer paths), and recommends OSS Fluentd plugins.
- **Configuration Generation (v0.12 -> v1)**: Automatically generates client-generic, v1-syntax OSS Fluentd configurations locally from read-only target snapshots, applying 10 breaking-change syntax rules and isolating proprietary filters for review.
- **Pre-Migration Validation**: Performs non-destructive AST syntax checks, tag routing, dependency context assembly, path permission validation, and blocker identification.
- **Controlled Migration**: Executes approval-gated, selective-scope cutovers with rollback state preservation, position offset continuity, and source-aware canary delivery verification.

*Note: No active modifications, installations, or active migration cutovers will occur without explicit user approval.*

---

## Hard Safety Restrictions
- When the user asks to run the skill, the agent must immediately ask the user for:
  - **Allowed VM**
  - **Allowed GCP Project**
  - **Allowed Zone**
- The agent must wait for the user to enter these details before proceeding with any discovery.

Connecting to or modifying any other infrastructure is strictly prohibited. Every `gcloud compute ssh` command must include the exact `--project` and `--zone` flags matching the dynamically provided input.

---

## Agent Execution
To run this migration automatically using an AI Agent, simply open this repository in your agent's workspace and provide the following prompt:
> **"Run the google-fluentd-migration-skill"**

The agent will automatically read the `SKILL.md` file, understand the architecture and safety boundaries, and interactively guide you through the migration stages.

---

## Quick Start: Local Testing & 3P App Config Translation (No VM Needed)

### 1. Run the One-Command Interactive Demo & 25-Scenario Verification Suite
Run `./run_demo.sh` (or `python3 tests/test_migration_suite.py`) to see a live **Before (`v0.12`) vs. After (`v1`)** config translation and execute all **25 third-party application migration scenarios** (Nginx, Apache, Syslog, Java HTTP/Forward, RabbitMQ, Redis, MongoDB, PostgreSQL, MySQL, Kafka, Tomcat, Elasticsearch, ZooKeeper, HAProxy, Kubernetes Metadata, Puppet, Memcached, Joomla CMS, GitLab, Magento, Redmine, SaltStack, and Prometheus-to-OpenCensus):
```bash
./run_demo.sh
```

### 2. Translate Any Individual Legacy `.conf` File (`sample_legacy_configs/`)
```bash
python3 scripts/migrate_legacy_to_modern.py \
    sample_legacy_configs/legacy_paulina_doc_example.conf \
    /tmp/modern_output.conf
```

### 3. Stage-by-Stage Local Test Wrappers
Use the test wrappers to validate the pipeline logic against local dummy configs safely without touching any VMs:
- Discovery: `./scripts/test_local_discovery.sh`
- Config Generation: `./scripts/test_config_generation.sh`
- Validation: `./scripts/test_pre_migration_validation.sh`
- Migration: `./scripts/test_controlled_migration.sh`

---

## Manual VM Execution

**1. VM Discovery (Stage 1):**
Run the interactive discovery script to securely prompt for the VM details, check service status, and parse `/etc/google-fluentd/` using standard read-only commands.
`./run_discovery.sh`

**2. OSS Config Generation (Stage 3):**
Generate client-generic, v1-syntax OSS Fluentd configurations locally from the read-only target snapshots.
`./run_config_generation.sh`

**3. Pre-Migration Validation (Stage 4):**
Perform non-destructive syntax, path permission, and blocker validation by full or selective application scope.
`./run_pre_migration_validation.sh`

**4. Controlled Migration (Stage 5):**
Execute approval-gated cutover for an approved application.
`./run_controlled_migration.sh`

---

## Stage 3 Syntax Modernization & Breaking-Change Rules Encoded (`v0.12` -> `v1`)

| # | Discrepancy / Breaking Change (`google-fluentd` vs OSS `fluentd` v1) | Legacy `google-fluentd` (`v0.12`) | Modern OSS `fluentd` (`v1` Fix Applied by Skill) |
| :- | :--- | :--- | :--- |
| **1** | **Flat Output Buffer Params** | `buffer_type file`, `buffer_chunk_limit`, `flush_interval`, `num_threads`, `retry_limit` | Wrapped inside nested `<buffer>` block (`@type file`, `chunk_limit_size`, `flush_interval`, `flush_thread_count`, `retry_max_times`) |
| **2** | **Deprecated `partial_success` Flag** | `partial_success true` | Automatically **removed** (permanently enabled by default in v1) |
| **3** | **Input `<parse>` & Inline Regex Formats** | `format json`, `format multiline`, or `format /<regex>/` | Converted to nested `<parse>` block (`@type regexp` + `expression /<regex>/` for inline regexes) |
| **4** | **JSON `auto_typecast` Crash** | `auto_typecast true` (silently ignored in v0.12; crashes v1) | Automatically **removed** from parser blocks |
| **5** | **Ruby `Time` Serializer Crash** | `raw_timestamp ${time}` in `record_transformer` | Explicitly cast to integer: `raw_timestamp ${time.to_i}` |
| **6** | **RabbitMQ Modern Erlang Format** | `time_format %Y-%m-%d %H:%M:%S` | Upgraded to millisecond precision (`%Y-%m-%d %H:%M:%S.%L`) + `<pid>` capture |
| **7** | **gRPC Transport & Compression** | REST defaults | Adds `use_grpc true` & `grpc_compression_algorithm gzip` |
| **8** | **Regex `#` Inline Comment Truncation** | `format1 /^... #(?<pid>\d+) .../` | Escapes unescaped `#` inside regex literals (`\#(?<pid>\d+)`) |
| **9** | **Syslog Port `514` Privilege Separation** | `port 514` (requires `root`) | Remaps to unprivileged `port 5140` for `_fluentd` daemon |
| **10** | **Prometheus Crash & Proprietary Directives** | `monitoring_type prometheus` / `analyze_config` / `add_insert_ids` | Switches to `monitoring_type opencensus` & comments out proprietary directives with `# WARNING [MIGRATION EDGE CASE]` |
