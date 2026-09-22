#!/bin/bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_CONFIG="$BASE_DIR/tests/sample_configs"

echo "Triggering local config discovery testing..."
OUTPUT=$(bash "$BASE_DIR/scripts/discover_config.sh" "$TARGET_CONFIG")

echo "$OUTPUT"

echo "================================================"
echo " Running Assertions..."
echo "================================================"

function assert_contains() {
    if ! echo "$OUTPUT" | grep -q "$1"; then
        echo "ASSERTION FAILED: Missing '$1' in output."
        exit 1
    fi
}

assert_contains "\[Included\] .*/tests/sample_configs/config.d/nginx.conf"
assert_contains "\[Included\] .*/tests/sample_configs/config.d/syslog.conf"
assert_contains "\[Not Included\] .*/tests/sample_configs/config.d/unused_config.bak"
assert_contains "type: tail"
assert_contains "path: /var/log/nginx/access.log"
assert_contains "parse_type: nginx"
assert_contains "format: syslog"
assert_contains "buffer_path: /var/lib/google-fluentd/buffers"
assert_contains "Require 'fluent-plugin-google-cloud' OSS plugin."
assert_contains "Fluentd core supports nginx out-of-the-box."

echo "All assertions passed successfully!"
