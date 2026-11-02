"""D115: the answer brain's model, per account: LightGBM, else XGBoost, trained only on the
account's own verdicts (LearningLabel). Until enough verdicts exist (both kinds), or when neither
library is installed, the fixed rule score is used instead (features.rule_score)."""

import logging
import pickle

log = logging.getLogger(__name__)

MIN_LABELS = 12  # and at least 3 of each kind


def available() -> list[str]:
    out = []
    for name in ("lightgbm", "xgboost"):
        try:
            __import__(name)
            out.append(name)
        except Exception:  # noqa: BLE001 - optional at run time; the rules stand in
            pass
    return out


def fit(rows: list[list[float]], labels: list[bool]) -> tuple[str, bytes] | None:
    """A trained model (engine name, bytes), or None when there is too little to learn from."""
    pos = sum(1 for x in labels if x)
    if len(rows) < MIN_LABELS or pos < 3 or len(rows) - pos < 3:
        return None
    y = [1 if x else 0 for x in labels]
    for name in available():
        try:
            if name == "lightgbm":
                import lightgbm as lgb

                m = lgb.LGBMClassifier(n_estimators=60, num_leaves=7, min_child_samples=2,
                                       learning_rate=0.1, verbose=-1)  # fmt: skip
            else:
                import xgboost as xgb

                m = xgb.XGBClassifier(n_estimators=60, max_depth=3, learning_rate=0.1,
                                      eval_metric="logloss")  # fmt: skip
            m.fit(rows, y)
            return name, pickle.dumps(m)
        except Exception:  # noqa: BLE001 - try the next engine; the rules stand in
            log.exception("answer brain: %s training failed", name)
    return None


def predict(engine: str, blob: bytes, rows: list[list[float]]) -> list[float]:
    m = pickle.loads(blob)  # noqa: S301 - written by this module only, from the account's labels
    return [float(p[1]) for p in m.predict_proba(rows)]
