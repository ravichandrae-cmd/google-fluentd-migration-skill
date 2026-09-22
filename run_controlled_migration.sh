#!/bin/bash
set -eo pipefail

echo "================================================"
echo " Google Fluentd to OSS Fluentd - Stage 5 Controlled Migration "
echo "================================================"

read -p "Enter path to generated OSS configs directory [./generated_oss_configs]: " CONFIG_DIR
CONFIG_DIR=${CONFIG_DIR:-./generated_oss_configs}

if [ ! -d "$CONFIG_DIR" ]; then
    echo "ERROR: Directory $CONFIG_DIR not found. Run Stage 3 config generation first."
    exit 1
fi

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
read -p "Select application number to migrate [1]: " APP_NUM
APP_NUM=${APP_NUM:-1}
IDX=$((APP_NUM-1))

if [ $IDX -lt 0 ] || [ $IDX -ge ${#CONFIGS[@]} ]; then
    echo "Invalid selection."
    exit 1
fi

SELECTED_CONF="config.d/$(basename "${CONFIGS[$IDX]}")"
APP_NAME=$(basename "${CONFIGS[$IDX]}")

echo ""
read -p "Execute migration on Remote VM via SSH (r) or Local Test Mode (l)? [r/l]: " MODE
MODE=${MODE:-r}

EXTRA_ARGS=()
if [[ "$MODE" =~ ^[Rr]$ ]]; then
    read -p "Enter Target VM: " PERMITTED_VM
    read -p "Enter GCP Project: " GCP_PROJECT
    read -p "Enter Zone: " GCP_ZONE
    EXTRA_ARGS=(--remote-vm "$PERMITTED_VM" --project "$GCP_PROJECT" --zone "$GCP_ZONE")
fi

echo ""
echo "=== Generating Stage 5 Execution Plan & Pre-Cutover Diffs ==="
python3 ./scripts/prepare_scoped_cutover_config.py "$CONFIG_DIR/google-fluentd.conf" "/tmp/fluentd_scoped_master.conf"
PLAN_JSON=$(python3 ./scripts/stage5_migration_engine.py "$CONFIG_DIR" "$SELECTED_CONF" "${EXTRA_ARGS[@]}")

echo ""
echo "================================================================="
echo " STAGE 5 CONTROLLED MIGRATION PLAN - TARGET: $APP_NAME "
echo "================================================================="
echo "$PLAN_JSON" | python3 -m json.tool

echo ""
echo "=== Configuration Diff (Conflict-Free Scoped OSS Master Config) ==="
diff -u "$CONFIG_DIR/google-fluentd.conf" "/tmp/fluentd_scoped_master.conf" || true

echo ""
echo "================================================================="
echo " APPROVAL GATE: The actions above will perform live cutover. "
echo "================================================================="
read -p "Do you approve and wish to execute this Stage 5 cutover on $PERMITTED_VM? [y/N]: " APPROVAL
APPROVAL=${APPROVAL:-N}

if [[ ! "$APPROVAL" =~ ^[Yy]$ ]]; then
    echo "Migration cutover cancelled by user. No system changes were made."
    exit 0
fi

echo ""
echo "=== Executing Approved Stage 5 Cutover for $APP_NAME ==="
REPORT_FILE="migration_execution_report.md"

python3 ./scripts/stage5_migration_engine.py "$CONFIG_DIR" "$SELECTED_CONF" \
    --execute \
    --scoped-master "/tmp/fluentd_scoped_master.conf" \
    --report "$REPORT_FILE" \
    "${EXTRA_ARGS[@]}"

# Sync with agent brain artifact directory if accessible
BRAIN_DIR="/usr/local/google/home/ravichandrae/.gemini/jetski/brain/47003932-a0d8-4f4b-af6d-32d5d4847ab1"
if [ -d "$BRAIN_DIR" ]; then
    cp "$REPORT_FILE" "$BRAIN_DIR/$REPORT_FILE" 2>/dev/null || true
fi

echo ""
echo "================================================"
echo " Stage 5 Migration Cutover Completed. "
echo " Migration Report generated at: $REPORT_FILE"
echo "================================================"
