#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TEST_DIR="$REPO_DIR/tests/test_orch_env"
rm -rf "$TEST_DIR"
mkdir -p "$TEST_DIR/config.d"

echo "================================================"
echo " Testing Migration Orchestrator Workflow Engine"
echo "================================================"

# Create mock active legacy configurations
cat << 'EOF' > "$TEST_DIR/google-fluentd.conf"
@include config.d/*.conf
<source>
  @type prometheus
  port 24231
</source>
<filter **>
  @type analyze_config
</filter>
<match **>
  @type google_cloud
</match>
EOF

cat << 'EOF' > "$TEST_DIR/config.d/test-app-json.conf"
<source>
  @type tail
  <parse>
    @type none
  </parse>
  path /var/log/test-app-json.log
  pos_file /var/lib/fluentd/pos/test-app-json.pos
  read_from_head true
  tag test.app.json
</source>

<match test.app.json>
  @type google_cloud
  detect_json true
</match>
EOF

MOCK_CONTEXT="$TEST_DIR/test_migration_context.json"

echo "--- Test 1: Shared Migration Context Initialization & Persistence ---"
python3 -c "
from scripts.migration_context import MigrationContext
ctx = MigrationContext('$MOCK_CONTEXT')
ctx.set_target('mock-test-vm', 'mock-project', 'mock-zone', connectivity_verified=True)
ctx.update_runtime(daemon_user='mock_user', oss_service_name='fluentd')
ctx.save()

ctx2 = MigrationContext('$MOCK_CONTEXT')
assert ctx2.data['target']['vm_name'] == 'mock-test-vm'
assert ctx2.data['runtime_environment']['daemon_user'] == 'mock_user'
print('PASS: MigrationContext state persistence verified.')
"

echo "--- Test 2: Phase 1 Automated Pipeline (Stages 1-4) & Gate 1 Halt ---"
# Stage mock configs into workspace staged_configs
mkdir -p "$REPO_DIR/staged_configs/config.d"
cp "$TEST_DIR/google-fluentd.conf" "$REPO_DIR/staged_configs/"
cp "$TEST_DIR/config.d/test-app-json.conf" "$REPO_DIR/staged_configs/config.d/"

python3 "$SCRIPT_DIR/orchestrate_migration.py" \
    --vm "mock-test-vm" \
    --project "mock-project" \
    --zone "mock-zone" \
    --context "$MOCK_CONTEXT" \
    --local-mode \
    --action auto-pipeline

python3 -c "
from scripts.migration_context import MigrationContext
ctx = MigrationContext('$MOCK_CONTEXT')
st = ctx.data['stage_status']
assert st['stage1_discovery'] == 'COMPLETED', 'Stage 1 should be completed'
assert st['stage2_assessment'] == 'COMPLETED', 'Stage 2 should be completed'
assert st['stage3_config_generation'] == 'COMPLETED', 'Stage 3 should be completed'
assert st['stage4_pre_validation'] == 'COMPLETED', 'Stage 4 should be completed'
assert st['gate1_scope_approval'] == 'PENDING', 'Gate 1 should be pending'
assert len(ctx.data['discovered_applications']) > 0, 'Applications should be discovered'
print('PASS: Stages 1-4 executed automatically and stopped cleanly at Gate 1.')
"

echo "--- Test 3: Gate 1 Approval, Internal Scoped Prep & Gate 2 Halt ---"
python3 "$SCRIPT_DIR/orchestrate_migration.py" \
    --context "$MOCK_CONTEXT" \
    --local-mode \
    --action approve-scope \
    --app "config.d/test-app-json.conf"

python3 -c "
from scripts.migration_context import MigrationContext
ctx = MigrationContext('$MOCK_CONTEXT')
assert ctx.data['stage_status']['gate1_scope_approval'] == 'APPROVED', 'Gate 1 should be approved'
assert ctx.data['selected_migration_scope']['application_conf'] == 'config.d/test-app-json.conf'
assert ctx.data['selected_migration_scope']['dry_run_verified'] is True
assert ctx.data['stage_status']['gate2_cutover_approval'] == 'PENDING', 'Gate 2 should be pending'
print('PASS: Gate 1 scope approved, internal prep executed, and halted cleanly at Gate 2.')
"

echo "--- Test 4: Gate 2 Authorization & Stage 5 Cutover Execution ---"
python3 "$SCRIPT_DIR/orchestrate_migration.py" \
    --context "$MOCK_CONTEXT" \
    --local-mode \
    --action execute-cutover

python3 -c "
from scripts.migration_context import MigrationContext
ctx = MigrationContext('$MOCK_CONTEXT')
assert ctx.data['stage_status']['gate2_cutover_approval'] == 'APPROVED', 'Gate 2 should be approved'
assert ctx.data['stage_status']['stage5_cutover'] == 'COMPLETED', 'Stage 5 should be completed'
assert ctx.data.get('overall_status') == 'COMPLETED', 'Overall status should be marked COMPLETED'
assert ctx.data['artifacts']['migration_execution_report'] is not None
print('PASS: Stage 5 cutover executed, overall_status marked as COMPLETED, and exited cleanly.')
"

echo "--- Test 5: Interactive 2-Gate Prompt Flow Verification ---"
MOCK_INTERACTIVE_CONTEXT="$TEST_DIR/test_interactive_context.json"
# Feed input: '1' for Gate 1 (scope), 'y' for Gate 2 (cutover)
printf "1\ny\n" | python3 "$SCRIPT_DIR/orchestrate_migration.py" \
    --vm "mock-interactive-vm" \
    --project "mock-project" \
    --zone "mock-zone" \
    --context "$MOCK_INTERACTIVE_CONTEXT" \
    --local-mode \
    --action interactive

python3 -c "
from scripts.migration_context import MigrationContext
ctx = MigrationContext('$MOCK_INTERACTIVE_CONTEXT')
assert ctx.data['stage_status']['stage1_discovery'] == 'COMPLETED'
assert ctx.data['stage_status']['stage4_pre_validation'] == 'COMPLETED'
assert ctx.data['stage_status']['gate1_scope_approval'] == 'APPROVED'
assert ctx.data['stage_status']['gate2_cutover_approval'] == 'APPROVED'
assert ctx.data['stage_status']['stage5_cutover'] == 'COMPLETED'
assert ctx.data.get('overall_status') == 'COMPLETED'
print('PASS: Interactive migration completed cleanly with exactly 2 user gates.')
"

rm -rf "$TEST_DIR"
rm -f "$REPO_DIR/staged_configs/config.d/test-app-json.conf"

echo "================================================"
echo " All Migration Orchestrator assertions passed!  "
echo "================================================"
