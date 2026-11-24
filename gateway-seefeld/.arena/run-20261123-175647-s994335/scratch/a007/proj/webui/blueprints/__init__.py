"""
Flask blueprints for the JerumedNexus Gateway Web UI.

Each cohesive area (users, dead-letter queue, discovery, metrics) lives in
its own blueprint so ``webui/app.py`` stays a thin composition root.
"""

from webui.blueprints.dlq import dlq_bp
from webui.blueprints.metrics import metrics_bp
from webui.blueprints.users import users_bp
from webui.blueprints.discovery import discovery_bp
from webui.blueprints.inspect import inspect_bp
from webui.blueprints.wizard import wizard_bp
from webui.blueprints.topology import topology_bp
from webui.blueprints.wire_replay_bp import wire_replay_bp
from webui.blueprints.bulk_dlq import bulk_dlq_bp
from webui.blueprints.qr_onboarding import qr_bp
from webui.blueprints.golden_capture import golden_bp
from webui.blueprints.build_info import build_info_bp
from webui.blueprints.fleet_bp import fleet_bp
from webui.blueprints.verifica import verifica_bp

__all__ = ["dlq_bp", "metrics_bp", "users_bp", "discovery_bp", "inspect_bp",
           "wizard_bp", "topology_bp", "wire_replay_bp", "bulk_dlq_bp",
           "qr_bp", "golden_bp", "build_info_bp", "fleet_bp", "verifica_bp"]
