#!/usr/bin/env python3
import os
import json
from datetime import datetime, timezone

DEFAULT_CONTEXT_FILE = "migration_context.json"

class MigrationContext:
    """
    Client-generic, shared migration state engine that maintains context across
    all stages of the google-fluentd to OSS Fluentd migration lifecycle.
    """
    def __init__(self, context_file=DEFAULT_CONTEXT_FILE):
        self.context_file = context_file
        self.data = {
            "version": "1.0",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target": {
                "vm_name": None,
                "project_id": None,
                "zone": None,
                "connectivity_verified": False
            },
            "runtime_environment": {
                "oss_service_name": None,
                "daemon_user": None,
                "daemon_group": None,
                "oss_config_dir": None,
                "oss_include_dir": None,
                "oss_pos_dir": None,
                "oss_buffer_dir": None,
                "legacy_service_name": None,
                "legacy_config_dir": None,
                "legacy_pos_dir": None
            },
            "discovered_applications": [],
            "compatibility_assessment": {
                "resolved_directives": [],
                "hard_blockers": [],
                "required_plugins": []
            },
            "selected_migration_scope": {
                "application_conf": None,
                "scoped_master_conf": None,
                "dry_run_verified": False,
                "canary_info": None
            },
            "stage_status": {
                "stage1_discovery": "PENDING",
                "stage2_assessment": "PENDING",
                "stage3_config_generation": "PENDING",
                "stage4_pre_validation": "PENDING",
                "gate1_scope_approval": "PENDING",
                "gate2_cutover_approval": "PENDING",
                "stage5_cutover": "PENDING"
            },
            "overall_status": "PENDING",
            "artifacts": {
                "staged_configs_dir": None,
                "generated_configs_dir": None,
                "assessment_report": None,
                "config_generation_report": None,
                "compatibility_review_items": None,
                "pre_migration_validation_report": None,
                "migration_execution_report": None
            }
        }
        if os.path.exists(self.context_file):
            self.load()

    def load(self, path=None):
        target_path = path or self.context_file
        if os.path.isfile(target_path):
            with open(target_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def save(self, path=None):
        target_path = path or self.context_file
        self.data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def set_target(self, vm_name, project_id, zone, connectivity_verified=True):
        self.data["target"]["vm_name"] = vm_name
        self.data["target"]["project_id"] = project_id
        self.data["target"]["zone"] = zone
        self.data["target"]["connectivity_verified"] = connectivity_verified
        self.save()

    def update_runtime(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.data["runtime_environment"]:
                self.data["runtime_environment"][k] = v
        self.save()

    def set_discovered_applications(self, apps_list):
        self.data["discovered_applications"] = apps_list
        self.save()

    def update_compatibility(self, resolved=None, blockers=None, plugins=None):
        if resolved is not None:
            self.data["compatibility_assessment"]["resolved_directives"] = sorted(list(set(resolved)))
        if blockers is not None:
            self.data["compatibility_assessment"]["hard_blockers"] = sorted(list(set(blockers)))
        if plugins is not None:
            self.data["compatibility_assessment"]["required_plugins"] = sorted(list(set(plugins)))
        self.save()

    def set_scope(self, app_conf, scoped_master_conf=None, dry_run_verified=False, canary_info=None):
        self.data["selected_migration_scope"]["application_conf"] = app_conf
        if scoped_master_conf:
            self.data["selected_migration_scope"]["scoped_master_conf"] = scoped_master_conf
        if dry_run_verified is not None:
            self.data["selected_migration_scope"]["dry_run_verified"] = dry_run_verified
        if canary_info:
            self.data["selected_migration_scope"]["canary_info"] = canary_info
        self.save()

    def update_stage_status(self, stage_name, status):
        if stage_name in self.data["stage_status"]:
            self.data["stage_status"][stage_name] = status
            self.save()

    def set_artifact(self, key, path):
        if key in self.data["artifacts"]:
            self.data["artifacts"][key] = path
            self.save()

    def is_gate_approved(self, gate_name):
        return self.data["stage_status"].get(gate_name) == "APPROVED"

    def mark_completed(self):
        self.data["overall_status"] = "COMPLETED"
        self.data["stage_status"]["stage5_cutover"] = "COMPLETED"
        self.save()

