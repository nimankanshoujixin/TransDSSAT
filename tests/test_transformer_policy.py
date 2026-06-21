from __future__ import annotations

import unittest

import transdssat.policy as policy_module


class TransformerPolicyTests(unittest.TestCase):
    @unittest.skipUnless(policy_module.TORCH_AVAILABLE, "PyTorch is required for Transformer policy tests.")
    def test_continuous_policy_outputs_nonnegative_amounts(self) -> None:
        import torch

        TransformerPolicy = policy_module.TransformerPolicy
        collate_supervised_batch = policy_module.collate_supervised_batch
        DEFAULT_CONTINUOUS_ACTION_SCALE = policy_module.DEFAULT_CONTINUOUS_ACTION_SCALE

        batch = [
            (
                [[0.0] * 13, [1.0] * 13],
                (12.5, 18.0),
            ),
            (
                [[0.5] * 13, [0.25] * 13, [0.75] * 13],
                (30.0, 40.0),
            ),
        ]
        features, padding_mask, irrigation_targets, nitrogen_targets = collate_supervised_batch(batch, device="cpu")
        model = TransformerPolicy().to("cpu")
        irrigation_pred, nitrogen_pred = model(features, padding_mask=padding_mask)

        self.assertEqual(tuple(irrigation_pred.shape), (2,))
        self.assertEqual(tuple(nitrogen_pred.shape), (2,))
        self.assertTrue(torch.isfinite(irrigation_pred).all().item())
        self.assertTrue(torch.isfinite(nitrogen_pred).all().item())
        self.assertTrue(torch.all(irrigation_pred >= 0.0).item())
        self.assertTrue(torch.all(nitrogen_pred >= 0.0).item())
        self.assertLessEqual(float(irrigation_pred.max().item()), DEFAULT_CONTINUOUS_ACTION_SCALE)
        self.assertLessEqual(float(nitrogen_pred.max().item()), DEFAULT_CONTINUOUS_ACTION_SCALE)
        self.assertEqual(irrigation_targets.dtype, torch.float32)
        self.assertEqual(nitrogen_targets.dtype, torch.float32)


if __name__ == "__main__":
    unittest.main()
