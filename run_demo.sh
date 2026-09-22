#!/usr/bin/env bash
set -e

echo "========================================================================="
echo " 🚀 GOOGLE-FLUENTD (v0.12) -> OSS FLUENTD (v1) MIGRATION SKILL DEMO"
echo "========================================================================="
echo ""
echo "1️⃣  STEP 1: Translating a sample Legacy google-fluentd config to OSS Fluentd v1..."
echo "   Input:  sample_legacy_configs/legacy_paulina_doc_example.conf"
echo "   Output: /tmp/demo_modern_fluentd.conf"
echo ""

python3 scripts/migrate_legacy_to_modern.py \
    sample_legacy_configs/legacy_paulina_doc_example.conf \
    /tmp/demo_modern_fluentd.conf

echo ""
echo "-------------------------------------------------------------------------"
echo " 📄 BEFORE (Legacy google-fluentd v0.12) vs. AFTER (Modern OSS Fluentd v1)"
echo "-------------------------------------------------------------------------"
echo ">>> BEFORE (sample_legacy_configs/legacy_paulina_doc_example.conf):"
cat sample_legacy_configs/legacy_paulina_doc_example.conf
echo ""
echo ">>> AFTER (/tmp/demo_modern_fluentd.conf):"
cat /tmp/demo_modern_fluentd.conf
echo "-------------------------------------------------------------------------"
echo ""
echo "2️⃣  STEP 2: Running Automated Verification Suite Across All 19 3P App Scenarios..."
echo ""
python3 tests/test_migration_suite.py
