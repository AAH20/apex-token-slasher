"""Unit tests for Hermes, Cognee, Hindsight, and Swarm integrations."""

import unittest
from apex_token_slasher.core.models import ChunkKind, GatingAction
from apex_token_slasher.integrations.cognee_bridge import CogneeGraphBridge
from apex_token_slasher.integrations.hindsight_distiller import HindsightMemoryDistiller
from apex_token_slasher.integrations.laya_clef_gate import LayaClefFastGate
from apex_token_slasher.integrations.nerve_supervisor import NerveSupervisorBridge
from apex_token_slasher.integrations.swarm_bridge import SwarmAgentRole, SwarmTokenBudgetBridge


class TestIntegrations(unittest.TestCase):
    def test_laya_clef_fast_gate_latency_and_routing(self) -> None:
        gate = LayaClefFastGate(bypass_token_threshold=1000, full_slash_token_threshold=5000)

        # 1. Under-budget prompt: BYPASS
        short_prompt = "Hello, summarize this function."
        verdict_short = gate.evaluate(short_prompt)
        self.assertEqual(verdict_short.action, GatingAction.BYPASS)
        self.assertLess(verdict_short.gate_latency_us, 50.0)  # sub-50µs SLA

        # 2. Large code prompt: AST_PRUNE or FULL_SLASH
        large_code = "def process(): pass\nclass Handler: pass\n" * 300
        verdict_code = gate.evaluate(large_code)
        self.assertIn(verdict_code.action, (GatingAction.AST_PRUNE, GatingAction.FULL_SLASH))
        self.assertLess(verdict_code.gate_latency_us, 50.0)

    def test_nerve_supervisor_dod_budget(self) -> None:
        nerve = NerveSupervisorBridge()
        budget_spec = nerve.enforce_dod_budget(requested_tokens=90000, locked_budget=70000)
        self.assertLessEqual(budget_spec.max_tokens, 65000)

    def test_cognee_graph_bridge(self) -> None:
        bridge = CogneeGraphBridge()
        entities = [
            {"id": "auth_service", "name": "AuthService", "type": "class", "relationships": ["verify_jwt"]},
            {"id": "verify_jwt", "name": "verify_jwt", "type": "function", "relationships": []},
        ]
        bridge.register_entities(entities)
        entries = bridge.extract_ast_entry_points("please inspect the AuthService authentication flow")

        self.assertIn("AuthService", entries)
        self.assertIn("verify_jwt", entries)

        chunk = bridge.build_cognee_graph_chunk(entries)
        self.assertIn("COGNEE_GRAPH_PROJECTION", chunk.content)
        self.assertTrue(chunk.is_pinned)

    def test_hindsight_memory_distiller(self) -> None:
        distiller = HindsightMemoryDistiller()
        raw_memories = [
            "In session 3 the user mentioned that they prefer Python 3.10 standard library only",
            "The agent observed that port 8080 is reserved for local proxy",
            "Remember that strict KaTeX syntax is required for README formulas",
        ]
        chunk = distiller.distill_to_chunk(raw_memories, bank_name="preferences")
        self.assertIn("Python 3.10 standard library only", chunk.content)
        self.assertIn("Port 8080 is reserved", chunk.content)
        self.assertNotIn("In session 3 the user mentioned", chunk.content)

    def test_swarm_bridge_mckp_and_consensus(self) -> None:
        bridge = SwarmTokenBudgetBridge()
        agents = [
            SwarmAgentRole("agent_arch", "architect", 4000, {ChunkKind.SOURCE_CODE}, {"RootClass"}),
            SwarmAgentRole("agent_code", "coder", 8000, {ChunkKind.SOURCE_CODE}, {"execute_task"}),
            SwarmAgentRole("agent_test", "tester", 2000, {ChunkKind.SOURCE_CODE}, {"test_suite"}),
        ]
        budgets = bridge.partition_swarm_budgets(total_swarm_budget=10000, agents=agents)
        total_allocated = sum(b.max_tokens for b in budgets.values())
        self.assertLessEqual(total_allocated, 10000)

        # Kemeny-Young rank consensus
        candidates = ["file_a.py", "file_b.py", "file_c.py"]
        rankings = [
            ["file_a.py", "file_b.py", "file_c.py"],
            ["file_a.py", "file_c.py", "file_b.py"],
            ["file_b.py", "file_a.py", "file_c.py"],
        ]
        consensus = bridge.kemeny_young_context_consensus(candidates, rankings)
        # file_a.py is preferred by 2 out of 3 agents in 1st place
        self.assertEqual(consensus[0], "file_a.py")


if __name__ == "__main__":
    unittest.main()
