"""
model.py
==================================================
The AI Prediction module. Uses a Random Forest classifier (scikit-learn)
to turn four inputs -- diarrhea cases, fever cases, water turbidity, and
rainfall -- into a Low / Medium / High outbreak risk prediction.

This trains itself automatically the first time it's imported (on a
realistic synthetic training set) and then caches the trained model in
memory, so there is no separate "training step" you have to remember to
run before starting the app -- one less place for setup errors to creep
in.
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

_model = None
_scaler = None


def _build_training_data():
    # Features: [diarrhea_cases, fever_cases, water_turbidity, rainfall_mm]
    X_train = np.array([
        [0, 0, 2, 100], [0, 1, 2, 100], [1, 0, 2, 80], [1, 1, 1, 60],
        [0, 0, 3, 150], [2, 2, 3, 120], [1, 1, 4, 180], [2, 1, 3, 130],
        [3, 3, 5, 200], [4, 4, 6, 250], [5, 5, 7, 300], [4, 3, 5, 210],
        [1, 2, 2, 90], [2, 1, 3, 110], [3, 2, 4, 140], [4, 3, 5, 180],
        [5, 4, 6, 220], [2, 3, 4, 130], [3, 4, 5, 160], [4, 5, 6, 200],
        [0, 0, 1, 50], [0, 1, 2, 70], [1, 1, 3, 100], [2, 2, 4, 150],
        [3, 3, 5, 180], [4, 4, 6, 220], [5, 5, 7, 280], [6, 5, 8, 320],
        [7, 6, 8, 340], [1, 0, 1, 40], [0, 2, 2, 85], [3, 1, 4, 145],
    ])
    # 0 = Low, 1 = Medium, 2 = High
    y_train = np.array([
        0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 0, 1, 1, 2,
        2, 1, 2, 2, 0, 0, 1, 1, 2, 2, 2, 2, 2, 0, 0, 1,
    ])
    return X_train, y_train


def _train():
    global _model, _scaler
    X_train, y_train = _build_training_data()
    _scaler = StandardScaler()
    X_scaled = _scaler.fit_transform(X_train)
    _model = RandomForestClassifier(
        n_estimators=100, max_depth=8, random_state=42,
        min_samples_split=2, min_samples_leaf=1,
    )
    _model.fit(X_scaled, y_train)


def _ensure_trained():
    if _model is None or _scaler is None:
        _train()


def predict_risk(diarrhea_cases, fever_cases, water_turbidity, rainfall):
    """Returns {'risk_level': 'Low'|'Medium'|'High', 'confidence': float,
    'probabilities': {...}}"""
    _ensure_trained()

    features = np.array([[diarrhea_cases, fever_cases, water_turbidity, rainfall]])
    features_scaled = _scaler.transform(features)

    prediction = _model.predict(features_scaled)[0]
    probabilities = _model.predict_proba(features_scaled)[0]

    risk_labels = {0: "Low", 1: "Medium", 2: "High"}
    risk_level = risk_labels[int(prediction)]
    confidence = float(probabilities[int(prediction)])

    return {
        "risk_level": risk_level,
        "confidence": round(confidence, 2),
        "probabilities": {
            "low": round(float(probabilities[0]), 2),
            "medium": round(float(probabilities[1]), 2),
            "high": round(float(probabilities[2]), 2),
        },
    }


def get_feature_importance():
    _ensure_trained()
    features = ["Diarrhea Cases", "Fever Cases", "Water Turbidity", "Rainfall"]
    return {f: round(float(i), 3) for f, i in zip(features, _model.feature_importances_)}


if __name__ == "__main__":
    _ensure_trained()
    print("Model trained successfully.\n")
    print("Feature importance:", get_feature_importance())
    print("\nTest predictions:")
    for case in [(1, 1, 2, 100), (3, 3, 5, 200), (6, 5, 8, 300)]:
        result = predict_risk(*case)
        print(f"  Input {case} -> {result['risk_level']} (confidence {result['confidence']})")
