# Google Fluentd Migration Skill POC

This repository contains a Proof of Concept (POC) Agent Skill designed to assist with migrating from `google-fluentd` to OSS Fluentd.

## Scope
Currently limited to generalized read-only discovery and migration assessment. 
The discovery script analyzes `@include` rules, identifies Included vs. Not Included configs, extracts logging metadata (format, parse types, buffer paths), and recommends OSS Fluentd plugins. No modifications, installations, or active migration cutovers will occur without explicit approval.

## Hard Safety Restrictions
- When the user asks to run the skill, the agent must immediately ask the user for:
  - **Allowed VM**
  - **Allowed GCP Project**
  - **Allowed Zone**
- The agent must wait for the user to enter these details before proceeding with any discovery.

Connecting to or modifying any other infrastructure is strictly prohibited. Every `gcloud compute ssh` command must include the exact `--project` and `--zone` flags matching the dynamically provided input.

## Execution
**1. Local Testing (Safe):**
Use the test wrapper to validate the discovery logic against dummy configs safely without touching any VMs.
`./scripts/test_local_discovery.sh`

**2. VM Discovery (Interactive Shell Script):**
Run the interactive discovery script in your terminal to securely prompt for the VM details, check the service status, and parse `/etc/google-fluentd/` using standard read-only bash commands.
`./run_discovery.sh`

**3. OSS Config Generation (Stage 3):**
Generate client-generic, v1-syntax OSS Fluentd configurations locally from read-only target snapshots or local files, isolating proprietary filters for review.
`./run_config_generation.sh`
- Local testing: `./scripts/test_config_generation.sh`

**4. Pre-Migration Validation (Stage 4):**
Perform non-destructive AST syntax, tag routing, dependency context assembly, path permission, and blocker validation by full or selective application scope.
`./run_pre_migration_validation.sh`
- Local testing: `./scripts/test_pre_migration_validation.sh`

**5. Controlled Migration (Stage 5):**
Execute approval-gated, selective-scope cutover for an approved application with rollback state preservation, position offset continuity, and source-aware canary delivery verification.
`./run_controlled_migration.sh`
- Local testing: `./scripts/test_controlled_migration.sh`
