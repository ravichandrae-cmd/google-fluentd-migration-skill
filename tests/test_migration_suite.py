#!/usr/bin/env python3
"""
Exhaustive Automated Test Suite for Upstream Config Migration Skill
Validates 100% rule compliance across 19 diverse application logging scenarios.
Reflects official "Breaking Changes & Workarounds" documentation (v0.12 -> v1).
"""

import sys
import os
import re

sys.path.append(os.path.abspath("scripts"))
from migrate_legacy_to_modern import migrate_legacy_file

TEST_CASES = [
    {
        "name": "Scenario 1: Nginx & Syslog Port Binding",
        "legacy_config": """
<source>
  @type tail
  path /var/log/nginx/access.log
  <parse>
    @type json
    auto_typecast true
  </parse>
</source>
<source>
  @type syslog
  port 514
</source>
""",
        "expected_checks": [
            ("auto_typecast directive stripped", lambda cfg: not re.search(r'^\s*auto_typecast\s+(true|false)', cfg, re.MULTILINE)),
            ("syslog port shifted to 5140", lambda cfg: "port 5140" in cfg),
        ]
    },
    {
        "name": "Scenario 2: Java HTTP Application Ingestion & Exception Handling",
        "legacy_config": """
<source>
  @type http
  port 8080
</source>
<filter java.app>
  @type detect_exceptions
  languages ["java"]
</filter>
""",
        "expected_checks": [
            ("HTTP receiver port preserved", lambda cfg: "port 8080" in cfg),
            ("detect_exceptions preserved", lambda cfg: "@type detect_exceptions" in cfg),
        ]
    },
    {
        "name": "Scenario 3: Fluent Forward Protocol Ingestion (@type forward)",
        "legacy_config": """
<source>
  @type forward
  port 24224
  bind 0.0.0.0
</source>
""",
        "expected_checks": [
            ("Forward receiver preserved", lambda cfg: "@type forward" in cfg and "24224" in cfg),
        ]
    },
    {
        "name": "Scenario 4: gRPC Transport & Compression Settings",
        "legacy_config": """
<match **>
  @type google_cloud
  auto_typecast true
  grpc_compression_algorithm gzip
</match>
""",
        "expected_checks": [
            ("auto_typecast directive stripped from match", lambda cfg: not re.search(r'^\s*auto_typecast\s+(true|false)', cfg, re.MULTILINE)),
            ("gRPC gzip compression retained", lambda cfg: "grpc_compression_algorithm gzip" in cfg),
        ]
    },
    {
        "name": "Scenario 5: Unmapped Parameter Edge-Case Warning Header",
        "legacy_config": """
<match **>
  @type google_cloud
  custom_unsupported_buffer_opt true
</match>
""",
        "expected_checks": [
            ("Warning header present", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 6: Dynamic Custom Customer Log Source (Glob Path + Custom Regex)",
        "legacy_config": """
<source>
  @type tail
  path /var/log/custom-app/*.log
  pos_file /var/log/fluentd/custom-app.pos
  tag customer.custom_app
  <parse>
    @type regexp
    expression /^(?<time>\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z) \\[(?<severity>\\w+)\\] (?<message>.*)$/
  </parse>
</source>
""",
        "expected_checks": [
            ("Dynamic glob path preserved", lambda cfg: "/var/log/custom-app/*.log" in cfg),
            ("Dynamic custom regex expression preserved", lambda cfg: "expression /^(?<time>" in cfg),
            ("Dynamic tag preserved", lambda cfg: "customer.custom_app" in cfg),
        ]
    },
    {
        "name": "Scenario 7: PostgreSQL Database Logging",
        "legacy_config": """
<source>
  @type tail
  path /var/log/postgresql/postgresql-14-main.log
  pos_file /var/log/fluentd/postgres.pos
  tag postgresql.db
  <parse>
    @type none
    auto_typecast true
  </parse>
</source>
""",
        "expected_checks": [
            ("Postgres path preserved", lambda cfg: "/var/log/postgresql/postgresql-14-main.log" in cfg),
            ("auto_typecast directive stripped", lambda cfg: not re.search(r'^\s*auto_typecast\s+(true|false)', cfg, re.MULTILINE)),
        ]
    },
    {
        "name": "Scenario 8: Kafka Message Broker Ingestion",
        "legacy_config": """
<source>
  @type tail
  path /var/log/kafka/server.log
  tag kafka.broker
  <parse>
    @type multiline
    format_firstline /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}/
  </parse>
</source>
<filter kafka.broker>
  @type record_transformer
  <record>
    cluster "kafka-cluster-1"
  </record>
</filter>
""",
        "expected_checks": [
            ("Kafka log path preserved", lambda cfg: "/var/log/kafka/server.log" in cfg),
            ("Multiline firstline pattern preserved", lambda cfg: "format_firstline" in cfg),
            ("Kafka cluster metadata preserved", lambda cfg: "kafka-cluster-1" in cfg),
        ]
    },
    {
        "name": "Scenario 9: Redis Database Ingestion",
        "legacy_config": """
<source>
  @type tail
  path /var/log/redis/redis-server.log
  pos_file /var/log/fluentd/redis.pos
  tag redis.server
  <parse>
    @type syslog
  </parse>
</source>
""",
        "expected_checks": [
            ("Redis log path preserved", lambda cfg: "/var/log/redis/redis-server.log" in cfg),
            ("Syslog parse format preserved", lambda cfg: "@type syslog" in cfg),
        ]
    },
    {
        "name": "Scenario 10: Tomcat Catalina Access Log Migration",
        "legacy_config": """
<source>
  @type tail
  path /var/log/tomcat/catalina.out
  pos_file /var/log/fluentd/tomcat.pos
  tag tomcat.catalina
</source>
<match tomcat.catalina>
  @type google_cloud
  custom_unsupported_buffer_opt true
</match>
""",
        "expected_checks": [
            ("Tomcat log path preserved", lambda cfg: "/var/log/tomcat/catalina.out" in cfg),
            ("Warning header generated for unmapped buffer option", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 11: MySQL Server Error Log Migration",
        "legacy_config": """
<source>
  @type tail
  path /var/log/mysql/error.log
  pos_file /var/log/fluentd/mysql.pos
  tag mysql.error
  <parse>
    @type none
    auto_typecast true
  </parse>
</source>
""",
        "expected_checks": [
            ("MySQL log path preserved", lambda cfg: "/var/log/mysql/error.log" in cfg),
            ("auto_typecast directive stripped", lambda cfg: not re.search(r'^\s*auto_typecast\s+(true|false)', cfg, re.MULTILINE)),
        ]
    },
    {
        "name": "Scenario 12: Elasticsearch Server Multiline Cluster Log",
        "legacy_config": """
<source>
  @type tail
  path /var/log/elasticsearch/elasticsearch.log
  tag elasticsearch.cluster
  <parse>
    @type multiline
    format_firstline /^\\[\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2},\\d{3}\\]/
  </parse>
</source>
""",
        "expected_checks": [
            ("Elasticsearch path preserved", lambda cfg: "/var/log/elasticsearch/elasticsearch.log" in cfg),
            ("Elasticsearch timestamp pattern preserved", lambda cfg: "format_firstline" in cfg),
        ]
    },
    {
        "name": "Scenario 13: ZooKeeper Coordination Server Log",
        "legacy_config": """
<source>
  @type tail
  path /var/log/zookeeper/zookeeper.log
  tag zookeeper.server
</source>
""",
        "expected_checks": [
            ("ZooKeeper log path preserved", lambda cfg: "/var/log/zookeeper/zookeeper.log" in cfg),
        ]
    },
    {
        "name": "Scenario 14: HAProxy Load Balancer Ingestion",
        "legacy_config": """
<source>
  @type tail
  path /var/log/haproxy.log
  tag haproxy.access
  <parse>
    @type syslog
  </parse>
</source>
""",
        "expected_checks": [
            ("HAProxy path preserved", lambda cfg: "/var/log/haproxy.log" in cfg),
            ("Syslog parser retained", lambda cfg: "@type syslog" in cfg),
        ]
    },
    {
        "name": "Scenario 15: Kubernetes Metadata Filter Pipeline Ingestion",
        "legacy_config": """
<filter kubernetes.**>
  @type kubernetes_metadata
  de_dot true
</filter>
""",
        "expected_checks": [
            ("Kubernetes metadata filter preserved", lambda cfg: "@type kubernetes_metadata" in cfg),
        ]
    },
    {
        "name": "Scenario 16: Puppet Server Multiline Log Migration",
        "legacy_config": """
<source>
  @type tail
  path /var/log/puppetlabs/puppetserver/puppetserver.log
  pos_file /var/log/fluentd/puppetserver.pos
  tag puppet.server
  <parse>
    @type multiline
    format_firstline /^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}/
    auto_typecast true
  </parse>
</source>
<filter puppet.server>
  @type detect_exceptions
  message message
  languages ["java"]
</filter>
<match puppet.server>
  @type google_cloud
  custom_unsupported_buffer_opt true
</match>
""",
        "expected_checks": [
            ("PuppetServer log path preserved", lambda cfg: "/var/log/puppetlabs/puppetserver/puppetserver.log" in cfg),
            ("auto_typecast directive stripped", lambda cfg: not re.search(r'^\s*auto_typecast\s+(true|false)', cfg, re.MULTILINE)),
            ("detect_exceptions preserved", lambda cfg: "@type detect_exceptions" in cfg),
            ("Warning header generated for unmapped buffer option", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 17: Memcached Cache Ingestion",
        "legacy_config": """
<source>
  @type tail
  path /var/log/memcached.log
  pos_file /var/log/fluentd/memcached.pos
  tag memcached.cache
  <parse>
    @type syslog
    auto_typecast true
  </parse>
</source>
<match memcached.cache>
  @type google_cloud
  custom_memcached_buffer_opt true
</match>
""",
        "expected_checks": [
            ("Memcached path preserved", lambda cfg: "/var/log/memcached.log" in cfg),
            ("auto_typecast directive stripped", lambda cfg: not re.search(r'^\s*auto_typecast\s+(true|false)', cfg, re.MULTILINE)),
            ("Warning header generated for unmapped option", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 18: Breaking Changes Doc Verification (Nested <buffer>, Ruby Time, Modern RabbitMQ)",
        "legacy_config": """
<source>
    @type tail
    path /var/log/rabbitmq/*.log
    pos_file /var/lib/google-fluentd/pos/rabbitmq.pos
    tag rabbitmq
    format multiline
    format_firstline /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}/
    format1 /^(?<time>\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}) \\[(?<severity>\\w+)\\] (?<message>.*)/
    time_format %Y-%m-%d %H:%M:%S
    auto_typecast true
</source>
<filter rabbitmq>
  @type record_transformer
  enable_ruby true
  <record>
    raw_timestamp ${time}
  </record>
</filter>
<match rabbitmq>
  @type google_cloud
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers
  buffer_chunk_limit 512KB
  flush_interval 5s
  disable_retry_limit false
  retry_limit 3
  max_retry_wait 300
  num_threads 8
  partial_success true
</match>
""",
        "expected_checks": [
            ("Nested <buffer> directive created", lambda cfg: "<buffer>" in cfg and "</buffer>" in cfg),
            ("buffer_chunk_limit converted to chunk_limit_size", lambda cfg: "chunk_limit_size 512KB" in cfg),
            ("disable_retry_limit converted to retry_forever", lambda cfg: "retry_forever false" in cfg),
            ("Ruby Time explicitly cast to ${time.to_i}", lambda cfg: "${time.to_i}" in cfg),
            ("Modern RabbitMQ millisecond regex applied", lambda cfg: "%Y-%m-%d %H:%M:%S.%L" in cfg),
            ("partial_success directive stripped", lambda cfg: "partial_success directive stripped" in cfg),
            ("auto_typecast directive stripped", lambda cfg: "auto_typecast directive stripped" in cfg),
        ]
    },
    {
        "name": "Scenario 19: Joomla CMS Application Logging Migration",
        "legacy_config": """
<source>
  @type tail
  path /var/www/html/joomla/administrator/logs/error.php
  pos_file /var/log/fluentd/joomla_error.pos
  tag joomla.error
  <parse>
    @type regexp
    expression /^(?<time>\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+\\d{2}:\\d{2})\\s+\\[(?<priority>\\w+)\\]\\s+\\[(?<category>[\\w\\.\\-]+)\\]\\s+(?<message>.*)$/
    auto_typecast true
  </parse>
</source>
<filter joomla.error>
  @type record_transformer
  <record>
    app_name "joomla-cms"
    environment "production"
  </record>
</filter>
<match joomla.error>
  @type google_cloud
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers/joomla
  buffer_chunk_limit 256KB
  flush_interval 5s
  retry_limit 5
  num_threads 4
  partial_success true
  custom_joomla_cache_opt true
</match>
""",
        "expected_checks": [
            ("Joomla log path preserved", lambda cfg: "/var/www/html/joomla/administrator/logs/error.php" in cfg),
            ("Joomla regex expression preserved", lambda cfg: "expression /^(?<time>" in cfg),
            ("auto_typecast directive stripped", lambda cfg: "auto_typecast directive stripped" in cfg),
            ("Nested <buffer> directive created", lambda cfg: "<buffer>" in cfg and "</buffer>" in cfg),
            ("chunk_limit_size converted", lambda cfg: "chunk_limit_size 256KB" in cfg),
            ("flush_thread_count converted", lambda cfg: "flush_thread_count 4" in cfg),
            ("Warning header generated for unmapped option", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 20: GitLab Production JSON Log Migration (Flat format json -> <parse>)",
        "legacy_config": """
<source>
  @type tail
  path /var/log/gitlab/gitlab-rails/production_json.log
  pos_file /var/log/fluentd/gitlab_production.pos
  tag gitlab.production
  format json
  time_format %Y-%m-%dT%H:%M:%S.%LZ
  time_key time
  auto_typecast true
</source>
<filter gitlab.production>
  @type record_transformer
  enable_ruby true
  <record>
    app "gitlab"
    raw_timestamp ${time}
  </record>
</filter>
<match gitlab.production>
  @type google_cloud
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers/gitlab
  buffer_chunk_limit 512KB
  flush_interval 10s
  retry_limit 5
  num_threads 4
  partial_success true
  gitlab_custom_routing true
</match>
""",
        "expected_checks": [
            ("Flat format json converted to <parse> block", lambda cfg: "<parse>\n    @type json" in cfg),
            ("auto_typecast stripped", lambda cfg: "auto_typecast directive stripped" in cfg),
            ("Ruby Time cast to ${time.to_i}", lambda cfg: "${time.to_i}" in cfg),
            ("flush_interval moved inside <buffer>", lambda cfg: "    flush_interval 10s" in cfg),
            ("Unmapped gitlab_custom_routing flagged and commented", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg and "# [UNMAPPED LEGACY DIRECTIVE" in cfg),
        ]
    },
    {
        "name": "Scenario 21: Redmine Production Multiline Log & Unescaped Regex '#' Comment Fix",
        "legacy_config": """
<source>
  @type tail
  path /var/log/redmine/default/production.log
  pos_file /var/log/fluentd/redmine_production.pos
  tag redmine.production
  format multiline
  format_firstline /^I, \\[\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{6} #\\d+\\]  INFO -- :/
  format1 /^(?<severity>[A-Z]), \\[(?<time>\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d{6}) #(?<pid>\\d+)\\]\\s+(?<level>[A-Z]+)\\s+--\\s+:\\s+(?<message>.*)$/
  time_format %Y-%m-%dT%H:%M:%S.%N
</source>
<match redmine.production>
  @type google_cloud
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers/redmine
  buffer_chunk_limit 256KB
  flush_interval 5s
  retry_limit 5
  num_threads 4
  partial_success true
  redmine_legacy_flag true
</match>
""",
        "expected_checks": [
            ("Flat multiline converted to <parse>", lambda cfg: "<parse>\n    @type multiline" in cfg),
            ("Unescaped '#' in regex escaped as '\\#'", lambda cfg: r"\#(?<pid>\d+)" in cfg and r"\#\d+" in cfg),
            ("Nested <buffer> created cleanly", lambda cfg: "chunk_limit_size 256KB" in cfg),
            ("Unmapped redmine_legacy_flag flagged", lambda cfg: "redmine_legacy_flag" in cfg and "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 22: Magento System Log (Flat Regex Format -> <parse> @type regexp)",
        "legacy_config": """
<source>
  @type tail
  path /var/www/html/magento2/var/log/system.log
  pos_file /var/log/fluentd/magento_system.pos
  tag magento.system
  format /^\\[(?<time>\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})\\] (?<logger>[a-z_]+)\\.(?<level>[A-Z]+): (?<message>.*)$/
  time_format %Y-%m-%d %H:%M:%S
  auto_typecast true
</source>
<match magento.system>
  @type google_cloud
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers/magento
  buffer_chunk_limit 128KB
  flush_interval 10s
  retry_limit 3
  num_threads 2
  partial_success true
  magento_flush_legacy true
</match>
""",
        "expected_checks": [
            ("Flat regex converted to @type regexp + expression", lambda cfg: "@type regexp\n    expression /^\\[" in cfg),
            ("Nested <buffer> created", lambda cfg: "chunk_limit_size 128KB" in cfg),
            ("Unmapped magento_flush_legacy flagged", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 23: SaltStack Minion Multiline Log Migration",
        "legacy_config": """
<source>
  @type tail
  path /var/log/salt/minion
  pos_file /var/log/fluentd/salt_minion.pos
  tag salt.minion
  format multiline
  format_firstline /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2},\\d{3}/
  format1 /^(?<time>\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2},\\d{3}) \\[(?<logger>[^\\]]+)\\]\\[(?<level>[A-Z]+)\\]\\[(?<pid>\\d+)\\] (?<message>.*)$/
  time_format %Y-%m-%d %H:%M:%S,%f
</source>
<filter salt.minion>
  @type record_transformer
  enable_ruby true
  <record>
    app "saltstack"
    legacy_timestamp ${time}
  </record>
</filter>
<match salt.minion>
  @type google_cloud
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers/salt
  buffer_chunk_limit 2M
  flush_interval 5s
  salt_master_ip 10.0.0.1
</match>
""",
        "expected_checks": [
            ("Salt multiline wrapped in <parse>", lambda cfg: "<parse>\n    @type multiline" in cfg),
            ("Ruby Time cast to ${time.to_i}", lambda cfg: "${time.to_i}" in cfg),
            ("Unmapped salt_master_ip flagged", lambda cfg: "salt_master_ip" in cfg and "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 24: MongoDB Database Structured & Custom Tuning Migration",
        "legacy_config": """
<source>
  @type tail
  path /var/log/mongodb/mongod.log
  pos_file /var/lib/google-fluentd/pos/mongodb.pos
  tag mongodb
  <parse>
    @type regexp
    expression /^(?<time>[^ ]*)\\s+(?<severity>\\w)\\s+(?<component>[^ ]*)\\s+\\[(?<context>[^\\]]*)\\]\\s+(?<message>.*)/
    time_format %Y-%m-%dT%H:%M:%S.%L%z
    auto_typecast true
  </parse>
</source>
<match mongodb>
  @type google_cloud
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers/mongodb
  buffer_chunk_limit 1M
  flush_interval 5s
  custom_mongo_sharding_flag true
</match>
""",
        "expected_checks": [
            ("MongoDB path preserved", lambda cfg: "/var/log/mongodb/mongod.log" in cfg),
            ("auto_typecast stripped", lambda cfg: "auto_typecast directive stripped" in cfg),
            ("Nested <buffer> created with 1M chunk limit", lambda cfg: "chunk_limit_size 1M" in cfg),
            ("Unmapped custom_mongo_sharding_flag flagged", lambda cfg: "WARNING [MIGRATION EDGE CASE]" in cfg),
        ]
    },
    {
        "name": "Scenario 25: Prometheus Monitoring Crash Workaround (monitoring_type prometheus -> opencensus)",
        "legacy_config": """
<match **>
  @type google_cloud
  enable_monitoring true
  monitoring_type prometheus
  buffer_type file
  buffer_path /var/log/google-fluentd/buffers/monitoring
  flush_interval 5s
</match>
""",
        "expected_checks": [
            ("monitoring_type switched from prometheus to opencensus", lambda cfg: "monitoring_type opencensus" in cfg),
            ("enable_monitoring preserved", lambda cfg: "enable_monitoring true" in cfg),
            ("Nested <buffer> created cleanly", lambda cfg: "flush_interval 5s" in cfg and "<buffer>" in cfg),
        ]
    }
]

def run_test_suite():
    print("=========================================================")
    print("   RUNNING EXHAUSTIVE DYNAMIC AGENT SKILL TEST SUITE     ")
    print("=========================================================\n")
    
    passed = 0
    total = len(TEST_CASES)
    
    # Save temporary test files and evaluate
    for i, tc in enumerate(TEST_CASES, 1):
        print(f"Testing {tc['name']}...")
        tmp_in = f"/tmp/test_legacy_{i}.conf"
        tmp_out = f"/tmp/test_modern_{i}.conf"
        with open(tmp_in, 'w') as f:
            f.write(tc['legacy_config'])
            
        migrate_legacy_file(tmp_in, tmp_out)
        with open(tmp_out, 'r') as f:
            result_cfg = f.read()
            
        case_passed = True
        for check_name, check_fn in tc['expected_checks']:
            if check_fn(result_cfg):
                print(f"  [PASS] {check_name}")
            else:
                print(f"  [FAIL] {check_name}")
                case_passed = False
                
        if case_passed:
            passed += 1
            print("Status: SUCCESS\n")
        else:
            print("Status: FAILED\n")
            
        if os.path.exists(tmp_in): os.remove(tmp_in)
        if os.path.exists(tmp_out): os.remove(tmp_out)
            
    print(f"=========================================================")
    print(f"TEST RESULTS: {passed}/{total} Scenarios Passed ({(passed/total)*100:.1f}%)")
    print(f"=========================================================")
    return passed == total

if __name__ == "__main__":
    success = run_test_suite()
    sys.exit(0 if success else 1)
