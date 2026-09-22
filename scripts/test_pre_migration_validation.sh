#!/bin/bash
set -eo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
TEST_DIR="$REPO_ROOT/tests/test_validation_env"
REPORT_FILE="$REPO_ROOT/tests/test_validation_report.md"

echo "================================================"
echo " Testing Stage 4 Pre-Migration Validator "
echo "================================================"

rm -rf "$TEST_DIR" "$REPORT_FILE"
mkdir -p "$TEST_DIR/config.d"

# Create a test setup with global match, add_insert_ids, and an unknown blocker
cat << 'EOF' > "$TEST_DIR/google-fluentd.conf"
# STATUS: [NOT MIGRATION-READY] - Contains commented proprietary/unknown directives requiring review.
@include config.d/*.conf

### [MANUAL REVIEW REQUIRED] COMPATIBILITY ITEM - analyze_config ###
# <filter **>
#   @type analyze_config
# </filter>
### END [MANUAL REVIEW REQUIRED] ###

### [MANUAL REVIEW REQUIRED] COMPATIBILITY ITEM - add_insert_ids ###
# <filter **>
#   @type add_insert_ids
# </filter>
### END [MANUAL REVIEW REQUIRED] ###

<match **>
  @type google_cloud
  buffer_path /var/log/fluentd/buffers
</match>
EOF

cat << 'EOF' > "$TEST_DIR/config.d/app1.conf"
# STATUS: [MIGRATION-READY] - Converted to OSS Fluentd syntax.
<source>
  @type tail
  <parse>
    @type json
  </parse>
  path /var/log/app1.log
  pos_file /var/lib/fluentd/pos/app1.pos
  tag app1.events
</source>
EOF

cat << 'EOF' > "$TEST_DIR/config.d/app_with_unknown_blocker.conf"
# STATUS: [NOT MIGRATION-READY] - Contains commented proprietary/unknown directives requiring review.
<source>
  @type tail
  path /var/log/app_unknown.log
  pos_file /var/lib/fluentd/pos/app_unknown.pos
  tag app.unknown
</source>

### [MANUAL REVIEW REQUIRED] COMPATIBILITY ITEM - custom_unsupported_plugin ###
# <filter app.unknown>
#   @type custom_unsupported_plugin
# </filter>
### END [MANUAL REVIEW REQUIRED] ###
EOF

echo "--- Test 1: Selective Scope Validation (app1.conf with native/telemetry classifications) ---"
python3 "$SCRIPT_DIR/validate_oss_config.py" "$TEST_DIR" "google-fluentd.conf" "config.d/app1.conf" "$REPORT_FILE"

# Assertion 1: Behavior classification verified
if ! grep -q "Resolved via Native Plugin" "$REPORT_FILE" || ! grep -q "Non-Blocking / Agent Telemetry" "$REPORT_FILE"; then
    echo "FAIL: add_insert_ids or analyze_config was not correctly classified in behavior analysis."
    exit 1
fi
echo "PASS: add_insert_ids and analyze_config correctly classified as resolved/non-blocking."

# Assertion 2: Clean app without hard blockers passes static checks
if grep -q "BLOCKED - UNRESOLVED COMPATIBILITY BLOCKERS" "$REPORT_FILE"; then
    echo "FAIL: app1.conf was blocked by non-blocking/resolved items."
    exit 1
fi
echo "PASS: app1.conf correctly has zero hard blockers."

echo "--- Test 2: Hard Blocker Validation (app_with_unknown_blocker.conf) ---"
python3 "$SCRIPT_DIR/validate_oss_config.py" "$TEST_DIR" "google-fluentd.conf" "config.d/app_with_unknown_blocker.conf" "$REPORT_FILE"

if ! grep -q "BLOCKED - UNRESOLVED COMPATIBILITY BLOCKERS" "$REPORT_FILE"; then
    echo "FAIL: Truly unknown plugin was not flagged as hard blocker."
    exit 1
fi
echo "PASS: Truly unknown custom plugin correctly flagged as hard blocker."

rm -rf "$TEST_DIR" "$REPORT_FILE"

echo "================================================"
echo " All Stage 4 validation test assertions passed! "
echo "================================================"
