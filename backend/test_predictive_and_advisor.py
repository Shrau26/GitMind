import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from predictive_risk import analyze_predictive_risk
from ai_advisor import classify_question, build_evidence


def repo_fixture():
    return {
        "full_name": "demo/repo",
        "health_score": 76,
        "health_status": "Fair",
        "risk_flags": ["possible maintenance risk"],
        "open_issues": 10,
        "open_pr_count": 14,
        "stale_pr_count": 8,
        "contributor_count": 5,
        "health_breakdown": {
            "activity": {"score": 75, "available": True},
            "issues": {"score": 70, "available": True},
            "pull_requests": {"score": 60, "available": True},
            "contributors": {"score": 65, "available": True},
            "testing": {"score": 45, "available": True},
            "security": {"score": 80, "available": True},
        },
        "contributor_analysis": {"top1_percentage": 82.0},
        "pr_analysis": {"stale_prs": 8},
        "testing_analysis": {"test_source_ratio": 0.1},
        "dependencies": {
            "dependency_health_score": 65,
            "security": {"available": True, "security_score": 80, "critical": 0, "high": 1, "medium": 0, "low": 0},
        },
        "ci_cd": {"ci_score": 75, "success_count": 3, "failure_count": 1, "sample_size": 4},
    }


class PredictiveTests(unittest.TestCase):
    def test_insufficient_history_is_explicit(self):
        result = analyze_predictive_risk(repo_fixture(), [])
        self.assertFalse(result["available"])
        self.assertIn("Forecast requires additional repository history", result["message"])

    def test_health_paradox_detected(self):
        repo = repo_fixture()
        snapshots = [
            {"id": 1, "captured_at": "2026-09-01 10:00:00", "metrics_json":
             '{"health_score":67,"contributor_concentration":55,"open_pr_count":8,"stale_pr_count":3,"factor_scores":{"testing":70,"security":90}}'},
            {"id": 2, "captured_at": "2026-10-01 10:00:00", "metrics_json":
             '{"health_score":76,"contributor_concentration":80,"open_pr_count":14,"stale_pr_count":8,"factor_scores":{"testing":45,"security":80}}'},
        ]
        result = analyze_predictive_risk(repo, snapshots)
        self.assertTrue(result["available"])
        self.assertTrue(result["health_paradox"]["detected"])
        self.assertGreaterEqual(len(result["health_paradox"]["worsened_factors"]), 2)

    def test_intervention_ranking_has_simulated_results(self):
        repo = repo_fixture()
        snapshots = [
            {"id": 1, "captured_at": "2026-09-01 10:00:00", "metrics_json":
             '{"health_score":70,"contributor_concentration":55,"open_pr_count":7,"stale_pr_count":2,"factor_scores":{"testing":75,"security":90}}'},
            {"id": 2, "captured_at": "2026-10-01 10:00:00", "metrics_json":
             '{"health_score":76,"contributor_concentration":82,"open_pr_count":14,"stale_pr_count":8,"factor_scores":{"testing":45,"security":80}}'},
        ]
        result = analyze_predictive_risk(repo, snapshots)
        self.assertTrue(result["recommended_intervention"])
        self.assertTrue(result["recommended_intervention"]["simulated"])
        if result["alternative_interventions"]:
            self.assertGreaterEqual(
                result["recommended_intervention"]["efficiency"],
                result["alternative_interventions"][0]["efficiency"]
            )

class AdvisorTests(unittest.TestCase):
    def test_question_routing(self):
        self.assertEqual(classify_question("Why is security risky?"), "security")
        self.assertEqual(classify_question("Why did my health score improve?"), "predictive")
        self.assertEqual(classify_question("Are dependencies outdated?"), "dependency")
        self.assertEqual(classify_question("How is testing doing?"), "testing")

    def test_evidence_is_topic_scoped(self):
        evidence = build_evidence(repo_fixture(), "Why is the health score changing?")
        self.assertEqual(evidence["topic"], "health")
        self.assertIn("health_components", evidence["evidence"])
        self.assertNotIn("top_contributors", evidence["evidence"])

if __name__ == "__main__":
    unittest.main()
