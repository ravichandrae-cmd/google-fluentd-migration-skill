#!/usr/bin/env python3
import sys
import os
import re
import glob
from datetime import datetime, timezone

# Known standard core & widely supported plugins in OSS Fluentd
KNOWN_SUPPORTED_PLUGINS = {
    # Core input plugins
    "tail", "in_tail", "http", "in_http", "forward", "in_forward", 
    "dummy", "in_dummy", "syslog", "in_syslog", "tcp", "in_tcp", 
    "udp", "in_udp", "unix", "in_unix", "exec", "in_exec", 
    "sample", "in_sample", "windows_eventlog", "debug_agent", "monitor_agent",
    
    # Core filter plugins
    "record_transformer", "filter_record_transformer", "grep", "filter_grep", 
    "parser", "filter_parser", "stdout", "filter_stdout", "record_modifier", "filter_record_modifier",
    
    # Core output / match plugins
    "null", "out_null", "stdout", "out_stdout", "file", "out_file", 
    "forward", "out_forward", "copy", "out_copy", "roundrobin", "out_roundrobin", 
    "exec", "out_exec", "exec_filter", "out_exec_filter", "relabel", "out_relabel",
    
    # Common Community / GCP plugins
    "google_cloud", "out_google_cloud",
    "prometheus", "in_prometheus", "prometheus_monitor", "in_prometheus_monitor", 
    "prometheus_output_monitor", "prometheus_tail_monitor",
    "systemd", "in_systemd",
    "rewrite_tag_filter", "detect_exceptions", "concat",
    "kubernetes_metadata_filter", "kubernetes_metadata",
    "multi_format_parser", "s3", "sql", "webhdfs", "record_reformer"
}

PROPRIETARY_PLUGINS = {
    "analyze_config": "Proprietary google-fluentd telemetry filter not supported in OSS Fluentd.",
    "add_insert_ids": "Proprietary google-fluentd deduplication filter not supported in OSS Fluentd."
}

class FluentdBlock:
    def __init__(self, tag_name, tag_arg, open_line, start_line_num):
        self.tag_name = tag_name.lower()
        self.tag_arg = tag_arg.strip() if tag_arg else ""
        self.open_line = open_line
        self.start_line_num = start_line_num
        self.end_line_num = None
        self.close_line = None
        self.lines = [open_line]
        self.plugin_type = None

