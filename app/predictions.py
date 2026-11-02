"""DIVINE AI: chronological, calibrated next-session research baselines.

Features use completed candles only. The target is the NEXT session's
open-to-close return, allowing the costed research strategy to enter at open.
No orders, brokerage execution, invented prices, or fabricated forecasts.
"""
from collections import defaultdict
from datetime import datetime, timedelta
import importlib.util
import json
from pathlib import Path
import threading
import uuid

from . import config
from .storage import now_iso

UNAVAILABLE = "Prediction unavailable — insufficient validated historical data."
HORIZON = "Next trading session · open to close"
FEATURES = ["return_1", "return_5", "return_20", "volatility_20", "volume_ratio",
            "opening_gap", "distance_sma_10", "distance_sma_20", "distance_sma_50",
            "atr_14", "rsi_14", "macd", "sector_momentum", "market_breadth"]


def libraries_available():
    return all(importlib.util.find_spec(name) for name in ("numpy", "sklearn", "joblib"))


def feature_rows(candles, memberships):
    import numpy as np
    by_symbol = defaultdict(list)
    daily_returns = defaultdict(dict)
    sectors = defaultdict(set)
    for symbol, sector in memberships:
        sectors[symbol].add(sector)
    for bar in candles:
        by_symbol[bar["symbol"]].append(bar)
    for symbol, bars in by_symbol.items():
        bars.sort(key=lambda r: r["timestamp"])
        for i in range(1, len(bars)):
            daily_returns[bars[i]["timestamp"]][symbol] = bars[i]["close"] / bars[i - 1]["close"] - 1
    rows = []
    for symbol, bars in by_symbol.items():
        if len(bars) < 61:
            continue
        close = np.array([b["close"] for b in bars], dtype=float)
        volume = np.array([b["volume"] for b in bars], dtype=float)
        ema12, ema26 = close[0], close[0]
        for i, bar in enumerate(bars):
            ema12 = close[i] * (2 / 13) + ema12 * (11 / 13)
            ema26 = close[i] * (2 / 27) + ema26 * (25 / 27)
            if i < 60:
                continue
            # Long suspensions, missing runs and unadjusted corporate-action jumps
            # cannot silently become ordinary next-session training examples.
            window = bars[i - 60:i + 1]
            if any((datetime.fromisoformat(b["timestamp"]) - datetime.fromisoformat(a["timestamp"])).days > 7
                   or abs(b["close"] / a["close"] - 1) > .4 for a, b in zip(window, window[1:])):
                continue
            returns = np.diff(close[i - 20:i + 1]) / close[i - 20:i]
            delta = np.diff(close[i - 14:i + 1])
            gain, loss = np.maximum(delta, 0).mean(), np.maximum(-delta, 0).mean()
            rsi = 50 if gain == loss == 0 else 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
            ranges = [max(bars[j]["high"] - bars[j]["low"], abs(bars[j]["high"] - close[j - 1]), abs(bars[j]["low"] - close[j - 1])) for j in range(i - 13, i + 1)]
            contemporaries = daily_returns[bar["timestamp"]]
            peer_returns = [r for peer, r in contemporaries.items() if sectors[peer] & sectors[symbol]]
            values = [close[i] / close[i - n] - 1 for n in (1, 5, 20)]
            values += [float(np.std(returns)), volume[i] / max(1, volume[i - 20:i].mean()) - 1,
                       bar["open"] / close[i - 1] - 1]
            values += [close[i] / close[i - n + 1:i + 1].mean() - 1 for n in (10, 20, 50)]
            values += [float(np.mean(ranges)) / close[i], rsi / 100, (ema12 - ema26) / close[i],
                       float(np.mean(peer_returns)) if peer_returns else 0,
                       sum(r > 0 for r in contemporaries.values()) / max(1, len(contemporaries))]
            if not np.isfinite(values).all():
                continue
            next_valid = i + 1 < len(bars) and (datetime.fromisoformat(bars[i + 1]["timestamp"]) - datetime.fromisoformat(bar["timestamp"])).days <= 7 and abs(bars[i + 1]["close"] / close[i] - 1) <= .4
            target = bars[i + 1]["close"] / bars[i + 1]["open"] - 1 if next_valid else None
            rows.append({"symbol": symbol, "as_of": bar["timestamp"], "price": float(close[i]),
                         "x": values, "target_return": target, "y": int(target > 0) if target is not None else None,
                         "label_date": bars[i + 1]["timestamp"] if next_valid else None})
    return sorted(rows, key=lambda r: (r["as_of"], r["symbol"]))


