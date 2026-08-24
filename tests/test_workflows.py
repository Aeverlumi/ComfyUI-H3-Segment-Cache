import json
import unittest
from collections import Counter
from pathlib import Path


WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "workflow_templates"


class WorkflowTests(unittest.TestCase):
    def load(self, filename):
        return json.loads((WORKFLOW_DIR / filename).read_text(encoding="utf-8"))

    def assert_links_are_valid(self, workflow):
        nodes = {node["id"]: node for node in workflow["nodes"]}
        self.assertEqual(len(nodes), len(workflow["nodes"]), "duplicate node id")
        seen_links = set()

        for link in workflow["links"]:
            link_id, source_id, source_slot, target_id, target_slot, _ = link
            self.assertNotIn(link_id, seen_links, f"duplicate link id {link_id}")
            seen_links.add(link_id)
            self.assertIn(source_id, nodes, f"link {link_id} has no source node")
            self.assertIn(target_id, nodes, f"link {link_id} has no target node")

            source = nodes[source_id]
            target = nodes[target_id]
            self.assertLess(source_slot, len(source.get("outputs", [])), f"link {link_id} source slot")
            self.assertLess(target_slot, len(target.get("inputs", [])), f"link {link_id} target slot")
            self.assertIn(link_id, source["outputs"][source_slot].get("links") or [])
            self.assertEqual(target["inputs"][target_slot].get("link"), link_id)

    def test_24gb_workflow(self):
        workflow = self.load(
            "minimaxh3_for_loop_motion_context_v8.5_24GB_无Latent放大_无二采.json"
        )
        self.assert_links_are_valid(workflow)
        types = Counter(node["type"] for node in workflow["nodes"])
        self.assertEqual(types["SamplerCustomAdvanced"], 2)
        self.assertEqual(types["H3SegmentCacheFinalize"], 1)
        self.assertFalse(any("LatentUpscal" in node_type for node_type in types))

    def test_32gb_workflow(self):
        workflow = self.load(
            "minimaxh3_for_loop_motion_context_v8.5_32GB_保留Latent放大_保留二采.json"
        )
        self.assert_links_are_valid(workflow)
        types = Counter(node["type"] for node in workflow["nodes"])
        self.assertEqual(types["SamplerCustomAdvanced"], 4)
        self.assertEqual(types["MinimaxH3LatentUpscalerNode3D"], 2)
        self.assertEqual(types["H3LatentUpscalerNode3DV3"], 2)
        self.assertEqual(types["H3SegmentCacheFinalize"], 1)
        scales = [
            node["widgets_values"][1]
            for node in workflow["nodes"]
            if node["type"] == "MinimaxH3LatentUpscalerNode3D"
        ]
        self.assertEqual(scales, [1.2, 1.2])


if __name__ == "__main__":
    unittest.main()
