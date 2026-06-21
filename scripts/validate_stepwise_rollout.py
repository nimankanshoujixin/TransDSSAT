from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.environments import StepwiseDecisionEnvironment
from transdssat.scenarios import build_quzhou_scenarios, clone_objective_context_with_reward_contract
from transdssat.stepwise_ppo import rollout_stepwise_episode, select_highest_legal_action


def choose_action(observation) -> dict[str, float]:
    constraints = observation.action_constraints
    irrigation_mm = min(25.0, constraints.irrigation.max_value)
    nitrogen_kg_ha = min(35.0, constraints.nitrogen.max_value)
    return {
        "irrigation_mm": irrigation_mm,
        "nitrogen_kg_ha": nitrogen_kg_ha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the continuous step-wise proxy environment.")
    parser.add_argument("--seed", type=int, default=20260526)
    parser.add_argument("--crop", choices=("maize", "wheat"), default="maize")
    parser.add_argument("--reward-contract", choices=("reward_v1", "reward_v2"), default="reward_v2")
    args = parser.parse_args()

    scenario = build_quzhou_scenarios(
        target_count=1,
        engines=("dssat_proxy",),
        crops_filter=(args.crop,),
        sampling_mode="random",
        seed=args.seed,
    )[0]
    scenario.objective_context = clone_objective_context_with_reward_contract(
        scenario.objective_context,
        args.reward_contract,
    )
    env = StepwiseDecisionEnvironment(scenario)
    observation = env.reset()

    decision_trace: list[dict] = []
    cumulative_reward = 0.0
    while not observation.done:
        action = choose_action(observation)
        observation, reward, done, info = env.step(action)
        cumulative_reward += reward
        decision_trace.append(
            {
                "decision_day_index": info["decision_day_index"],
                "executed_action": info["executed_action"],
                "reward": reward,
                "days_executed": info["days_executed"],
                "remaining_irrigation_mm": info["remaining_irrigation_mm"],
                "remaining_nitrogen_kg_ha": info["remaining_nitrogen_kg_ha"],
            }
        )
        if done:
            break

    history_episode = rollout_stepwise_episode(
        scenario,
        select_highest_legal_action,
        policy_id="history_conditioned_validation",
        notes=["sequence_interface_smoke_check"],
    )

    summary = {
        "scenario_id": scenario.scenario_id,
        "crop_name": scenario.crop_spec.crop_name,
        "cultivar_id": scenario.cultivar_id,
        "objective_context": scenario.objective_context.to_dict(),
        "reward_contract": args.reward_contract,
        "decision_context": scenario.decision_context.to_dict(),
        "state_interface_contract": scenario.state_interface_contract_dict(),
        "decision_count": len(decision_trace),
        "cumulative_reward": round(cumulative_reward, 6),
        "final_outcome": env.final_outcome().to_dict(),
        "history_conditioned_sequence": {
            "enabled": True,
            "first_transition_sequence_length": history_episode.transitions[0].sequence_length if history_episode.transitions else 0,
            "max_sequence_length": max(
                (transition.sequence_length for transition in history_episode.transitions),
                default=0,
            ),
        },
        "decision_trace": decision_trace,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
