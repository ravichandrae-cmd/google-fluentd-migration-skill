#!/bin/bash
set -eo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
SAMPLE_DIR="$REPO_ROOT/tests/sample_configs"
OUT_DIR="$REPO_ROOT/tests/test_output_configs"
REPORT_FILE="$REPO_ROOT/tests/test_config_report.md"
REVIEW_FILE="$REPO_ROOT/tests/test_review_items.md"

echo "================================================"
echo " Testing Stage 3 OSS Config Generator "
echo "================================================"

rm -rf "$OUT_DIR" "$REPORT_FILE" "$REVIEW_FILE"

python3 "$SCRIPT_DIR/generate_oss_config.py" "$SAMPLE_DIR" "$OUT_DIR" "google-fluentd.conf" "/var/lib/fluentd/pos" "/var/log/fluentd/buffers" "$REPORT_FILE" "$REVIEW_FILE"

echo -e "\nRunning Assertions..."

# Assertion 1: Unreferenced files (.bak) must not be in output
if [ -f "$OUT_DIR/config.d/unused_config.bak" ]; then
    echo "FAIL: Unreferenced file unused_config.bak was generated in output."
    exit 1
fi
echo "PASS: Unreferenced file unused_config.bak correctly excluded."

# Assertion 2: Referenced files must exist
if [ ! -f "$OUT_DIR/google-fluentd.conf" ] || [ ! -f "$OUT_DIR/config.d/nginx.conf" ] || [ ! -f "$OUT_DIR/config.d/syslog.conf" ]; then
    echo "FAIL: Missing expected generated configuration files."
    exit 1
fi
echo "PASS: All active configuration files generated."

# Assertion 3: Entire block commenting for proprietary filters
if grep -q "^<filter \*\*" "$OUT_DIR/google-fluentd.conf"; then
    echo "FAIL: Un-commented <filter **> tag found for proprietary plugins in google-fluentd.conf."
    exit 1
fi
if ! grep -q "# <filter \*\*" "$OUT_DIR/google-fluentd.conf" || ! grep -q "# </filter>" "$OUT_DIR/google-fluentd.conf"; then
    echo "FAIL: Entire filter block was not commented out properly."
    exit 1
fi
echo "PASS: Entire proprietary filter blocks (<filter **> ... </filter>) successfully commented out."

# Assertion 4: NOT MIGRATION-READY banner and report status
if ! grep -q "STATUS: \[NOT MIGRATION-READY\]" "$OUT_DIR/google-fluentd.conf"; then
    echo "FAIL: Header banner in google-fluentd.conf does not indicate NOT MIGRATION-READY."
    exit 1
fi
if ! grep -q "OVERALL STATUS: NOT MIGRATION-READY" "$REPORT_FILE"; then
    echo "FAIL: Overall report status is not NOT MIGRATION-READY."
    exit 1
fi
echo "PASS: Migration readiness status correctly marked as NOT MIGRATION-READY."

# Assertion 5: Full original blocks preserved in review artifact
if ! grep -q "analyze_config" "$REVIEW_FILE" || ! grep -q "add_insert_ids" "$REVIEW_FILE"; then
    echo "FAIL: Compatibility review artifact does not contain full review items."
    exit 1
fi
echo "PASS: Compatibility review items and full original blocks preserved in review artifact."

# Assertion 6: Path remapping (pos_file & buffer_path)
if grep -q "google-fluentd" "$OUT_DIR/config.d/nginx.conf" "$OUT_DIR/config.d/syslog.conf"; then
    echo "FAIL: Legacy google-fluentd paths found in generated config files."
    exit 1
fi
echo "PASS: All buffer_path and pos_file entries successfully remapped to /var/log/fluentd and /var/lib/fluentd."

# Assertion 7: Syntax upgrade (format -> <parse>)
if grep -q "^[[:space:]]*format " "$OUT_DIR/config.d/syslog.conf"; then
    echo "FAIL: Legacy 'format syslog' was not upgraded to <parse> syntax."
    exit 1
fi
if ! grep -q "<parse>" "$OUT_DIR/config.d/syslog.conf"; then
    echo "FAIL: <parse> block not found in syslog.conf."
    exit 1
fi
echo "PASS: Legacy format syntax successfully upgraded to Fluentd v1 <parse> blocks."

rm -rf "$OUT_DIR" "$REPORT_FILE" "$REVIEW_FILE"

echo "================================================"
echo " All Stage 3 generator assertions passed! "
echo "================================================"
