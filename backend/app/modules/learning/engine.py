"""D115: the answer brain's model, per account: LightGBM, else XGBoost, trained only on the
account's own verdicts (LearningLabel). Until enough verdicts exist (both kinds), or when neither
library is installed, the fixed rule score is used instead (features.rule_score)."""

import logging

log = logging.getLogger(__name__)

MIN_LABELS = 12  # and at least 3 of each kind


def available() -> list[str]:
    """The installed engines, LightGBM first (plain imports: no computed import, which the
    forbidden-capabilities check refuses anywhere in the app)."""
    out = []
    try:
        import lightgbm  # noqa: F401

        out.append("lightgbm")
    except Exception:  # noqa: BLE001 - optional at run time; the rules stand in
        pass
    try:
        import xgboost  # noqa: F401

        out.append("xgboost")
    except Exception:  # noqa: BLE001
        pass
    return out


def fit(rows: list[list[float]], labels: list[bool]) -> tuple[str, bytes] | None:
    """A trained model (engine name, its own serialized form), or None when there is too
    little to learn from. Native training APIs: no scikit-learn, and no pickle (LightGBM's model
    text, XGBoost's UBJSON)."""
    pos = sum(1 for x in labels if x)
    if len(rows) < MIN_LABELS or pos < 3 or len(rows) - pos < 3:
        return None
    import numpy as np

    x = np.asarray(rows, dtype=float)
    y = np.asarray([1 if v else 0 for v in labels], dtype=float)
    for name in available():
        try:
            if name == "lightgbm":
                import lightgbm as lgb

                params = {"objective": "binary", "num_leaves": 7, "min_data_in_leaf": 2,
                          "min_data_in_bin": 1, "learning_rate": 0.1, "verbose": -1}  # fmt: skip
                booster = lgb.train(params, lgb.Dataset(x, label=y, params={"verbose": -1}),
                                    num_boost_round=60)  # fmt: skip
                return name, booster.model_to_string().encode()
            import xgboost as xgb

            params = {"objective": "binary:logistic", "max_depth": 3, "eta": 0.1}
            booster = xgb.train(params, xgb.DMatrix(x, label=y), num_boost_round=60)
            return name, bytes(booster.save_raw("ubj"))
        except Exception:  # noqa: BLE001 - try the next engine; the rules stand in
            log.exception("answer brain: %s training failed", name)
    return None


def predict(engine: str, blob: bytes, rows: list[list[float]]) -> list[float]:
    """The probability that the account would accept each pair."""
    import numpy as np

    x = np.asarray(rows, dtype=float)
    if engine == "lightgbm":
        import lightgbm as lgb

        return [float(p) for p in lgb.Booster(model_str=blob.decode()).predict(x)]
    import xgboost as xgb

    b = xgb.Booster()
    b.load_model(bytearray(blob))
    return [float(p) for p in b.predict(xgb.DMatrix(x))]
