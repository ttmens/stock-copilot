"""WeightOptimizer — dynamically tune signal fusion weights based on historical performance.

Uses an exponential moving average approach: signal layers that have been
more predictive recently get higher weight.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default weights (5-layer fusion)
DEFAULT_WEIGHTS = {
    "hard": 0.40,
    "soft": 0.25,
    "gate": 0.15,
    "dragon_tiger": 0.10,
    "announcement": 0.10,
}

# Bounds: no weight can go below this (prevents zeroing out any layer)
MIN_WEIGHT = 0.05

# Learning rate: how aggressively to adjust weights (0.01 = conservative, 0.1 = aggressive)
LEARNING_RATE = 0.05


@dataclass
class WeightConfig:
    """Current signal fusion weights."""
    hard: float = 0.40
    soft: float = 0.25
    gate: float = 0.15
    dragon_tiger: float = 0.10
    announcement: float = 0.10
    version: int = 1
    last_updated: str = ""
    history: list[dict] = field(default_factory=list)  # past weight snapshots

    def to_dict(self) -> dict:
        return {
            "hard": self.hard,
            "soft": self.soft,
            "gate": self.gate,
            "dragon_tiger": self.dragon_tiger,
            "announcement": self.announcement,
            "version": self.version,
            "last_updated": self.last_updated,
            "history": self.history[-20:],  # keep last 20
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WeightConfig":
        return cls(
            hard=d.get("hard", 0.40),
            soft=d.get("soft", 0.25),
            gate=d.get("gate", 0.15),
            dragon_tiger=d.get("dragon_tiger", 0.10),
            announcement=d.get("announcement", 0.10),
            version=d.get("version", 1),
            last_updated=d.get("last_updated", ""),
            history=d.get("history", []),
        )


class WeightOptimizer:
    """Dynamically optimize signal fusion weights based on historical accuracy."""

    def __init__(self, config_path: str = "config/fusion_weights.json"):
        self.config_path = Path(config_path)
        self.weights = self._load_config()

    def _load_config(self) -> WeightConfig:
        if self.config_path.exists():
            try:
                d = json.loads(self.config_path.read_text())
                return WeightConfig.from_dict(d)
            except Exception as e:
                logger.warning("Failed to load weight config: %s, using defaults", e)
        return WeightConfig(
            last_updated="",
            history=[],
        )

    def save_config(self):
        """Persist current weights to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.weights.to_dict(), ensure_ascii=False, indent=2)
        )
        logger.info("Saved weight config v%d: %s",
                     self.weights.version,
                     {k: round(v, 3) for k, v in self._as_dict().items()})

    def optimize(
        self,
        performance_report,
        lr: float = LEARNING_RATE,
    ) -> dict:
        """Adjust weights based on a performance report.

        Strategy:
        1. Evaluate each layer's predictive power
        2. Increase weight for layers that agreed with actual outcome
        3. Decrease weight for layers that disagreed
        4. Normalize to sum=1.0
        """
        current = self._as_dict()
        layer_accuracy = self._compute_layer_accuracy(performance_report)

        if not layer_accuracy:
            logger.info("No layer accuracy data, keeping current weights")
            return current

        # Adjust each weight based on layer accuracy
        new_weights = {}
        total_accuracy = sum(layer_accuracy.values())
        if total_accuracy <= 0:
            return current

        for layer_name, accuracy in layer_accuracy.items():
            if layer_name not in current:
                continue

            # Target weight proportional to accuracy
            target = accuracy / total_accuracy

            # Smooth adjustment (EMA)
            old = current[layer_name]
            new_weights[layer_name] = old + lr * (target - old)

        # Apply minimum weight floor
        for k in new_weights:
            new_weights[k] = max(MIN_WEIGHT, new_weights[k])

        # Normalize to sum=1.0
        total = sum(new_weights.values())
        if total > 0:
            for k in new_weights:
                new_weights[k] = round(new_weights[k] / total, 4)

        # Update config
        self.weights.hard = new_weights.get("hard", 0.40)
        self.weights.soft = new_weights.get("soft", 0.25)
        self.weights.gate = new_weights.get("gate", 0.15)
        self.weights.dragon_tiger = new_weights.get("dragon_tiger", 0.10)
        self.weights.announcement = new_weights.get("announcement", 0.10)
        self.weights.version += 1

        from datetime import datetime
        self.weights.last_updated = datetime.now().isoformat()
        self.weights.history.append({
            "version": self.weights.version,
            "weights": {k: round(v, 3) for k, v in new_weights.items()},
            "win_rate": round(getattr(performance_report, 'win_rate', 0), 3),
            "updated_at": self.weights.last_updated,
        })

        self.save_config()
        return new_weights

    def get_weights(self) -> dict:
        """Return current fusion weights."""
        return self._as_dict()

    def apply_to_fusion(self):
        """Patch signal_fusion.py to use current weights.

        This modifies the hardcoded weights in fuse_signals() at runtime
        by monkey-patching the module-level constants.
        """
        weights = self._as_dict()

        # Monkey-patch: override the weight variables used in fuse_signals
        import src.data.signal_fusion as sf

        # Store original if not already backed up
        if not hasattr(sf, "_original_weights"):
            sf._original_weights = {
                "w_hard_default": 0.40,
                "w_soft_default": 0.25,
                "w_gate_default": 0.15,
            }

        # Update the module-level weight references
        sf.W_HARD = weights["hard"]
        sf.W_SOFT = weights["soft"]
        sf.W_GATE = weights["gate"]
        sf.W_DRAGON_TIGER = weights["dragon_tiger"]
        sf.W_ANNOUNCEMENT = weights["announcement"]

        logger.info("Applied optimized weights to signal_fusion: %s",
                     {k: round(v, 3) for k, v in weights.items()})

    def reset_to_defaults(self):
        """Reset weights to hardcoded defaults."""
        self.weights = WeightConfig(last_updated="")
        self.save_config()
        logger.info("Reset weights to defaults")

    # ── Private helpers ──────────────────────────────────────────

    def _as_dict(self) -> dict:
        return {
            "hard": self.weights.hard,
            "soft": self.weights.soft,
            "gate": self.weights.gate,
            "dragon_tiger": self.weights.dragon_tiger,
            "announcement": self.weights.announcement,
        }

    def _compute_layer_accuracy(self, performance_report) -> dict[str, float]:
        """Compute per-layer predictive accuracy from verification results.

        For each layer, check if its direction agreed with actual outcome.
        Returns: {"hard": 0.65, "soft": 0.55, ...}
        """
        verifications = getattr(performance_report, 'verifications', [])
        if not verifications:
            return {}

        layer_correct = {"hard": 0, "soft": 0, "gate": 0}
        layer_total = {"hard": 0, "soft": 0, "gate": 0}

        for ver in verifications:
            actual_dir = getattr(ver, 'actual_direction', None)
            if actual_dir is None or actual_dir == "flat":
                continue

            # Hard signal accuracy
            hard_score = getattr(ver, 'predicted_score', 0)
            if hasattr(ver, 'hard_score'):
                hard_score = ver.hard_score
            if hard_score > 0.1:
                layer_total["hard"] += 1
                if actual_dir == "up":
                    layer_correct["hard"] += 1
            elif hard_score < -0.1:
                layer_total["hard"] += 1
                if actual_dir == "down":
                    layer_correct["hard"] += 1

            # Soft signal accuracy (inferred from final_signal patterns)
            # When hard != final, soft likely influenced the direction
            predicted = getattr(ver, 'predicted', 'hold')
            if predicted in ("strong_buy", "buy") and actual_dir == "up":
                layer_total["soft"] += 1
                layer_correct["soft"] += 1
            elif predicted in ("strong_sell", "sell") and actual_dir == "down":
                layer_total["soft"] += 1
                layer_correct["soft"] += 1
            elif predicted in ("strong_buy", "buy", "strong_sell", "sell"):
                layer_total["soft"] += 1

        result = {}
        for layer in layer_total:
            if layer_total[layer] > 0:
                result[layer] = layer_correct[layer] / layer_total[layer]
            else:
                result[layer] = 0.5  # neutral prior

        return result
