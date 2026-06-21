from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from transdssat.domain import CropState


DEFAULT_CONTINUOUS_ACTION_SCALE = 500.0


def encode_state(state: CropState) -> list[float]:
    return [
        float(state.day_index),
        float(state.stage_index),
        float(state.soil_moisture),
        float(state.root_zone_water_mm),
        float(state.soil_nitrogen_kg_ha),
        float(state.canopy_cover),
        float(state.biomass_kg_ha),
        float(state.water_stress),
        float(state.nitrogen_stress),
        float(state.tmean_c),
        float(state.precipitation_mm),
        float(state.et0_mm),
        float(state.radiation_mj_m2),
    ]


def iter_supervised_examples(dataset_path: str | Path) -> Iterable[tuple[list[list[float]], tuple[float, float]]]:
    with Path(dataset_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            trajectory = json.loads(line)
            steps = trajectory["steps"]
            policy = trajectory.get("policy")
            if policy and policy.get("actions"):
                for action in policy["actions"]:
                    day_index = int(action["day_index"])
                    sequence = [
                        encode_state(CropState(**step["state"]))
                        for step in steps
                        if int(step["state"]["day_index"]) <= day_index
                    ]
                    if not sequence:
                        continue
                    yield sequence, (action["irrigation_mm"], action["nitrogen_kg_ha"])
                continue

            sequence = [encode_state(CropState(**step["state"])) for step in steps]
            if not sequence:
                continue
            last_action = steps[-1]["action"]
            yield sequence, (last_action["irrigation_mm"], last_action["nitrogen_kg_ha"])


try:
    import torch
    from torch import nn

    TORCH_AVAILABLE = True

    class TransformerPolicy(nn.Module):
        def __init__(
            self,
            input_dim: int = 13,
            hidden_dim: int = 128,
            num_heads: int = 4,
            num_layers: int = 3,
        ) -> None:
            super().__init__()
            self.input_projection = nn.Linear(input_dim, hidden_dim)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=num_heads,
                batch_first=True,
                dim_feedforward=hidden_dim * 4,
                dropout=0.1,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.norm = nn.LayerNorm(hidden_dim)
            self.irrigation_head = nn.Linear(hidden_dim, 1)
            self.nitrogen_head = nn.Linear(hidden_dim, 1)

        def forward(
            self,
            x: torch.Tensor,
            padding_mask: torch.Tensor | None = None,
        ) -> tuple[torch.Tensor, torch.Tensor]:
            hidden = self.input_projection(x)
            encoded = self.encoder(hidden, src_key_padding_mask=padding_mask)
            if padding_mask is None:
                pooled = encoded[:, -1, :]
            else:
                lengths = (~padding_mask).sum(dim=1).clamp(min=1) - 1
                pooled = encoded[torch.arange(encoded.size(0), device=encoded.device), lengths]
            pooled = self.norm(pooled)
            irrigation = torch.sigmoid(self.irrigation_head(pooled)).squeeze(-1) * DEFAULT_CONTINUOUS_ACTION_SCALE
            nitrogen = torch.sigmoid(self.nitrogen_head(pooled)).squeeze(-1) * DEFAULT_CONTINUOUS_ACTION_SCALE
            return irrigation, nitrogen


except ImportError:  # pragma: no cover - depends on local environment
    TORCH_AVAILABLE = False
    TransformerPolicy = None


@dataclass(slots=True)
class TrainingReadiness:
    torch_available: bool
    message: str


def training_readiness() -> TrainingReadiness:
    if TORCH_AVAILABLE:
        return TrainingReadiness(torch_available=True, message="PyTorch detected.")
    return TrainingReadiness(
        torch_available=False,
        message=(
            "PyTorch is not installed. Install torch first to train the Transformer "
            "policy, then rerun scripts/train_transformer.py."
        ),
    )


def collate_supervised_batch(
    batch: list[tuple[list[list[float]], tuple[float, float]]],
    device: "torch.device | str | None" = None,
) -> tuple["torch.Tensor", "torch.Tensor", "torch.Tensor", "torch.Tensor"]:
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is required to collate supervised Transformer batches.")

    import torch

    batch_size = len(batch)
    max_len = max(len(sequence) for sequence, _ in batch)
    input_dim = len(batch[0][0][0])
    features = torch.zeros((batch_size, max_len, input_dim), dtype=torch.float32, device=device)
    padding_mask = torch.ones((batch_size, max_len), dtype=torch.bool, device=device)
    irrigation_targets = torch.zeros(batch_size, dtype=torch.float32, device=device)
    nitrogen_targets = torch.zeros(batch_size, dtype=torch.float32, device=device)

    for row_index, (sequence, action) in enumerate(batch):
        seq_tensor = torch.tensor(sequence, dtype=torch.float32, device=device)
        length = seq_tensor.size(0)
        features[row_index, :length, :] = seq_tensor
        padding_mask[row_index, :length] = False
        irrigation_targets[row_index] = float(action[0])
        nitrogen_targets[row_index] = float(action[1])

    return features, padding_mask, irrigation_targets, nitrogen_targets
