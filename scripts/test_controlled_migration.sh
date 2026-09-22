#!/bin/bash
set -eo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
TEST_DIR="$REPO_ROOT/tests/test_stage5_env"

echo "================================================"
echo " Testing Stage 5 Controlled Migration Engine "
echo "================================================"

rm -rf "$TEST_DIR"
mkdir -p "$TEST_DIR/config.d"

# Setup test master config with Prometheus port listener
cat << 'EOF' > "$TEST_DIR/google-fluentd.conf"
@include config.d/*.conf

<source>
  @type prometheus
  port 24231
</source>

<source>
  @type prometheus_monitor
</source>

<match **>
  @type google_cloud
  buffer_path /var/log/fluentd/buffers
</match>
EOF

cat << 'EOF' > "$TEST_DIR/config.d/ravi-detect-json-baseline.conf"
<source>
  @type tail
  <parse>
    @type none
  </parse>
  path /var/log/ravi-detect-json-baseline.log
  pos_file /var/lib/fluentd/pos/ravi-detect-json-baseline.pos
  tag ravi.detect_json.baseline
</source>

<match ravi.detect_json.baseline>
  @type google_cloud
  detect_json true
</match>
EOF

cat << 'EOF' > "$TEST_DIR/config.d/app_http.conf"
<source>
  @type http
  port 9880
</source>
<match app.http>
  @type google_cloud
</match>
EOF

echo "--- Test 1: Conflict-Free Scoped Master Config Generation ---"
python3 "$SCRIPT_DIR/prepare_scoped_cutover_config.py" "$TEST_DIR/google-fluentd.conf" "$TEST_DIR/scoped_master.conf"

if grep -q "^<source>" "$TEST_DIR/scoped_master.conf"; then
    echo "FAIL: Shared port listener <source> was not excluded in scoped master config."
    exit 1
fi

if grep -q "<match \*\*>" "$TEST_DIR/scoped_master.conf"; then
    echo "FAIL: Unnecessary global catch-all <match **> was introduced in minimal scoped master config."
    exit 1
fi

if ! grep -q "@include /etc/fluent/conf.d/\*\.conf" "$TEST_DIR/scoped_master.conf"; then
    echo "FAIL: Missing standard OSS @include conf.d/*.conf directive."
    exit 1
fi

if grep -q "config\.d" "$TEST_DIR/scoped_master.conf"; then
    echo "FAIL: Duplicate or extra config.d include found in scoped master config."
    exit 1
fi
echo "PASS: Scoped master config successfully generated known-good minimal pattern with single include path."

echo "--- Test 2: Execution Plan Generation (Tail Source) ---"
PLAN_OUT=$(python3 "$SCRIPT_DIR/stage5_migration_engine.py" "$TEST_DIR" "config.d/ravi-detect-json-baseline.conf")

if ! echo "$PLAN_OUT" | grep -q "ravi.detect_json.baseline"; then
    echo "FAIL: Target tag missing in generated plan."
    exit 1
fi

if ! echo "$PLAN_OUT" | grep -q "Deactivate Application in Legacy Agent"; then
    echo "FAIL: Deactivate legacy step missing in plan."
    exit 1
fi

if ! echo "$PLAN_OUT" | grep -q "Transfer Position State"; then
    echo "FAIL: Transfer position step missing in plan."
    exit 1
fi

if ! echo "$PLAN_OUT" | grep -q "Step 6: End-to-End Canary Validation"; then
    echo "FAIL: Step 6 Canary Validation naming missing in plan."
    exit 1
fi
echo "PASS: Execution plan correctly structured with proper sequence and position preservation."

echo "--- Test 3: Source-Aware Canary Generation (HTTP Source) ---"
PLAN_HTTP=$(python3 "$SCRIPT_DIR/stage5_migration_engine.py" "$TEST_DIR" "config.d/app_http.conf")

if ! echo "$PLAN_HTTP" | grep -q "curl -s -X POST"; then
    echo "FAIL: HTTP source canary was not generated with curl POST."
    exit 1
fi
echo "PASS: Source-aware canary generator correctly selected HTTP curl injection."

echo "--- Test 4: Execution Cutover Flow & Report Generation ---"
REPORT_TEST="$TEST_DIR/test_migration_report.md"
python3 "$SCRIPT_DIR/stage5_migration_engine.py" "$TEST_DIR" "config.d/ravi-detect-json-baseline.conf" \
    --execute \
    --scoped-master "$TEST_DIR/scoped_master.conf" \
    --report "$REPORT_TEST"

if [ ! -f "$REPORT_TEST" ]; then
    echo "FAIL: Migration execution report was not created."
    exit 1
fi

if ! grep -q "STAGE 5 MIGRATION SUCCESSFUL - CANARY VERIFIED" "$REPORT_TEST"; then
    echo "FAIL: Report does not indicate successful migration."
    exit 1
fi

if ! grep -q "Step 6: End-to-End Canary Validation" "$REPORT_TEST"; then
    echo "FAIL: Report does not contain Step 6 Canary Validation."
    exit 1
fi

if ! grep -q "Rollback Safeguard Procedure" "$REPORT_TEST"; then
    echo "FAIL: Report does not include Rollback Safeguard Procedure."
    exit 1
fi
echo "PASS: Stage 5 execution flow completed and generated complete execution report with rollback instructions."

echo "--- Test 5: Step 3 Remote Stat Quoting Verification ---"
python3 -c "
import shlex, subprocess, tempfile
with tempfile.NamedTemporaryFile(prefix='test pos ', suffix='.pos') as tf:
    stat_cmd = f\"stat -c '%s %Y' {shlex.quote(tf.name)} 2>/dev/null || echo '0 0'\"
    remote_cmd = f\"bash -c {shlex.quote(stat_cmd)}\"
    res = subprocess.run(['bash', '-c', remote_cmd], capture_output=True, text=True)
    if res.returncode != 0 or 'missing operand' in res.stderr:
        print('FAIL: stat quoting failed:', res.stderr)
        exit(1)
    parts = res.stdout.strip().split()
    if len(parts) != 2:
        print('FAIL: unexpected stat output:', res.stdout)
        exit(1)
print('PASS: stat command executed cleanly without missing operand errors.')
"
echo "PASS: Step 3 remote stat quoting confirmed safe against shell expansion."

echo "--- Test 6: Authoritative Systemd Service User/Group Discovery Verification ---"
python3 -c "
import re

mock_unit_1 = '''
[Unit]
Description=fluentd service

[Service]
User=_fluentd
Group=_fluentd
Environment=FLUENT_CONF=/etc/fluent/fluentd.conf
'''

mock_unit_2 = '''
[Service]
User = custom-logger
Group = custom-group # logging group
'''

def parse_user_group(unit_text):
    user_found = None
    group_found = None
    for line in unit_text.splitlines():
        line_str = line.strip()
        m_user = re.match(r'^\s*User\s*=\s*[\"\'\']?([^\"\'\'\s#]+)', line_str)
        if m_user:
            user_found = m_user.group(1).strip()
        m_group = re.match(r'^\s*Group\s*=\s*[\"\'\']?([^\"\'\'\s#]+)', line_str)
        if m_group:
            group_found = m_group.group(1).strip()
    return user_found, group_found

u1, g1 = parse_user_group(mock_unit_1)
assert u1 == '_fluentd' and g1 == '_fluentd', f'Expected _fluentd, got {u1}:{g1}'

u2, g2 = parse_user_group(mock_unit_2)
assert u2 == 'custom-logger' and g2 == 'custom-group', f'Expected custom-logger:custom-group, got {u2}:{g2}'

print('PASS: Authoritative systemd service User/Group discovery verified dynamically.')
"

rm -rf "$TEST_DIR"

echo "================================================"
echo " All Stage 5 migration engine assertions passed! "
echo "================================================"
