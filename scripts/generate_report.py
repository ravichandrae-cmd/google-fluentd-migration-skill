#!/usr/bin/env python3
import sys
import re
from datetime import datetime, timezone

def parse_discovery_output(filepath):
    data = {
        "main_config": "Unknown",
        "include_patterns": "Unknown",
        "included_files": [],
        "sources": set(),
        "filters": set(),
        "matches": set(),
        "service_status": "Unknown",
        "fluentd_version": "Unknown",
        "ruby_version": "Unknown",
        "installed_plugins": [],
        "permissions": []
    }

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = [l.rstrip() for l in f]
    except Exception as e:
        print(f"Error reading discovery file: {e}", file=sys.stderr)
        return data

    current_section = None
    current_sub = None
    in_block = None

    for line in lines:
        if line.startswith("=== 1. Main Configuration File ==="):
            current_section = 1
            current_sub = None
            continue
        elif line.startswith("=== 2. @include Rules & Config Files ==="):
            current_section = 2
            current_sub = None
            continue
        elif line.startswith("=== 3. Extracted Key Fields"):
            current_section = 3
            current_sub = None
            continue
        elif line.startswith("=== 4. OSS Plugin Recommendations"):
            current_section = 4
            current_sub = None
            continue
        elif line.startswith("=== 5. Environment & Service Details"):
            current_section = 5
            current_sub = None
            continue
        elif line.startswith("=== 6. File & Path Permissions"):
            current_section = 6
            current_sub = None
            continue
        elif line.startswith("================================================"):
            continue

        if current_section == 1:
            if line.startswith("Found: "):
                data["main_config"] = line.split("Found: ", 1)[1].strip()
        elif current_section == 2:
            if line.startswith("Include patterns found in main config:"):
                current_sub = "patterns"
                continue
            elif line.startswith("--- Included Configuration Files ---"):
                current_sub = "included"
                continue
            elif line.startswith("--- Not Included"):
                current_sub = "not_included"
                continue

            if current_sub == "patterns" and line and not line.startswith("---"):
                data["include_patterns"] = line.strip()
            elif current_sub == "included" and line.startswith("[Included] "):
                data["included_files"].append(line.split("[Included] ", 1)[1].strip())
        elif current_section == 3:
            if "[Source block]" in line:
                in_block = "source"
            elif "[Filter block]" in line:
                in_block = "filter"
            elif "[Match block]" in line:
                in_block = "match"
            elif line.strip().startswith("type: "):
                t = line.strip().split("type: ", 1)[1].strip()
                if in_block == "source":
                    data["sources"].add(t)
                elif in_block == "filter":
                    data["filters"].add(t)
                elif in_block == "match":
                    data["matches"].add(t)
        elif current_section == 5:
            if line.startswith("--- Service Status ---"):
                current_sub = "service"
                continue
            elif line.startswith("--- Google Fluentd Version ---"):
                current_sub = "version"
                continue
            elif line.startswith("--- Embedded Ruby Version ---"):
                current_sub = "ruby"
                continue
            elif line.startswith("--- Installed Plugins ---"):
                current_sub = "plugins"
                continue

            if current_sub == "service" and line and not line.startswith("---"):
                data["service_status"] = line.strip()
            elif current_sub == "version" and line and not line.startswith("---"):
                data["fluentd_version"] = line.strip()
            elif current_sub == "ruby" and line and not line.startswith("---"):
                data["ruby_version"] = line.strip()
            elif current_sub == "plugins" and line and not line.startswith("---"):
                if line.startswith("fluent-") or line.startswith("fluentd"):
                    data["installed_plugins"].append(line.strip())
        elif current_section == 6:
            if line and not line.startswith("Checking permissions") and not line.startswith("================="):
                data["permissions"].append(line.strip())

    return data

