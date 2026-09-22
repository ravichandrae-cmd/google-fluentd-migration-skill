#!/bin/bash
set -eo pipefail

echo "================================================"
echo " Google Fluentd to OSS Fluentd - Stage 3 Config Generator "
echo "================================================"

read -p "Generate from Remote VM via SSH (r) or Local Config Directory (l)? [r/l]: " MODE
MODE=${MODE:-r}

if [[ "$MODE" =~ ^[Rr]$ ]]; then
    read -p "Enter Target VM: " PERMITTED_VM
    read -p "Enter GCP Project: " GCP_PROJECT
    read -p "Enter Zone: " GCP_ZONE

    read -p "Enter Target OSS position-file directory [/var/lib/fluentd/pos]: " TARGET_POS_DIR
    TARGET_POS_DIR=${TARGET_POS_DIR:-/var/lib/fluentd/pos}

    read -p "Enter Target OSS buffer directory [/var/log/fluentd/buffers]: " TARGET_BUFFER_DIR
    TARGET_BUFFER_DIR=${TARGET_BUFFER_DIR:-/var/log/fluentd/buffers}

    STAGED_DIR="./staged_configs"
    mkdir -p -m 700 "$STAGED_DIR"

    echo ""
    echo "=== Streaming read-only snapshot from $PERMITTED_VM:/etc/google-fluentd ==="
    gcloud compute ssh "$PERMITTED_VM" --project="$GCP_PROJECT" --zone="$GCP_ZONE" --command="tar -czf - -C /etc/google-fluentd . 2>/dev/null" | tar -xzf - -C "$STAGED_DIR"
else
    read -p "Enter path to local config directory [tests/sample_configs]: " STAGED_DIR
    STAGED_DIR=${STAGED_DIR:-tests/sample_configs}

    read -p "Enter Target OSS position-file directory [/var/lib/fluentd/pos]: " TARGET_POS_DIR
    TARGET_POS_DIR=${TARGET_POS_DIR:-/var/lib/fluentd/pos}

    read -p "Enter Target OSS buffer directory [/var/log/fluentd/buffers]: " TARGET_BUFFER_DIR
    TARGET_BUFFER_DIR=${TARGET_BUFFER_DIR:-/var/log/fluentd/buffers}
fi

OUT_DIR="./generated_oss_configs"
REPORT_FILE="config_generation_report.md"
REVIEW_FILE="compatibility_review_items.md"

echo ""
echo "=== Transforming configurations into $OUT_DIR ==="
python3 ./scripts/generate_oss_config.py "$STAGED_DIR" "$OUT_DIR" "google-fluentd.conf" "$TARGET_POS_DIR" "$TARGET_BUFFER_DIR" "$REPORT_FILE" "$REVIEW_FILE"

# Also update agent artifact directory if accessible
BRAIN_DIR="/usr/local/google/home/ravichandrae/.gemini/jetski/brain/47003932-a0d8-4f4b-af6d-32d5d4847ab1"
if [ -d "$BRAIN_DIR" ]; then
    cp "$REPORT_FILE" "$BRAIN_DIR/$REPORT_FILE" 2>/dev/null || true
    cp "$REVIEW_FILE" "$BRAIN_DIR/$REVIEW_FILE" 2>/dev/null || true
fi

if [[ "$MODE" =~ ^[Rr]$ ]]; then
    echo ""
    read -p "Do you want to delete the staged client configs from $STAGED_DIR now? [Y/n]: " CLEANUP
    CLEANUP=${CLEANUP:-Y}
    if [[ "$CLEANUP" =~ ^[Yy]$ ]]; then
        rm -rf "$STAGED_DIR"
        echo "Staged directory $STAGED_DIR removed securely."
    else
        echo "Staged directory $STAGED_DIR retained with 700 permissions."
    fi
fi

echo ""
echo "================================================"
echo " Stage 3 Config Generation completed. "
echo " Generated OSS Configs: $OUT_DIR"
echo " Stage 3 Report: $REPORT_FILE"
echo " Compatibility Review Items: $REVIEW_FILE"
echo "================================================"
