from __future__ import annotations

from abc import ABC, abstractmethod

from transdssat.domain import CropAction, CropOutcome, CropState


class CropEnvironment(ABC):
    @abstractmethod
    def reset(self) -> CropState:
        raise NotImplementedError

    @abstractmethod
    def step(self, action: CropAction) -> tuple[CropState, float, bool, dict]:
        raise NotImplementedError

    @abstractmethod
    def final_outcome(self) -> CropOutcome:
        raise NotImplementedError