def generate_markdown(vm, project, zone, data):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    sources_str = ", ".join(sorted(data["sources"])) if data["sources"] else "Unknown"
    filters_str = ", ".join(sorted(data["filters"])) if data["filters"] else "Unknown"
    matches_str = ", ".join(sorted(data["matches"])) if data["matches"] else "Unknown"

    included_md = "\n".join([f"  - `{f}`" for f in data["included_files"]]) if data["included_files"] else "  - Unknown"
    plugins_md = "\n".join([f"  - `{p}`" for p in data["installed_plugins"]]) if data["installed_plugins"] else "  - Unknown"
    perms_md = "\n".join([f"  - `{p}`" for p in data["permissions"]]) if data["permissions"] else "  - Unknown"

    md = f"""# Google Fluentd to OSS Fluentd Migration Assessment (Stage 2 Report)

**Report Generated:** {timestamp}

## Target Infrastructure
- **VM:** `{vm}`
- **GCP Project:** `{project}`
- **Zone:** `{zone}`

---

## 1. Discovered Facts
- **Service Status:** {data['service_status']}
- **Google Fluentd Version:** {data['fluentd_version']}
- **Embedded Ruby Version:** {data['ruby_version']}
- **Installed Plugins / Fluent Gems:**
{plugins_md}
- **Main Configuration:** `{data['main_config']}`
- **Include Patterns:** `{data['include_patterns']}`
- **Included Configuration Files:**
{included_md}
- **Source Plugins Used:** `{sources_str}`
- **Filter Plugins Used:** `{filters_str}`
- **Match / Output Plugins Used:** `{matches_str}`
- **File, Log, and State-Path Permissions:**
{perms_md}

---

## 2. Unknowns
- **Proprietary Filter Internal Transformations:** The exact runtime mutations performed by `analyze_config` and `add_insert_ids` on log events require behavioral analysis to determine if downstream consumers rely on specific fields or headers injected by them.
- **Service Restart & Ingestion Gaps:** Whether downstream log sinks or alerting pipelines rely on specific insert IDs generated by `add_insert_ids`.
- **Unincluded Configuration Files:** Any inactive `.bak` or unreferenced `.conf` files residing in `/etc/google-fluentd/config.d/` that are omitted from active `@include` evaluation.

---

## 3. Required OSS Plugins
- **`fluent-plugin-google-cloud`**: Essential replacement for `@type google_cloud` output blocks to ensure uninterrupted delivery to Google Cloud Logging.
- **`fluent-plugin-prometheus`**: Required to support `prometheus` and `prometheus_monitor` metrics source blocks.
- **`fluent-plugin-systemd`** *(if applicable)*: Recommended if systemd journal log formatting is introduced.

---

## 4. Compatibility Warnings
- **Proprietary Google Filters (`analyze_config`, `add_insert_ids`):** These filters do not exist in standard OSS Fluentd and are marked as **compatibility items requiring behavior analysis or an OSS equivalent so existing behavior is preserved**. Do not automatically remove them without verifying replacement logic.
- **Permission & Ownership Conflicts:** `google-fluentd` runs under `root:root` with state files in `/var/lib/google-fluentd/pos/` and `/var/log/google-fluentd/buffers/`. Standard OSS Fluentd daemon accounts (such as `fluentd` or `td-agent`) will encounter `Permission denied` errors unless state paths are isolated and ownerships are correctly assigned.
- **Embedded Ruby Environment:** Existing `google-fluentd` installations rely on embedded Ruby bundles; custom scripts or gems must be verified against the target OSS Fluentd Ruby environment.

---

## 5. Recommended Next Steps
1. **Stage 3 (OSS Config Generation & Compatibility Resolution):** Generate equivalent OSS Fluentd configuration files while conducting behavior analysis on `analyze_config` and `add_insert_ids` to implement OSS equivalents (e.g., via `record_transformer`, Lua, or native plugins) so that existing log processing behavior is strictly preserved.
2. **Path & Buffer Segregation:** Point all `pos_file` and `buffer_path` directives in the generated OSS configurations to dedicated OSS Fluentd state directories (e.g., `/var/log/fluentd/buffers` and `/var/lib/fluentd/pos`) to avoid concurrency locking with any running `google-fluentd` instances.
3. **Stage 4 (Pre-Migration Dry-Run):** Run `fluentd --dry-run` against the generated OSS configs to validate syntax, plugin availability, and file-access permissions prior to scheduling a controlled cutover.
"""
    return md

def main():
    if len(sys.argv) < 6:
        print("Usage: generate_report.py <vm> <project> <zone> <discovery_output_file> <report_output_file>", file=sys.stderr)
        sys.exit(1)

    vm = sys.argv[1]
    project = sys.argv[2]
    zone = sys.argv[3]
    discovery_file = sys.argv[4]
    report_file = sys.argv[5]

    data = parse_discovery_output(discovery_file)
    markdown_content = generate_markdown(vm, project, zone, data)

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    print(f"Successfully generated assessment report at {report_file}")

if __name__ == '__main__':
    main()
