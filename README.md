# Google Fluentd Migration Skill

An agentic skill to automate discovery, configuration generation, and validation for migrating workloads from Google Fluentd to OSS Fluentd.

## Scope
This skill provides an end-to-end automated workflow for migrating logging workloads:
- **Discovery**: Analyzes `@include` rules, identifies configurations, extracts logging metadata (format, parse types, buffer paths), and recommends OSS Fluentd plugins.
- **Configuration Generation**: Automatically generates client-generic, v1-syntax OSS Fluentd configurations locally from read-only target snapshots, isolating proprietary filters for review.
- **Pre-Migration Validation**: Performs non-destructive AST syntax checks, tag routing, dependency context assembly, path permission validation, and blocker identification.
- **Controlled Migration**: Executes approval-gated, selective-scope cutovers with rollback state preservation, position offset continuity, and source-aware canary delivery verification.

*Note: No active modifications, installations, or active migration cutovers will occur without explicit user approval.*

## Hard Safety Restrictions
- When the user asks to run the skill, the agent must immediately ask the user for:
  - **Allowed VM**
  - **Allowed GCP Project**
  - **Allowed Zone**
- The agent must wait for the user to enter these details before proceeding with any discovery.

Connecting to or modifying any other infrastructure is strictly prohibited. Every `gcloud compute ssh` command must include the exact `--project` and `--zone` flags matching the dynamically provided input.

## Execution

**1. Local Testing (Safe):**
Use the test wrappers to validate the logic against local dummy configs safely without touching any VMs.
- Discovery: `./scripts/test_local_discovery.sh`
- Config Generation: `./scripts/test_config_generation.sh`
- Validation: `./scripts/test_pre_migration_validation.sh`
- Migration: `./scripts/test_controlled_migration.sh`

**2. VM Discovery (Stage 1):**
Run the interactive discovery script to securely prompt for the VM details, check service status, and parse `/etc/google-fluentd/` using standard read-only commands.
`./run_discovery.sh`

**3. OSS Config Generation (Stage 3):**
Generate client-generic, v1-syntax OSS Fluentd configurations locally from the read-only target snapshots.
`./run_config_generation.sh`

**4. Pre-Migration Validation (Stage 4):**
Perform non-destructive syntax, path permission, and blocker validation by full or selective application scope.
`./run_pre_migration_validation.sh`

**5. Controlled Migration (Stage 5):**
Execute approval-gated cutover for an approved application.
`./run_controlled_migration.sh`
