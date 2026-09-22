#!/bin/bash
set -eo pipefail

echo "================================================"
echo " Google Fluentd Migration Discovery "
echo "================================================"

read -p "Enter Permitted VM: " PERMITTED_VM
read -p "Enter GCP Project: " GCP_PROJECT
read -p "Enter Zone: " GCP_ZONE

TMP_OUT=$(mktemp)

echo ""
echo "=== Executing discovery on $PERMITTED_VM (streaming via SSH) ==="
if gcloud compute ssh "$PERMITTED_VM" --project="$GCP_PROJECT" --zone="$GCP_ZONE" --command="bash -s -- /etc/google-fluentd" < ./scripts/discover_config.sh | tee "$TMP_OUT"; then
    echo ""
    echo "=== Generating Migration Assessment Report ==="
    python3 ./scripts/generate_report.py "$PERMITTED_VM" "$GCP_PROJECT" "$GCP_ZONE" "$TMP_OUT" "migration_assessment.md"
    
    # Also update agent artifact directory if accessible
    BRAIN_DIR="${AGENT_WORKSPACE_DIR:-/tmp/agent_artifacts}"
    if [ -d "$BRAIN_DIR" ]; then
        cp migration_assessment.md "$BRAIN_DIR/migration_assessment.md" 2>/dev/null || true
    fi
    
    rm -f "$TMP_OUT"
    echo ""
    echo "================================================"
    echo " Discovery workflow completed successfully. "
    echo " Report written to: migration_assessment.md"
    echo "================================================"
else
    echo ""
    echo "ERROR: Discovery execution failed or incomplete. Previous report (if any) was not overwritten."
    rm -f "$TMP_OUT"
    exit 1
fi