def build_model(name):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if name == "Logistic Regression":
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.2, max_iter=1500, random_state=369))
    return RandomForestClassifier(n_estimators=120, max_depth=4, min_samples_leaf=20, n_jobs=1, random_state=369)


def fit_calibrated(name, rows):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    dates = sorted({r["as_of"] for r in rows})
    cutoff = dates[int(len(dates) * .8)]
    training = [r for r in rows if r["label_date"] < cutoff]
    calibration = [r for r in rows if r["as_of"] >= cutoff]
    if min(len(training), len(calibration)) < 30 or any(len({r["y"] for r in part}) < 2 for part in (training, calibration)):
        raise ValueError("Insufficient class diversity for chronological probability calibration.")
    model = build_model(name)
    model.fit([r["x"] for r in training], [r["y"] for r in training])
    probability = model.predict_proba([r["x"] for r in calibration])[:, 1]
    logits = np.log(np.clip(probability, 1e-6, 1 - 1e-6) / np.clip(1 - probability, 1e-6, 1))
    calibrator = LogisticRegression(C=1, random_state=369).fit(logits.reshape(-1, 1), [r["y"] for r in calibration])
    return {"model": model, "calibrator": calibrator, "calibration_start": cutoff}


def probabilities(artifact, rows):
    import numpy as np
    raw = artifact["model"].predict_proba([r["x"] for r in rows])[:, 1]
    logits = np.log(np.clip(raw, 1e-6, 1 - 1e-6) / np.clip(1 - raw, 1e-6, 1))
    return artifact["calibrator"].predict_proba(logits.reshape(-1, 1))[:, 1]


def evaluate(rows, probability):
    import numpy as np
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, brier_score_loss, log_loss
    y = np.array([r["y"] for r in rows])
    p = np.array(probability)
    predicted = (p >= .5).astype(int)
    calibration = []
    error = 0.0
    for low in np.arange(0, 1, .1):
        mask = (p >= low) & ((p < low + .1) if low < .9 else (p <= 1))
        if mask.any():
            mean, observed, count = float(p[mask].mean()), float(y[mask].mean()), int(mask.sum())
            calibration.append({"forecast": mean, "observed": observed, "count": count})
            error += abs(mean - observed) * count / len(y)
    daily = defaultdict(list)
    exposure = 0
    for row, prob in zip(rows, p):
        direction = (1 if prob >= .55 else -1 if prob <= .45 else 0) if row.get("backtest_eligible", True) else 0
        exposure += int(direction != 0)
        # Equal allocation across every available symbol; untraded allocations stay cash.
        daily[row["label_date"]].append(direction * row["target_return"] - (config.BACKTEST_COST_BPS / 10000 if direction else 0))
    equity, peak, max_dd = 1.0, 1.0, 0.0
    curve = []
    for day, values in sorted(daily.items()):
        equity *= 1 + float(np.mean(values))
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1)
        curve.append({"date": day, "return": equity - 1})
    return {"directional_accuracy": float(accuracy_score(y, predicted)),
            "precision": float(precision_score(y, predicted, zero_division=0)),
            "recall": float(recall_score(y, predicted, zero_division=0)),
            "f1": float(f1_score(y, predicted, zero_division=0)),
            "roc_auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None,
            "brier_score": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p, labels=[0, 1])),
            "calibration_error": error, "calibration_bins": calibration,
            "samples": len(rows), "sessions": len(daily), "start": rows[0]["as_of"], "end": rows[-1]["as_of"],
            "backtest_return_after_costs": equity - 1, "maximum_drawdown": max_dd,
            "round_trip_cost_bps": config.BACKTEST_COST_BPS, "trades": exposure, "equity_curve": curve,
            "mae": None, "rmse": None, "regression_note": "Direction classifier; no return-range or regression claims.",
            "backtest_note": "Research only: equal allocations, next-session open/close, round-trip costs and slippage included. Verified BE trade-for-trade instruments stay in cash. No liquidity, borrow or capacity guarantee."}


