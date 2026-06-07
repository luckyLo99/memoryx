from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memoryx.mcp import build_memoryx_tool_registry, bind_mcp_session
from memoryx.observability import DiagnosticsBundle, ProfileRunner, RetrievalDebugger, current_context
from memoryx.observability.metrics import default_metrics
from memoryx.security.maintenance import DatabaseMaintenance

from .artifacts import E2EArtifactBundle

@dataclass(frozen=True)
class E2ERunResult:
    ok: bool
    claim_id: str
    query_result_count: int
    retrieval_event_count: int
    artifacts: dict[str, str]
    metrics: dict[str, Any]
    trace: dict[str, Any]

class E2ERuntimeHarness:
    def __init__(self, db_path: str, artifact_dir: str):
        self.db_path = db_path
        self.artifacts = E2EArtifactBundle(Path(artifact_dir))

    def run_local_registry_e2e(self) -> E2ERunResult:
        token, trace_token = bind_mcp_session(
            session_id='e2e-session',
            agent_id='memoryx-e2e-agent',
            user_id='e2e-user',
            run_id='e2e-run',
            request_id='e2e-request',
        )

        default_metrics.reset()
        registry = build_memoryx_tool_registry(self.db_path)

        signal = registry.call(
            'memory.signal',
            {
                'event_type': 'user_message',
                'text': 'For MCP e2e tests, always prefer concise structured responses.',
                'metadata': {'source': 'phase14_e2e'},
                'session_id': 'e2e-session',
                'agent_id': 'memoryx-e2e-agent',
                'user_id': 'e2e-user',
            },
        )
        if not signal.ok:
            raise AssertionError(signal.error)
        claim_id = signal.data['claim_id']

        query = registry.call(
            'memory.query',
            {
                'query': 'concise structured MCP e2e responses',
                'limit': 6,
                'session_history': ['hello'],
                'session_id': 'e2e-session',
                'agent_id': 'memoryx-e2e-agent',
                'user_id': 'e2e-user',
            },
        )
        if not query.ok:
            raise AssertionError(query.error)

        debug = registry.call('memory.debug', {'query': 'concise structured', 'limit': 10})
        if not debug.ok:
            raise AssertionError(debug.error)

        stats = registry.call('memory.stats', {})
        if not stats.ok:
            raise AssertionError(stats.error)

        audit_path = self.artifacts.path('e2e_audit_export.json')
        audit = registry.call('memory.audit_export', {'output_path': audit_path, 'redact': True})
        if not audit.ok:
            raise AssertionError(audit.error)

        debug_path = self.artifacts.write_json('e2e_retrieval_debug.json', debug.data)
        diagnostics_path = self.artifacts.path('e2e_diagnostics.zip')
        DiagnosticsBundle(self.db_path).build(diagnostics_path, include_profile=False)

        profile_json = self.artifacts.path('e2e_profile.json')
        profile_md = self.artifacts.path('e2e_profile.md')
        ProfileRunner(self.db_path).run(records=20, queries=3, output_json=profile_json, output_md=profile_md)

        retrieval_event_count = DatabaseMaintenance(self.db_path).stats().get('retrieval_events') or 0
        query_result_count = len(query.data.get('instruction_context', [])) + len(query.data.get('evidence_context', []))

        metrics = default_metrics.snapshot()
        metrics_path = self.artifacts.write_json('e2e_metrics.json', metrics)
        trace = current_context()

        return E2ERunResult(
            ok=True,
            claim_id=claim_id,
            query_result_count=query_result_count,
            retrieval_event_count=retrieval_event_count,
            artifacts={
                'debug': debug_path,
                'diagnostics': diagnostics_path,
                'profile_json': profile_json,
                'profile_md': profile_md,
                'audit': audit_path,
                'metrics': metrics_path,
            },
            metrics=metrics,
            trace=trace,
        )

    def debug_retrieval_only(self, query: str = 'concise structured') -> dict[str, Any]:
        return RetrievalDebugger(self.db_path).debug_query(query, limit=10)
