import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha import models  # noqa: E402


class TestModelsTable(unittest.TestCase):
    """Models — the lookup run() uses to size a Context before any backend
    exists. It is folded from the backend tables rather than hand-written,
    because the hand-written version had already drifted: it claimed
    claude-sonnet-4-6 was 200k while the Anthropic backend said 1M.
    """

    def test_every_backend_model_is_in_the_table(self):
        for backend in models.BACKENDS:
            for model in backend.MODELS:
                with self.subTest(backend=backend.__name__, model=model):
                    self.assertTrue(models.known(model))

    def test_windows_agree_with_the_backend_that_declares_them(self):
        for backend in models.BACKENDS:
            for model, spec in backend.MODELS.items():
                with self.subTest(backend=backend.__name__, model=model):
                    self.assertEqual(
                        spec["context_window"], models.context_window(model)
                    )

    def test_no_model_is_claimed_by_two_backends(self):
        all_ids = [m for backend in models.BACKENDS for m in backend.MODELS]

        self.assertEqual(sorted(set(all_ids)), sorted(all_ids))

    def test_an_unknown_model_falls_back_conservatively(self):
        self.assertFalse(models.known("no-such-model"))
        self.assertEqual(
            models.DEFAULT_CONTEXT_WINDOW, models.context_window("no-such-model")
        )

    def test_the_configured_player_model_is_known(self):
        """The configured model has to resolve to a real window, or the agent
        compacts against the 32k fallback while a 200k window sits unused."""
        settings = boukensha.config().tasks("player")
        if not settings:
            self.skipTest("no player task configured")

        model = boukensha.Player.model(settings)

        self.assertTrue(models.known(model), f"settings.yaml runs {model}")


if __name__ == "__main__":
    unittest.main()
