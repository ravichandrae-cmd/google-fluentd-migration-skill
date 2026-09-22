#!/usr/bin/env python3
"""
End-to-End Migration Tool
Translates any legacy Fluentd/Ops Agent configuration into a modern upstream configuration based on SKILL.md rules.
Reflects official "Breaking Changes & Workarounds" documentation (v0.12 -> v1).
"""

import sys
import os
import re


def escape_unescaped_hash_in_regex(line):
    """
    Rule E / Rule 6: In Fluentd v1, an unescaped '#' inside a regex pattern is
    treated as an inline comment, truncating the line and causing a ConfigError.
    Escapes any unescaped '#' inside /.../ regex literals.
    """
    m = re.match(r'^(\s*(?:format\d*|format_firstline|expression)\s+/)(.*)(/\s*)$', line)
    if not m:
        return line, False
    prefix, body, suffix = m.groups()
    # Replace '#' not preceded by '\' with '\#'
    new_body, count = re.subn(r'(?<!\\)#', r'\\#', body)
    return prefix + new_body + suffix, (count > 0)


def convert_flat_source_parse(source_block):
    """
    Rule C: Converts flat v0.12 parser directives (format, format_firstline,
    format1..N, time_format, time_key, keep_time_key) inside a <source> block
    into a nested v1 <parse> block.
    """
    if '<parse>' in source_block:
        return source_block, False

    lines = source_block.splitlines()
    new_lines = []
    parse_lines = []
    converted = False

    parse_keys = ('format_firstline', 'time_format', 'time_key', 'keep_time_key')

    for line in lines:
        stripped = line.strip()
        # Check flat 'format <val>' (but not format_firstline or format1)
        m_fmt = re.match(r'^(\s*)format\s+(.+)$', line)
        if m_fmt:
            fmt_val = m_fmt.group(2).strip()
            converted = True
            if fmt_val.startswith('/') and fmt_val.endswith('/'):
                parse_lines.append("    @type regexp")
                parse_lines.append(f"    expression {fmt_val}")
            else:
                parse_lines.append(f"    @type {fmt_val}")
            continue

        # Check format1..N or parse_keys
        if re.match(r'^\s*(format\d+|' + '|'.join(parse_keys) + r')\s+', line):
            if converted or re.search(r'^\s*format\s+', source_block, re.MULTILINE):
                converted = True
                parse_lines.append(f"    {stripped}")
                continue

        # Check auto_typecast note if format was flat
        if '# NOTE: auto_typecast directive stripped' in line and (
            converted or re.search(r'^\s*format\s+', source_block, re.MULTILINE)
        ):
            parse_lines.append(f"    {stripped}")
            continue

        new_lines.append(line)

    if converted and parse_lines:
        # Insert <parse> block right before </source>
        final_lines = []
        for line in new_lines:
            if line.strip() == '</source>':
                final_lines.append("  <parse>")
                final_lines.extend(parse_lines)
                final_lines.append("  </parse>")
            final_lines.append(line)
        return "\n".join(final_lines), True

    return source_block, False


