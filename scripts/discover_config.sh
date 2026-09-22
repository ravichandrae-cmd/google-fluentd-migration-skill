#!/bin/bash
set -euo pipefail

TARGET_DIR="${1:-/etc/google-fluentd}"
MAIN_CONF="$TARGET_DIR/google-fluentd.conf"

echo "================================================"
echo " Starting Discovery Assessment in: $TARGET_DIR"
echo "================================================"

if [ ! -d "$TARGET_DIR" ]; then
    echo "ERROR: Configuration directory $TARGET_DIR not found."
    exit 1
fi

echo -e "\n=== 1. Main Configuration File ==="
if [ -f "$MAIN_CONF" ]; then
    echo "Found: $MAIN_CONF"
else
    echo "ERROR: Main config $MAIN_CONF not found."
    exit 1
fi

echo -e "\n=== 2. @include Rules & Config Files ==="
INCLUDES=$(grep -E "^[[:space:]]*@include" "$MAIN_CONF" | awk '{print $2}' || true)
echo "Include patterns found in main config:"
echo "$INCLUDES"

echo -e "\n--- Included Configuration Files ---"
INCLUDED_FILES=("$MAIN_CONF")
if [ -n "$INCLUDES" ]; then
    for pattern in $INCLUDES; do
        if [[ "$pattern" != /* ]]; then
            pattern="$TARGET_DIR/$pattern"
        fi
        # Use nullglob to prevent iterating over unexpanded glob literals
        shopt -s nullglob
        for file in $pattern; do
            if [ -f "$file" ]; then
                echo "[Included] $file"
                INCLUDED_FILES+=("$file")
            fi
        done
        shopt -u nullglob
    done
fi

echo -e "\n--- Not Included / Unknown Configuration Files ---"
CONFIG_D="$TARGET_DIR/config.d"
if [ -d "$CONFIG_D" ]; then
    shopt -s nullglob
    for file in "$CONFIG_D"/*; do
        if [ -f "$file" ]; then
            is_included=0
            for included in "${INCLUDED_FILES[@]}"; do
                if [ "$file" == "$included" ]; then
                    is_included=1
                    break
                fi
            done
            if [ "$is_included" -eq 0 ]; then
                if [[ "$file" == *.conf ]]; then
                    echo "[Unknown] $file (Has .conf but not matched by include)"
                else
                    echo "[Not Included] $file"
                fi
            fi
        fi
    done
    shopt -u nullglob
fi

echo -e "\n=== 3. Extracted Key Fields (Sources, Matches, Filters) ==="
for file in "${INCLUDED_FILES[@]}"; do
    echo "--- Parsing: $file ---"
    awk '
        /<source>/ { in_block="source"; print "  [Source block]" }
        /<match/ { in_block="match"; tag=$2; gsub(/>/, "", tag); print "  [Match block] tag: " tag }
        /<filter/ { in_block="filter"; tag=$2; gsub(/>/, "", tag); print "  [Filter block] tag: " tag }
        /<parse>/ { in_parse=1 }
        /<\/(source|match|filter)>/ { in_block="" }
        /<\/parse>/ { in_parse=0 }
        in_block && /^[[:space:]]*@type/ { if (in_parse) {print "    parse_type: " $2} else {print "    type: " $2} }
        in_block && /^[[:space:]]*path/ { print "    path: " $2 }
        in_block && /^[[:space:]]*pos_file/ { print "    pos_file: " $2 }
        in_block && /^[[:space:]]*tag/ && !/<filter|<match/ { print "    tag: " $2 }
        in_block && /^[[:space:]]*format/ { print "    format: " $2 }
        in_block && /^[[:space:]]*buffer_path/ { print "    buffer_path: " $2 }
    ' "$file"
done

echo -e "\n=== 4. OSS Plugin Recommendations ==="
if [ ${#INCLUDED_FILES[@]} -gt 0 ]; then
    ALL_INCLUDED_CONTENT=$(cat "${INCLUDED_FILES[@]}" 2>/dev/null || true)
    
    if echo "$ALL_INCLUDED_CONTENT" | grep -q "@type google_cloud"; then
        echo "- Detected '@type google_cloud' output."
        echo "  -> Recommendation: Require 'fluent-plugin-google-cloud' OSS plugin."
    fi
    if echo "$ALL_INCLUDED_CONTENT" | grep -q "format systemd"; then
        echo "- Detected 'format systemd' parser."
        echo "  -> Recommendation: Require 'fluent-plugin-systemd' OSS plugin."
    fi
    if echo "$ALL_INCLUDED_CONTENT" | grep -q "format nginx" || echo "$ALL_INCLUDED_CONTENT" | grep -A1 "<parse>" | grep -q "@type nginx"; then
        echo "- Detected 'format nginx' or '@type nginx'."
        echo "  -> Recommendation: Fluentd core supports nginx out-of-the-box."
    fi
fi

echo -e "\n=== 5. Environment & Service Details ==="
echo "--- Service Status ---"
if systemctl status google-fluentd --no-pager 2>/dev/null; then
    echo "Service is running (systemctl)"
elif ps -ef | grep '[g]oogle-fluentd' | grep -v -E '(bash -s|discover_config|google-fluentd-migration)' >/dev/null 2>&1; then
    echo "Service process found (ps):"
    ps -ef | grep '[g]oogle-fluentd' | grep -v -E '(bash -s|discover_config|google-fluentd-migration)'
else
    echo "Service not found or inaccessible via systemctl or ps"
fi

echo -e "\n--- Google Fluentd Version ---"
google-fluentd --version 2>/dev/null || /opt/google-fluentd/embedded/bin/fluentd --version 2>/dev/null || echo "Version unknown"

echo -e "\n--- Embedded Ruby Version ---"
/opt/google-fluentd/embedded/bin/ruby -v 2>/dev/null || ruby -v 2>/dev/null || echo "Ruby not found"

echo -e "\n--- Installed Plugins ---"
/opt/google-fluentd/embedded/bin/fluent-gem list 2>/dev/null || fluent-gem list 2>/dev/null || echo "fluent-gem not found"

echo -e "\n=== 6. File & Path Permissions ==="
# Base directories
PATHS_TO_CHECK=("/etc/google-fluentd" "/var/log/google-fluentd" "/var/lib/google-fluentd" "/var/lib/google-fluentd/pos")

# Dynamically extract all log paths, pos files, and buffer paths from both the main config AND included configs
DYNAMIC_PATHS=$(awk '/^[[:space:]]*(path|pos_file|buffer_path)/ { print $2 }' "$MAIN_CONF" "${INCLUDED_FILES[@]}" 2>/dev/null | sort -u || true)
for p in $DYNAMIC_PATHS; do
    PATHS_TO_CHECK+=("$p")
done

echo "Checking permissions for base directories and discovered config paths:"
for p in "${PATHS_TO_CHECK[@]}"; do
    ls -ld $p 2>/dev/null || echo "Missing or inaccessible: $p"
done

echo -e "\n================================================"
echo " Discovery completed safely (Read-Only)."