def resolve_include_chain(stage_dir, main_conf_rel):
    """
    Recursively resolve all @include files starting from main_conf_rel inside stage_dir.
    Returns a set of absolute file paths that are active in the configuration.
    """
    active_files = set()
    to_visit = [os.path.normpath(os.path.join(stage_dir, main_conf_rel))]

    while to_visit:
        curr = to_visit.pop()
        if curr in active_files or not os.path.isfile(curr):
            continue
        active_files.add(curr)

        try:
            with open(curr, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception:
            continue

        for line in lines:
            line_str = line.strip()
            if line_str.startswith("@include "):
                pattern = line_str.split("@include ", 1)[1].strip()
                if not os.path.isabs(pattern):
                    pattern_path = os.path.join(stage_dir, pattern)
                else:
                    rel_part = pattern.lstrip('/')
                    parts = rel_part.split('/')
                    if len(parts) > 2 and parts[0] == 'etc' and 'fluentd' in parts[1]:
                        rel_part = os.path.join(*parts[2:])
                    pattern_path = os.path.join(stage_dir, rel_part)

                matched = glob.glob(pattern_path)
                for m in matched:
                    if os.path.isfile(m) and m not in active_files:
                        to_visit.append(m)

    return active_files

def parse_file_blocks(lines):
    """
    Groups configuration lines into raw strings and FluentdBlock objects.
    """
    items = []
    stack = []

    for idx, line in enumerate(lines, start=1):
        m_open = re.match(r'^[ \t]*<([a-zA-Z0-9_]+)(?:\s+([^>]*))?>', line)
        m_close = re.match(r'^[ \t]*<\/([a-zA-Z0-9_]+)>', line)

        if m_close:
            close_tag = m_close.group(1).lower()
            if stack and stack[-1].tag_name == close_tag:
                top = stack.pop()
                top.close_line = line
                top.end_line_num = idx
                top.lines.append(line)
                if not stack:
                    items.append(top)
                else:
                    stack[-1].lines.append(line)
                continue
            elif stack:
                stack[-1].lines.append(line)
                continue
            else:
                items.append(line)
                continue

        if m_open:
            open_tag = m_open.group(1).lower()
            # If inside a plugin block and encounter a parameter sub-block (<parse>, <buffer>, etc.), keep it inside current block
            if stack and stack[-1].tag_name in ("source", "filter", "match") and open_tag in ("parse", "buffer", "record", "format", "inject", "secondary", "extract"):
                stack[-1].lines.append(line)
                continue

            block = FluentdBlock(open_tag, m_open.group(2), line, idx)
            if stack:
                stack[-1].lines.append(line)
            stack.append(block)
            continue

        if stack:
            stack[-1].lines.append(line)
        else:
            items.append(line)

    while stack:
        b = stack.pop(0)
        items.append(b)

    return items

def check_block_support(block):
    if block.tag_name not in ("source", "filter", "match"):
        return True, None

    for line in block.lines:
        m = re.match(r'^[ \t]*(@type|type)\s+([^\s#]+)', line)
        if m:
            block.plugin_type = m.group(2).strip()
            break

    if not block.plugin_type:
        return True, None

    ptype = block.plugin_type
    if ptype in PROPRIETARY_PLUGINS:
        return False, PROPRIETARY_PLUGINS[ptype]

    if ptype not in KNOWN_SUPPORTED_PLUGINS:
        return False, f"Unknown or custom plugin '{ptype}' not present in standard OSS Fluentd distribution."

    return True, None

def transform_file_content(lines, rel_path, target_pos_dir, target_buffer_dir):
    """
    Transforms lines of a config file:
    - Entire block commenting for unsupported / proprietary plugins
    - Syntax upgrade (format -> <parse>)
    - Path remapping (pos_file, buffer_path)
    Returns: (new_lines, has_compatibility_items, review_items, path_remaps, syntax_upgrades, required_plugins, unchanged_settings)
    """
    parsed_items = parse_file_blocks(lines)

    new_lines = []
    has_compatibility_items = False
    review_items = []
    path_remaps = []
    syntax_upgrades = []
    required_plugins = set()
    unchanged_settings = []

    for item in parsed_items:
        if isinstance(item, str):
            stripped = item.strip()
            # Remap pos_file or buffer_path outside blocks if any
            if stripped.startswith("pos_file "):
                old_pos = stripped.split("pos_file ", 1)[1].strip()
                filename = os.path.basename(old_pos)
                new_pos = os.path.join(target_pos_dir, filename)
                path_remaps.append({"type": "pos_file", "old": old_pos, "new": new_pos, "file": rel_path})
                indent = item[:len(item) - len(item.lstrip())]
                new_lines.append(f"{indent}pos_file {new_pos}\n")
            elif stripped.startswith("buffer_path "):
                old_buf = stripped.split("buffer_path ", 1)[1].strip()
                new_buf = target_buffer_dir
                path_remaps.append({"type": "buffer_path", "old": old_buf, "new": new_buf, "file": rel_path})
                indent = item[:len(item) - len(item.lstrip())]
                new_lines.append(f"{indent}buffer_path {new_buf}\n")
            else:
                new_lines.append(item)
            continue

        block = item
        is_supported, reason = check_block_support(block)

        if not is_supported:
            has_compatibility_items = True
            raw_block_str = "".join(block.lines)
            end_ln = block.end_line_num if block.end_line_num else (block.start_line_num + len(block.lines) - 1)
            review_items.append({
                "file": rel_path,
                "start_line": block.start_line_num,
                "end_line": end_ln,
                "block_tag": f"<{block.tag_name}{' ' + block.tag_arg if block.tag_arg else ''}>",
                "plugin_type": block.plugin_type or "unknown",
                "reason": reason,
                "raw_block": raw_block_str
            })

            # Comment out the ENTIRE block safely
            new_lines.append(f"### [MANUAL REVIEW REQUIRED] COMPATIBILITY ITEM - {block.plugin_type} ###\n")
            for raw_l in block.lines:
                r_str = raw_l.rstrip('\r\n')
                if not r_str.strip():
                    new_lines.append("#\n")
                else:
                    new_lines.append(f"# {r_str}\n")
            new_lines.append("### END [MANUAL REVIEW REQUIRED] ###\n")
            continue

        # Supported block processing
        unchanged_settings.append(f"{rel_path}: <{block.tag_name}{' ' + block.tag_arg if block.tag_arg else ''}>")

        # Plugin dependency detection
        if block.plugin_type == "google_cloud":
            required_plugins.add("fluent-plugin-google-cloud")
        elif block.plugin_type in ("prometheus", "prometheus_monitor", "prometheus_output_monitor", "prometheus_tail_monitor"):
            required_plugins.add("fluent-plugin-prometheus")
        elif block.plugin_type == "systemd":
            required_plugins.add("fluent-plugin-systemd")
        elif block.plugin_type == "rewrite_tag_filter":
            required_plugins.add("fluent-plugin-rewrite-tag-filter")
        elif block.plugin_type == "detect_exceptions":
            required_plugins.add("fluent-plugin-detect-exceptions")
        elif block.plugin_type == "concat":
            required_plugins.add("fluent-plugin-concat")
        elif block.plugin_type == "kubernetes_metadata_filter":
            required_plugins.add("fluent-plugin-kubernetes_metadata_filter")

        # Line-by-line processing inside supported block
        for idx_in_block, bline in enumerate(block.lines):
            bstripped = bline.strip()
            curr_line_num = block.start_line_num + idx_in_block

            # Remap pos_file
            if bstripped.startswith("pos_file "):
                old_pos = bstripped.split("pos_file ", 1)[1].strip()
                filename = os.path.basename(old_pos)
                new_pos = os.path.join(target_pos_dir, filename)
                path_remaps.append({"type": "pos_file", "old": old_pos, "new": new_pos, "file": rel_path})
                indent = bline[:len(bline) - len(bline.lstrip())]
                new_lines.append(f"{indent}pos_file {new_pos}\n")
                continue

            # Remap buffer_path
            if bstripped.startswith("buffer_path "):
                old_buf = bstripped.split("buffer_path ", 1)[1].strip()
                new_buf = target_buffer_dir
                path_remaps.append({"type": "buffer_path", "old": old_buf, "new": new_buf, "file": rel_path})
                indent = bline[:len(bline) - len(bline.lstrip())]
                new_lines.append(f"{indent}buffer_path {new_buf}\n")
                continue

            # Upgrade legacy format syntax inside <source>
            if block.tag_name == "source" and bstripped.startswith("format "):
                fmt_val = bstripped.split("format ", 1)[1].strip()
                syntax_upgrades.append({"file": rel_path, "line": curr_line_num, "old": bstripped, "new": f"<parse> @type {fmt_val} </parse>"})
                indent = bline[:len(bline) - len(bline.lstrip())]
                new_lines.append(f"{indent}<parse>\n")
                new_lines.append(f"{indent}  @type {fmt_val}\n")
                new_lines.append(f"{indent}</parse>\n")
                continue

            new_lines.append(bline)

    if has_compatibility_items:
        banner = "# STATUS: [NOT MIGRATION-READY] - Contains commented proprietary/unknown directives requiring review.\n"
        new_lines.insert(0, banner)
    else:
        banner = "# STATUS: [MIGRATION-READY] - Converted to OSS Fluentd syntax.\n"
        new_lines.insert(0, banner)

    return new_lines, has_compatibility_items, review_items, path_remaps, syntax_upgrades, required_plugins, unchanged_settings

def generate_reports(report_file, review_file, all_review_items, all_remaps, all_upgrades, all_plugins, all_unchanged, overall_ready):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_str = "**OVERALL STATUS: MIGRATION-READY**" if overall_ready else "**OVERALL STATUS: NOT MIGRATION-READY (Review Required)**"

    # Write review artifact
    with open(review_file, 'w', encoding='utf-8') as rf:
        rf.write(f"# Google Fluentd to OSS Fluentd - Compatibility Review Items\n\n")
        rf.write(f"**Generated:** {timestamp}\n\n")
        rf.write(f"**Status:** {status_str}\n\n")
        rf.write("The following proprietary or unknown Fluentd blocks were detected during Stage 3 config generation. To prevent startup crashes, each block was commented out in full within the generated OSS Fluentd configurations and preserved below for behavior analysis and review.\n\n")
        
        if not all_review_items:
            rf.write("*No manual review compatibility items detected.*\n")
        else:
            for idx, item in enumerate(all_review_items, start=1):
                rf.write(f"### Item {idx}: `{item['block_tag']}` in `{item['file']}` (Lines {item['start_line']}-{item['end_line']})\n")
                rf.write(f"- **Plugin Type:** `{item['plugin_type']}`\n")
                rf.write(f"- **Reason:** {item['reason']}\n")
                if item['plugin_type'] == 'analyze_config':
                    rf.write(f"- **Action / Equivalent:** Proprietary internal configuration telemetry filter. In OSS Fluentd, metrics can be collected via `fluent-plugin-prometheus` or removed.\n")
                elif item['plugin_type'] == 'add_insert_ids':
                    rf.write(f"- **Action / Equivalent:** Injects unique insert IDs for Cloud Logging deduplication. In OSS Fluentd, this can be handled via `fluent-plugin-google-cloud` built-in `auto_insert_id` or `record_transformer` UUID generation.\n")
                else:
                    rf.write(f"- **Action / Equivalent:** Confirm if this custom plugin gem is available and compatible with the target OSS Fluentd Ruby environment.\n")
                rf.write("\n**Original Unmodified Block:**\n```apache\n")
                rf.write(item['raw_block'])
                if not item['raw_block'].endswith('\n'):
                    rf.write('\n')
                rf.write("```\n\n---\n\n")

    # Write stage 3 report
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# Google Fluentd to OSS Fluentd - Stage 3 Config Generation Report\n\n")
        f.write(f"**Generated:** {timestamp}\n\n")
        f.write(f"{status_str}\n\n")

        f.write("## 1. Migration Readiness Status\n")
        if overall_ready:
            f.write("All recursively referenced configuration files were successfully transformed into valid OSS Fluentd v1 syntax without unresolved proprietary directives.\n\n")
        else:
            f.write("One or more generated configuration files contain commented proprietary/unsupported blocks (`analyze_config`, `add_insert_ids`) requiring manual compatibility review before cutover. See `compatibility_review_items.md` for full original blocks.\n\n")

        f.write("## 2. Required OSS Fluentd Plugins\n")
        if not all_plugins:
            f.write("- Standard OSS Fluentd core plugins only.\n\n")
        else:
            for p in sorted(all_plugins):
                f.write(f"- `{p}` (install via `fluent-gem install {p}` or package manager)\n")
            f.write("\n")

        f.write("## 3. Path Remappings (`pos_file` & `buffer_path`)\n")
        if not all_remaps:
            f.write("*No path remappings required.*\n\n")
        else:
            f.write("| Config File | Directive Type | Old Path | New Target OSS Path |\n")
            f.write("| :--- | :--- | :--- | :--- |\n")
            for r in all_remaps:
                f.write(f"| `{r['file']}` | `{r['type']}` | `{r['old']}` | `{r['new']}` |\n")
            f.write("\n")

        f.write("## 4. Legacy Syntax Upgrades (Fluentd v1)\n")
        if not all_upgrades:
            f.write("*No legacy syntax upgrades needed.*\n\n")
        else:
            f.write("| Config File | Line | Old Syntax | Modern v1 Syntax |\n")
            f.write("| :--- | :--- | :--- | :--- |\n")
            for u in all_upgrades:
                f.write(f"| `{u['file']}` | {u['line']} | `{u['old']}` | `{u['new'].replace(chr(10), ' ')}` |\n")
            f.write("\n")

        f.write("## 5. Unsupported / Manual-Review Compatibility Items\n")
        if not all_review_items:
            f.write("*No unsupported directives found.*\n\n")
        else:
            f.write(f"Found {len(all_review_items)} proprietary/unsupported blocks requiring review. See separate artifact `compatibility_review_items.md` for the complete audit.\n\n")

        f.write("## 6. Unchanged Directives & Settings (Transferred 1:1)\n")
        for u in all_unchanged[:20]:
            f.write(f"- `{u}`\n")
        if len(all_unchanged) > 20:
            f.write(f"- *...and {len(all_unchanged) - 20} more standard blocks.*\n")
        f.write("\n")

def main():
    if len(sys.argv) < 8:
        print("Usage: generate_oss_config.py <staged_dir> <output_dir> <main_conf_rel> <target_pos_dir> <target_buffer_dir> <report_file> <review_file>", file=sys.stderr)
        sys.exit(1)

    staged_dir = os.path.abspath(sys.argv[1])
    output_dir = os.path.abspath(sys.argv[2])
    main_conf_rel = sys.argv[3]
    target_pos_dir = sys.argv[4]
    target_buffer_dir = sys.argv[5]
    report_file = sys.argv[6]
    review_file = sys.argv[7]

    if not os.path.exists(staged_dir):
        print(f"Error: Staged config directory {staged_dir} does not exist.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    active_files = resolve_include_chain(staged_dir, main_conf_rel)
    if not active_files:
        print(f"Error: No active files resolved from {main_conf_rel} in {staged_dir}.", file=sys.stderr)
        sys.exit(1)

    all_review_items = []
    all_remaps = []
    all_upgrades = []
    all_plugins = set()
    all_unchanged = []
    overall_ready = True

    for abs_path in sorted(active_files):
        rel_path = os.path.relpath(abs_path, staged_dir)
        target_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading {abs_path}: {e}", file=sys.stderr)
            continue

        new_lines, has_compat, review_items, path_remaps, syntax_upgrades, required_plugins, unchanged_settings = transform_file_content(
            lines, rel_path, target_pos_dir, target_buffer_dir
        )

        if has_compat:
            overall_ready = False

        all_review_items.extend(review_items)
        all_remaps.extend(path_remaps)
        all_upgrades.extend(syntax_upgrades)
        all_plugins.update(required_plugins)
        all_unchanged.extend(unchanged_settings)

        with open(target_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    generate_reports(report_file, review_file, all_review_items, all_remaps, all_upgrades, all_plugins, all_unchanged, overall_ready)
    print(f"Successfully transformed {len(active_files)} active configuration files into {output_dir}")
    print(f"Stage 3 Report generated at: {report_file}")
    print(f"Review Artifact generated at: {review_file}")

if __name__ == '__main__':
    main()
