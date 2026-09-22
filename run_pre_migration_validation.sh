#!/bin/bash
set -eo pipefail

echo "================================================"
echo " Google Fluentd to OSS Fluentd - Stage 4 Pre-Migration Validation "
echo "================================================"

read -p "Enter path to generated OSS configs directory [./generated_oss_configs]: " CONFIG_DIR
CONFIG_DIR=${CONFIG_DIR:-./generated_oss_configs}

if [ ! -d "$CONFIG_DIR" ]; then
    echo "ERROR: Directory $CONFIG_DIR not found. Run Stage 3 config generation first."
    exit 1
fi

echo ""
echo "=== Select Migration Validation Scope ==="
echo "  [a] All Applications (Validate full configuration tree)"
echo "  [s] Select Specific Application(s) / Config(s)"
read -p "Select scope mode [a/s]: " SCOPE_CHOICE
SCOPE_CHOICE=${SCOPE_CHOICE:-a}

SCOPE_PARAM="all"
if [[ "$SCOPE_CHOICE" =~ ^[Ss]$ ]]; then
    echo ""
    echo "Available application configs in $CONFIG_DIR/config.d/:"
    CONFIGS=($(ls "$CONFIG_DIR/config.d/"*.conf 2>/dev/null || true))
    if [ ${#CONFIGS[@]} -eq 0 ]; then
        echo "No .conf files found in $CONFIG_DIR/config.d/."
        exit 1
    fi

    for i in "${!CONFIGS[@]}"; do
        echo "  $((i+1)). $(basename "${CONFIGS[$i]}")"
    done

    echo ""
    read -p "Enter number(s) comma-separated (e.g. 1 or 1,3) or filename: " SELECTION
    if [[ "$SELECTION" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        SELECTED_FILES=()
        IFS=',' read -ra ADDR <<< "$SELECTION"
        for num in "${ADDR[@]}"; do
            idx=$((num-1))
            if [ $idx -ge 0 ] && [ $idx -lt ${#CONFIGS[@]} ]; then
                SELECTED_FILES+=("config.d/$(basename "${CONFIGS[$idx]}")")
            fi
        done
        SCOPE_PARAM=$(IFS=','; echo "${SELECTED_FILES[*]}")
    else
        SCOPE_PARAM="$SELECTION"
    fi
fi

echo ""
read -p "Execute live dry-run on Remote VM via SSH (r) or Local Environment (l)? [r/l]: " DRY_MODE
DRY_MODE=${DRY_MODE:-r}

EXTRA_ARGS=()
if [[ "$DRY_MODE" =~ ^[Rr]$ ]]; then
    read -p "Enter Target VM: " PERMITTED_VM
    read -p "Enter GCP Project: " GCP_PROJECT
    read -p "Enter Zone: " GCP_ZONE
    EXTRA_ARGS=(--remote-vm "$PERMITTED_VM" --project "$GCP_PROJECT" --zone "$GCP_ZONE")
fi

REPORT_FILE="pre_migration_validation_report.md"

echo ""
echo "=== Running Pre-Migration Validation for Scope: $SCOPE_PARAM ==="
python3 ./scripts/validate_oss_config.py "$CONFIG_DIR" "google-fluentd.conf" "$SCOPE_PARAM" "$REPORT_FILE" "${EXTRA_ARGS[@]}"

# Sync with agent brain artifact directory if accessible
BRAIN_DIR="/usr/local/google/home/ravichandrae/.gemini/jetski/brain/47003932-a0d8-4f4b-af6d-32d5d4847ab1"
if [ -d "$BRAIN_DIR" ]; then
    cp "$REPORT_FILE" "$BRAIN_DIR/$REPORT_FILE" 2>/dev/null || true
fi

echo ""
echo "================================================"
echo " Stage 4 Pre-Migration Validation Completed. "
echo " Validation Report generated at: $REPORT_FILE"
echo "================================================"