class PredictionLab:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.state = "idle"
        self.message = UNAVAILABLE
        self.last_attempt = None

    def dataset(self):
        with self.store.connection() as db:
            memberships = [(r["symbol"], r["sector_id"]) for r in db.execute("SELECT DISTINCT symbol,sector_id FROM sector_memberships")]
            restricted = {r["symbol"] for r in db.execute("SELECT symbol FROM instrument_resolutions WHERE provider_symbol LIKE '%-BE'")}
        rows = feature_rows(self.store.candles(), memberships)
        for row in rows:
            row["backtest_eligible"] = row["symbol"] not in restricted
        return rows

    def status(self):
        model = self.store.model()
        coverage = self.store.overview()
        blockers = []
        if not config.DATA_RETENTION_AUTHORIZED:
            blockers.append("Explicit historical storage and ML-use authorization is required.")
        if not coverage["candles"]:
            blockers.append("No authorized completed daily candles have been imported.")
        history = self.store.predictions()
        seen = set()
        latest = []
        for row in history if config.DATA_RETENTION_AUTHORIZED else []:
            if row["symbol"] not in seen and row["actual_return"] is None and model and row["version"] == model["version"]:
                latest.append(row)
                seen.add(row["symbol"])
        return {"state": "ready" if model and self.state == "idle" else self.state,
                "message": "Validated model restored from private storage." if model and self.state == "idle" else self.message, "last_attempt": self.last_attempt,
                "libraries_available": libraries_available(), "model": model, "coverage": coverage,
                "storage_authorized": config.DATA_RETENTION_AUTHORIZED, "blockers": blockers,
                "predictions": latest, "history": history[:200], "horizon": HORIZON, "last_evaluation": self.store.last_evaluation(),
                "notice": "Forecast probabilities are research estimates, separate from live quotes. No guaranteed accuracy or profits."}

    def train(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A training or inference job is already running.")
        self.state = "training"
        self.last_attempt = now_iso()
        try:
            if not config.DATA_RETENTION_AUTHORIZED:
                raise ValueError("Enable authorized data retention before training.")
            if not libraries_available():
                raise ValueError("Install the machine-learning requirements before training.")
            import joblib
            import numpy as np
            from sklearn.model_selection import TimeSeriesSplit
            rows = [r for r in self.dataset() if r["y"] is not None]
            dates = sorted({r["as_of"] for r in rows})
            if len(dates) < 180 or len(rows) < 300:
                raise ValueError(UNAVAILABLE + " Need at least 240 completed candles per stock, 180 feature sessions and 300 labeled observations.")
            prior = self.store.model()
            if prior and sum(day > prior["data_through"] for day in dates) < config.TRAINING_MIN_NEW_SESSIONS:
                raise ValueError("Retraining deferred until sufficient new sessions exist.")
            # Final 25% is untouched until candidate selection/calibration is finished.
            test_start = dates[int(len(dates) * .75)]
            development = [r for r in rows if r["label_date"] < test_start]
            test = [r for r in rows if r["as_of"] >= test_start]
            dev_dates = sorted({r["as_of"] for r in development})
            comparison = {}
            for name in ("Logistic Regression", "Random Forest"):
                folds = []
                for train_idx, validation_idx in TimeSeriesSplit(n_splits=3, gap=1).split(dev_dates):
                    validation_start = dev_dates[int(validation_idx[0])]
                    train_dates = {dev_dates[int(i)] for i in train_idx}
                    validation_dates = {dev_dates[int(i)] for i in validation_idx}
                    training = [r for r in development if r["as_of"] in train_dates and r["label_date"] < validation_start]
                    validation = [r for r in development if r["as_of"] in validation_dates]
                    artifact = fit_calibrated(name, training)
                    folds.append(evaluate(validation, probabilities(artifact, validation)))
                comparison[name] = {"mean_brier_score": float(np.mean([f["brier_score"] for f in folds])), "walk_forward": folds}
            best = min(comparison, key=lambda n: comparison[n]["mean_brier_score"])
            artifact = fit_calibrated(best, development)
            metrics = evaluate(test, probabilities(artifact, test))
            train_prior = float(np.mean([r["y"] for r in development]))
            baseline = evaluate(test, np.repeat(train_prior, len(test)))
            metrics["majority_class_baseline"] = {"directional_accuracy": baseline["directional_accuracy"], "brier_score": baseline["brier_score"], "probability_up": train_prior}
            metrics["no_change_baseline"] = {"return_after_costs": 0.0, "maximum_drawdown": 0.0, "note": "Cash/no-change reference, no transactions."}
            if metrics["sessions"] < 30 or metrics["roc_auc"] is None or metrics["roc_auc"] < .5 or metrics["brier_score"] >= baseline["brier_score"]:
                self.message = "Model withheld: out-of-sample evidence did not pass the calibration and baseline gates."
                self._record_rejection(best, metrics, comparison)
                self.state = "withheld"
                return {"state": self.state, "message": self.message, "evaluation": metrics}
            version = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
            config.MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
            path = config.MODEL_DIRECTORY / f"{version}.joblib"
            joblib.dump({**artifact, "version": version, "features": FEATURES}, path)
            payload = {"features": FEATURES, "horizon": HORIZON, "calibration": "Platt sigmoid, fitted on the final chronological 20% of development data.",
                       "calibration_start": artifact["calibration_start"], "test_start": test_start,
                       "selection": "Lowest mean walk-forward Brier score; test data excluded from model selection.",
                       "universe_note": "Current approved universe; historical survivorship and corporate-action adjustment limitations apply.",
                       "return_range": "Unsupported by the direction baseline.", "comparison": comparison}
            with self.store.connection() as db:
                db.execute("INSERT INTO model_versions VALUES(?,?,?,?,?,?)", (version, now_iso(), best, str(path), dates[-1], json.dumps(payload)))
                db.execute("INSERT INTO model_metrics VALUES(?,?,?)", (version, "out_of_sample", json.dumps(metrics)))
            self.message = "Validated model saved. Forecasts use completed daily candles."
            self.state = "ready"
            self._infer(artifact, version)
            return {"state": self.state, "version": version, "evaluation": metrics}
        except (ValueError, ImportError) as exc:
            self.state, self.message = "unavailable", str(exc)
            raise ValueError(str(exc)) from exc
        except Exception as exc:
            self.state, self.message = "error", "Training failed; inspect the data and server environment."
            raise ValueError(self.message) from exc
        finally:
            self.lock.release()

    def _record_rejection(self, name, metrics, comparison):
        # Retain rejected evaluations for audit without activating a model.
        with self.store.connection() as db:
            db.execute("INSERT INTO training_evaluations VALUES(?,?)", (now_iso(), json.dumps({"name": name, "accepted": False, "metrics": metrics, "comparison": comparison})))

    def infer(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A training or inference job is already running.")
        try:
            if not config.DATA_RETENTION_AUTHORIZED:
                raise ValueError("Authorized historical data retention is required.")
            import joblib
            with self.store.connection() as db:
                row = db.execute("SELECT * FROM model_versions ORDER BY trained_at DESC LIMIT 1").fetchone()
            if not row:
                raise ValueError(UNAVAILABLE)
            # Read only the server-owned artifact directory; no uploaded pickles.
            path = Path(row["artifact_path"]).resolve()
            if path.parent != config.MODEL_DIRECTORY.resolve():
                raise ValueError("Model artifact path is invalid.")
            return self._infer(joblib.load(path), row["version"])
        finally:
            self.lock.release()

    def _infer(self, artifact, version):
        rows = self.dataset()
        if not rows:
            raise ValueError(UNAVAILABLE)
        newest = max(r["as_of"] for r in rows)
        latest = [r for r in rows if r["as_of"] == newest and r["y"] is None]
        if not latest:
            return {"count": 0}
        p = probabilities(artifact, latest)
        with self.store.connection() as db:
            # Reconcile previous forecasts only when their NEXT actual session exists.
            for row in rows:
                if row["target_return"] is not None:
                    db.execute("UPDATE predictions SET actual_return=? WHERE symbol=? AND as_of=? AND actual_return IS NULL", (row["target_return"], row["symbol"], row["as_of"]))
            for row, probability in zip(latest, p):
                db.execute("INSERT OR IGNORE INTO predictions VALUES(?,?,?,?,?,?,?,?,NULL)",
                           (version, row["symbol"], row["as_of"], HORIZON, float(probability), float(1 - probability), row["price"], now_iso()))
        return {"count": len(latest), "version": version}
