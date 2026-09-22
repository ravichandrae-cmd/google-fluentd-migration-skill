#!/usr/bin/env python3
import sys
import os
import re

def generate_conflict_free_master_config(master_conf_path, output_path, exclude_shared_listeners=True):
    """
    Generates a minimal, conflict-free OSS Fluentd master configuration that preserves
    the known-good OSS pattern (@include conf.d/*.conf / config.d/*.conf) without introducing
    unnecessary legacy catch-all matchers, OpenCensus monitoring, deprecated parameters,
    or port listeners that conflict with google-fluentd.
    """
    lines = [
        "# ====================================================================\n",
        "# OSS Fluentd Master Configuration (Selective Coexistence Scope)\n",
        "# Preserves known-good OSS pattern with single include path\n",
        "# ====================================================================\n",
        "\n",
        "# Include modular application configurations from standard OSS conf.d directory\n",
        "@include /etc/fluent/conf.d/*.conf\n",
        "\n"
    ]

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    return True

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: prepare_scoped_cutover_config.py <master_conf_input> <output_path>", file=sys.stderr)
        sys.exit(1)

    success = generate_conflict_free_master_config(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