def migrate_legacy_file(input_path, output_path=None):
    if not os.path.exists(input_path):
        print(f"[ERROR] Input legacy config file '{input_path}' not found.")
        sys.exit(1)

    print(f"=== Reading Legacy Configuration: {input_path} ===")
    with open(input_path, 'r') as f:
        legacy_content = f.read()

    print("=== Applying SKILL.md v0.12 -> v1 Syntax Rules & Breaking Change Workarounds ===")
    migrated = legacy_content

    # 1. Strip auto_typecast directive
    if 'auto_typecast' in migrated:
        migrated = re.sub(
            r'^\s*auto_typecast\s+(true|false).*$',
            '    # NOTE: auto_typecast directive stripped (unsupported in v1 JSON parser)',
            migrated,
            flags=re.MULTILINE,
        )
        print("  [RULE APPLIED] Stripped unsupported 'auto_typecast' parameter.")

    # 2. Strip partial_success (permanently enabled in v1)
    if 'partial_success' in migrated:
        migrated = re.sub(
            r'^\s*partial_success\s+.*$',
            '  # NOTE: partial_success directive stripped (permanently enabled in v1)',
            migrated,
            flags=re.MULTILINE,
        )
        print("  [RULE APPLIED] Stripped 'partial_success' parameter (default in v1).")

    # 3. Ruby Time Object Explicit Casting (${time} -> ${time.to_i})
    if 'enable_ruby true' in migrated and '${time}' in migrated:
        migrated = migrated.replace('${time}', '${time.to_i}')
        print("  [RULE APPLIED] Explicitly cast Ruby Time object '${time}' to '${time.to_i}' for v1 buffer serialization.")

    # 4. Modern RabbitMQ Log Ingestion Regex
    if 'tag rabbitmq' in migrated or 'rabbitmq' in input_path:
        migrated = re.sub(
            r'format_firstline /.+/',
            r'format_firstline /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\.\\d{3}/',
            migrated,
        )
        migrated = re.sub(
            r'format1 /.+/',
            r'format1 /^(?<time>\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}\\.\\d{3}) \\[(?<severity>[^\\]]+)\\] <(?<pid>[^>]+)> (?m:(?<message>.*))$/',
            migrated,
        )
        migrated = re.sub(r'time_format .+', r'time_format %Y-%m-%d %H:%M:%S.%L', migrated)
        print("  [RULE APPLIED] Updated RabbitMQ parser regex to modern millisecond precision format.")

    # 5. Escape unescaped '#' in Regex patterns (Rule E / Rule 6)
    escaped_any_hash = False
    escaped_lines = []
    for line in migrated.splitlines():
        new_line, changed = escape_unescaped_hash_in_regex(line)
        if changed:
            escaped_any_hash = True
        escaped_lines.append(new_line)
    if escaped_any_hash:
        migrated = "\n".join(escaped_lines)
        print("  [RULE APPLIED] Escaped literal '#' as '\\#' in regex pattern to prevent v1 comment truncation.")

    # 6. Convert flat <source> format directives into nested <parse> block (Rule C)
    def replace_source(match):
        block = match.group(0)
        new_block, changed = convert_flat_source_parse(block)
        return new_block

    before_parse = migrated
    migrated = re.sub(r'<source>.*?</source>', replace_source, migrated, flags=re.DOTALL)
    if migrated != before_parse:
        print("  [RULE APPLIED] Converted flat 'format' directives into nested <parse> block.")

    # 7. Shift Syslog port 514 to 5140
    if 'port 514' in migrated and 'port 5140' not in migrated:
        migrated = re.sub(r'port 514(?!\d)', r'port 5140 # NOTE: Shifted to unprivileged port 5140', migrated)
        print("  [RULE APPLIED] Shifted Syslog port 514 to unprivileged port 5140.")

    # 7b. Convert monitoring_type prometheus to opencensus (Rule 9)
    if re.search(r'^\s*monitoring_type\s+prometheus\b', migrated, re.MULTILINE):
        migrated = re.sub(
            r'^(\s*)monitoring_type\s+prometheus\b.*$',
            r'\1monitoring_type opencensus # NOTE: Switched from prometheus to opencensus (avoids prometheus-client >= 0.10 crash)',
            migrated,
            flags=re.MULTILINE,
        )
        print("  [RULE APPLIED] Switched 'monitoring_type prometheus' to 'monitoring_type opencensus'.")

    # 8. Convert Flat Buffer Options to Nested <buffer> Block inside <match> (Rule B)
    buffer_params = {
        'buffer_type': '@type',
        'buffer_path': 'path',
        'buffer_chunk_limit': 'chunk_limit_size',
        'flush_interval': 'flush_interval',
        'disable_retry_limit': 'retry_forever',
        'retry_limit': 'retry_max_times',
        'retry_wait': 'retry_wait',
        'max_retry_wait': 'retry_max_interval',
        'num_threads': 'flush_thread_count',
    }

    buf_lines = []
    for line in migrated.splitlines():
        for old_param, new_param in buffer_params.items():
            if re.search(r'^\s*' + old_param + r'\s+', line):
                val = re.sub(r'^\s*' + old_param + r'\s+', '', line).strip()
                buf_lines.append(f"    {new_param} {val}")
                break

    if buf_lines:
        # Remove flat buffer lines from match body
        for old_param in buffer_params.keys():
            migrated = re.sub(r'^\s*' + old_param + r'\s+.*$\n?', '', migrated, flags=re.MULTILINE)

        buffer_block = "  <buffer>\n" + "\n".join(buf_lines) + "\n  </buffer>"
        # Insert <buffer> block right after @type google_cloud (or after <match> if no @type line)
        if re.search(r'(<match[^>]*>\s*\n\s*@type\s+\S+)', migrated):
            migrated = re.sub(r'(<match[^>]*>\s*\n\s*@type\s+\S+)', r'\1\n' + buffer_block, migrated)
        else:
            migrated = re.sub(r'(<match[^>]*>)', r'\1\n' + buffer_block, migrated)
        print("  [RULE APPLIED] Converted flat buffer options into nested <buffer> directive.")

    # 9. Ensure use_grpc setting in google_cloud match blocks right after @type google_cloud (Rule F)
    if '<match' in migrated and 'use_grpc' not in migrated:
        if re.search(r'(<match[^>]*>\s*\n\s*@type\s+\S+)', migrated):
            migrated = re.sub(
                r'(<match[^>]*>\s*\n\s*@type\s+\S+)',
                r'\1\n  use_grpc true\n  grpc_compression_algorithm gzip',
                migrated,
            )
        else:
            migrated = re.sub(r'(<match[^>]*>)', r'\1\n  use_grpc true\n  grpc_compression_algorithm gzip', migrated)
        print("  [RULE APPLIED] Added 'use_grpc true' & gzip compression transport settings.")

    # 10. Edge Case Warning Detection & Safe Isolation (Rule G)
    unmapped_pattern = r'^\s*((?:custom_\w+|\w+_custom_\w+|\w+_legacy(?:_\w+)?|salt_master_ip|analyze_config|add_insert_ids))\s+.*$'
    unmapped_params = re.findall(unmapped_pattern, legacy_content, flags=re.MULTILINE)
    if unmapped_params:
        # Safely comment out unmapped directives so Fluentd v1 does not crash on unknown keys
        migrated = re.sub(
            unmapped_pattern,
            lambda m: f"  # [UNMAPPED LEGACY DIRECTIVE COMMENTED FOR V1 SAFETY] {m.group(0).strip()}",
            migrated,
            flags=re.MULTILINE,
        )
        warn_block = "# WARNING [MIGRATION EDGE CASE]:\n"
        warn_block += "# The following legacy parameters could not be automatically mapped to upstream format:\n"
        for param in unmapped_params:
            warn_block += f"# - Parameter: '{param}'\n"
        warn_block += "# Action Required: Review upstream documentation for equivalent tuning options.\n\n"
        migrated = warn_block + migrated
        print(f"  [EDGE CASE WARN] Flagged {len(unmapped_params)} unmapped parameter(s) for human review.")

    if not output_path:
        output_path = os.path.join(os.path.dirname(input_path), "modern.config")

    with open(output_path, 'w') as f:
        f.write("# Upstream Migrated Configuration (v1 Standard)\n")
        f.write("# Generated automatically using upstream-config-migrator SKILL.md\n\n")
        f.write(migrated)

    print(f"\n[SUCCESS] Generated Modern Upstream Config: {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 migrate_legacy_to_modern.py <path_to_legacy_config> [output_path]")
        sys.exit(1)

    inp = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else None
    migrate_legacy_file(inp, outp)
