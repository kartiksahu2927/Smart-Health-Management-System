"""
app.py
==================================================
Main Flask application for the Smart Health Surveillance System.

Run with:  python app.py
Then open: http://localhost:5000

The database and ML model both initialise themselves automatically the
first time this file runs -- there is no separate setup script you need
to remember to run first.
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

import database
import model
import health_data

app = Flask(__name__)
app.secret_key = "smart-health-surveillance-secret-key-2024"

# ---- One-time startup: make sure the DB exists, make sure the model is trained ----
database.init_database(force=False)
model._ensure_trained()


def get_db():
    return database.get_connection()


def is_logged_in():
    """Simple boolean check -- deliberately returns True/False only (never
    a Flask Response object) so 'if not is_logged_in():' always behaves
    correctly at the top of a route."""
    return "user_id" in session


# ======================================================================
# AUTH: Login / Register / Forgot Password / Logout
# ======================================================================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        conn = get_db()
        user = conn.execute("SELECT * FROM Users WHERE username = ? OR email = ?",
                             (username, username)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["village_id"] = user["village_id"]
            return jsonify({"success": True, "role": user["role"]})
        return jsonify({"success": False, "message": "Invalid username or password."}), 401

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.get_json()
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        mobile = (data.get("mobile") or "").strip()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        role = data.get("role")
        village_id = data.get("village_id")

        if not all([name, email, username, password, role, village_id]):
            return jsonify({"success": False, "message": "Please fill in all required fields."}), 400

        conn = get_db()
        existing = conn.execute("SELECT id FROM Users WHERE username = ? OR email = ?",
                                 (username, email)).fetchone()
        if existing:
            conn.close()
            return jsonify({"success": False, "message": "That username or email is already registered."}), 400

        conn.execute("""
            INSERT INTO Users (name, email, username, password, mobile, role, village_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, email, username, generate_password_hash(password), mobile, role, village_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Registration successful. You can now log in."})

    # GET: build the village dropdown, grouped by region, from the database
    conn = get_db()
    rows = conn.execute("SELECT id, name, state, region FROM Villages ORDER BY region, name").fetchall()
    conn.close()

    grouped = {}
    for row in rows:
        grouped.setdefault(row["region"], []).append(row)

    return render_template("register.html", grouped_villages=grouped)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        data = request.get_json()
        email = (data.get("email") or "").strip().lower()

        conn = get_db()
        user = conn.execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if not user:
            # Don't reveal whether the email exists -- standard practice
            return jsonify({"success": True,
                             "message": "If that email is registered, password reset instructions would be sent to it."})

        # NOTE: this demo has no email server configured. In a real
        # deployment this is where you'd email a reset link. For this
        # project we surface a one-time demo token directly so the flow
        # is fully testable without SMTP setup.
        return jsonify({
            "success": True,
            "message": "Demo mode: no email server is configured, so here is your reset confirmation directly.",
            "demo_note": f"Account found for {user['name']} ({user['role']}). "
                          f"In production this would arrive by email instead of on-screen."
        })

    return render_template("forgot_password.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ======================================================================
# DASHBOARD
# ======================================================================

@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    conn = get_db()
    total_reports = conn.execute("SELECT COUNT(*) FROM HealthReports").fetchone()[0]
    villages_monitored = conn.execute("SELECT COUNT(*) FROM Villages").fetchone()[0]
    active_alerts = conn.execute("SELECT COUNT(*) FROM Alerts WHERE status = 'Active'").fetchone()[0]
    conn.close()

    snapshots = health_data.get_all_locations_live()
    high_risk_villages = len([s for s in snapshots if s["risk_level"] in ("Critical", "High")])

    return render_template("dashboard.html",
                            name=session["name"], role=session["role"],
                            total_reports=total_reports,
                            villages_monitored=villages_monitored,
                            active_alerts=active_alerts,
                            high_risk_villages=high_risk_villages)


# ======================================================================
# VILLAGE MANAGEMENT
# ======================================================================

@app.route("/villages")
def villages():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("villages.html", name=session["name"], role=session["role"])


@app.route("/api/villages", methods=["GET"])
def api_villages_list():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    search = request.args.get("q", "").strip()
    conn = get_db()
    if search:
        rows = conn.execute("""
            SELECT * FROM Villages WHERE name LIKE ? OR state LIKE ? ORDER BY name
        """, (f"%{search}%", f"%{search}%")).fetchall()
    else:
        rows = conn.execute("SELECT * FROM Villages ORDER BY name").fetchall()
    conn.close()
    return jsonify({"success": True, "villages": [dict(r) for r in rows]})


@app.route("/api/villages", methods=["POST"])
def api_villages_add():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    data = request.get_json()
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO Villages (name, state, region, district, population, latitude, longitude, water_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (data.get("name"), data.get("state"), data.get("region", "Other"),
              data.get("district", data.get("state")), data.get("population"),
              data.get("latitude"), data.get("longitude"), data.get("water_source", "Not specified")))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/villages/<int:village_id>", methods=["PUT"])
def api_villages_edit(village_id):
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    data = request.get_json()
    try:
        conn = get_db()
        conn.execute("""
            UPDATE Villages SET name=?, state=?, district=?, population=?, latitude=?, longitude=?, water_source=?
            WHERE id=?
        """, (data.get("name"), data.get("state"), data.get("district"), data.get("population"),
              data.get("latitude"), data.get("longitude"), data.get("water_source"), village_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/villages/<int:village_id>", methods=["DELETE"])
def api_villages_delete(village_id):
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    try:
        conn = get_db()
        conn.execute("DELETE FROM Villages WHERE id = ?", (village_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# ======================================================================
# HEALTH REPORTING
# ======================================================================

@app.route("/health-report", methods=["GET"])
def health_report_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    conn = get_db()
    villages_rows = conn.execute("SELECT id, name, state FROM Villages ORDER BY name").fetchall()
    recent = conn.execute("""
        SELECT hr.*, v.name as village_name FROM HealthReports hr
        JOIN Villages v ON hr.village_id = v.id
        ORDER BY hr.created_at DESC LIMIT 10
    """).fetchall()
    conn.close()
    return render_template("health_report.html", name=session["name"], role=session["role"],
                            villages=villages_rows, recent_reports=recent)


@app.route("/api/health-report", methods=["POST"])
def api_health_report_submit():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    data = request.get_json()
    try:
        conn = get_db()
        village_id = int(data.get("village_id"))
        diarrhea = int(data.get("diarrhea", 0))
        fever = int(data.get("fever", 0))
        vomiting = int(data.get("vomiting", 0))
        typhoid = int(data.get("typhoid", 0))
        cholera = int(data.get("cholera", 0))
        notes = data.get("notes", "")

        cursor = conn.execute("""
            INSERT INTO HealthReports (village_id, user_id, diarrhea, fever, vomiting, typhoid, cholera, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (village_id, session["user_id"], diarrhea, fever, vomiting, typhoid, cholera, notes))
        conn.commit()

        # Run AI prediction using this report + a representative turbidity/rainfall
        village = conn.execute("SELECT * FROM Villages WHERE id = ?", (village_id,)).fetchone()
        snapshot = health_data.get_location_by_id(village_id) if village else None
        turbidity = snapshot["water_quality"]["turbidity"] if snapshot else 3.0
        rainfall = snapshot["rainfall_mm"] if snapshot else 50.0

        result = model.predict_risk(diarrhea, fever, turbidity, rainfall)

        conn.execute("""
            INSERT INTO Predictions (village_id, risk_level, probability)
            VALUES (?, ?, ?)
        """, (village_id, result["risk_level"], result["confidence"]))

        # Auto-generate an alert for high risk
        if result["risk_level"] == "High":
            conn.execute("""
                INSERT INTO Alerts (village_id, alert_type, message, status)
                VALUES (?, ?, ?, ?)
            """, (village_id, "Outbreak Risk",
                  f"High outbreak risk predicted: {diarrhea} diarrhea, {fever} fever cases reported.",
                  "Active"))

        conn.commit()
        conn.close()

        return jsonify({"success": True, "risk_level": result["risk_level"], "confidence": result["confidence"]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# ======================================================================
# WATER QUALITY MONITORING
# ======================================================================

@app.route("/water-quality", methods=["GET"])
def water_quality_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    conn = get_db()
    villages_rows = conn.execute("SELECT id, name, state FROM Villages ORDER BY name").fetchall()
    recent = conn.execute("""
        SELECT wq.*, v.name as village_name FROM WaterQuality wq
        JOIN Villages v ON wq.village_id = v.id
        ORDER BY wq.created_at DESC LIMIT 10
    """).fetchall()
    conn.close()
    return render_template("water_quality.html", name=session["name"], role=session["role"],
                            villages=villages_rows, recent_tests=recent)


@app.route("/api/water-quality", methods=["POST"])
def api_water_quality_submit():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    data = request.get_json()
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO WaterQuality (village_id, user_id, water_source_name, ph, turbidity, temperature, bacteria_present)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (int(data.get("village_id")), session["user_id"], data.get("water_source_name"),
              float(data.get("ph")), float(data.get("turbidity")), float(data.get("temperature")),
              data.get("bacteria_present", "No")))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# ======================================================================
# AI PREDICTION (standalone tool page)
# ======================================================================

@app.route("/prediction")
def prediction_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    conn = get_db()
    villages_rows = conn.execute("SELECT id, name, state FROM Villages ORDER BY name").fetchall()
    conn.close()
    return render_template("prediction.html", name=session["name"], role=session["role"], villages=villages_rows)


@app.route("/api/predict", methods=["POST"])
def api_predict():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    data = request.get_json()
    try:
        result = model.predict_risk(
            diarrhea_cases=float(data.get("diarrhea", 0)),
            fever_cases=float(data.get("fever", 0)),
            water_turbidity=float(data.get("turbidity", 0)),
            rainfall=float(data.get("rainfall", 0)),
        )
        importance = model.get_feature_importance()
        return jsonify({"success": True, "result": result, "feature_importance": importance})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# ======================================================================
# ALERTS
# ======================================================================

@app.route("/alerts")
def alerts_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("alerts.html", name=session["name"], role=session["role"])


@app.route("/api/alerts")
def api_alerts_list():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    conn = get_db()
    rows = conn.execute("""
        SELECT a.*, v.name as village_name, v.state FROM Alerts a
        JOIN Villages v ON a.village_id = v.id
        ORDER BY a.alert_date DESC LIMIT 50
    """).fetchall()
    conn.close()

    # Also surface live high-risk locations as "system-generated" alerts
    # even if no one has manually filed a report yet -- keeps this page
    # meaningful from the very first run.
    live_alerts = []
    for snapshot in health_data.get_all_locations_live():
        if snapshot["risk_level"] in ("Critical", "High"):
            live_alerts.append({
                "id": f"live-{snapshot['id']}",
                "village_name": snapshot["name"],
                "state": snapshot["state"],
                "alert_type": "Live Risk Monitor",
                "message": f"{snapshot['risk_level']} risk: {snapshot['total_cases']} active cases, "
                           f"water turbidity {snapshot['water_quality']['turbidity']} NTU.",
                "status": "Active",
                "alert_date": snapshot["last_updated"],
                "severity": snapshot["risk_level"],
            })

    return jsonify({"success": True, "alerts": [dict(r) for r in rows], "live_alerts": live_alerts})


@app.route("/api/alerts/<int:alert_id>/resolve", methods=["POST"])
def api_alert_resolve(alert_id):
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    conn = get_db()
    conn.execute("UPDATE Alerts SET status = 'Resolved' WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ======================================================================
# MAP
# ======================================================================

@app.route("/map")
def map_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("map.html", name=session["name"], role=session["role"])


@app.route("/api/map-data")
def api_map_data():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    snapshots = health_data.get_all_locations_live()
    hotspots = health_data.get_hotspot_points()
    return jsonify({"success": True, "locations": snapshots, "hotspots": hotspots})


# ======================================================================
# REPORTS
# ======================================================================

@app.route("/reports")
def reports_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("reports.html", name=session["name"], role=session["role"])


@app.route("/api/reports")
def api_reports():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    period = request.args.get("period", "weekly")
    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(period, 7)
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_db()
    reports = conn.execute("""
        SELECT hr.*, v.name as village_name FROM HealthReports hr
        JOIN Villages v ON hr.village_id = v.id
        WHERE hr.report_date >= ? ORDER BY hr.report_date DESC
    """, (since,)).fetchall()

    predictions = conn.execute("""
        SELECT p.*, v.name as village_name FROM Predictions p
        JOIN Villages v ON p.village_id = v.id
        WHERE p.prediction_date >= ? ORDER BY p.prediction_date DESC
    """, (since,)).fetchall()

    alerts = conn.execute("""
        SELECT a.*, v.name as village_name FROM Alerts a
        JOIN Villages v ON a.village_id = v.id
        WHERE a.alert_date >= ? ORDER BY a.alert_date DESC
    """, (since,)).fetchall()
    conn.close()

    totals = {"diarrhea": 0, "fever": 0, "vomiting": 0, "typhoid": 0, "cholera": 0}
    for r in reports:
        for key in totals:
            totals[key] += r[key] or 0

    return jsonify({
        "success": True,
        "period": period,
        "reports": [dict(r) for r in reports],
        "predictions": [dict(p) for p in predictions],
        "alerts": [dict(a) for a in alerts],
        "totals": totals,
    })


# ======================================================================
# ANALYTICS  (previously empty -- now fully populated)
# ======================================================================

@app.route("/analytics")
def analytics_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("analytics.html", name=session["name"], role=session["role"])


@app.route("/api/analytics")
def api_analytics():
    if "user_id" not in session:
        return jsonify({"success": False}), 401

    snapshots = health_data.get_all_locations_live()
    disease_totals = health_data.get_disease_distribution()
    region_summary = health_data.get_region_summary()

    top_areas = sorted(snapshots, key=lambda s: s["total_cases"], reverse=True)[:10]

    avg_cases = round(sum(s["total_cases"] for s in snapshots) / len(snapshots))
    avg_mortality = round(sum(s["mortality_rate"] for s in snapshots) / len(snapshots), 1)
    critical_count = len([s for s in snapshots if s["risk_level"] == "Critical"])
    alert_rate = round((critical_count / len(snapshots)) * 100)
    most_common_disease = max(disease_totals, key=disease_totals.get)

    water_vs_cases = [
        {"name": s["name"], "turbidity": s["water_quality"]["turbidity"],
         "cases": s["total_cases"], "risk": s["risk_level"]}
        for s in snapshots
    ]

    return jsonify({
        "success": True,
        "metrics": {
            "avg_cases": avg_cases,
            "avg_mortality": avg_mortality,
            "alert_rate": alert_rate,
            "most_common_disease": most_common_disease.replace("_", " ").title(),
        },
        "top_areas": [{"name": s["name"], "state": s["state"], "cases": s["total_cases"], "risk": s["risk_level"]} for s in top_areas],
        "disease_totals": disease_totals,
        "region_summary": region_summary,
        "water_vs_cases": water_vs_cases,
        "all_locations": snapshots,
    })


# ======================================================================
# AWARENESS
# ======================================================================

@app.route("/awareness")
def awareness_page():
    if not is_logged_in():
        return redirect(url_for("login"))
    return render_template("awareness.html", name=session["name"], role=session["role"])


# ======================================================================
# ADMIN PANEL
# ======================================================================

@app.route("/admin")
def admin_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))
    return render_template("admin.html", name=session["name"], role=session["role"])


@app.route("/api/admin/overview")
def api_admin_overview():
    if session.get("role") != "Admin":
        return jsonify({"success": False, "message": "Admin access required."}), 403

    conn = get_db()
    users = conn.execute("SELECT id, name, email, username, role, village_id FROM Users ORDER BY name").fetchall()
    villages_rows = conn.execute("SELECT * FROM Villages ORDER BY name").fetchall()
    predictions = conn.execute("""
        SELECT p.*, v.name as village_name FROM Predictions p
        JOIN Villages v ON p.village_id = v.id ORDER BY p.prediction_date DESC LIMIT 20
    """).fetchall()
    alerts = conn.execute("""
        SELECT a.*, v.name as village_name FROM Alerts a
        JOIN Villages v ON a.village_id = v.id ORDER BY a.alert_date DESC LIMIT 20
    """).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "users": [dict(u) for u in users],
        "villages": [dict(v) for v in villages_rows],
        "predictions": [dict(p) for p in predictions],
        "alerts": [dict(a) for a in alerts],
    })


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
def api_admin_delete_user(user_id):
    if session.get("role") != "Admin":
        return jsonify({"success": False}), 403
    conn = get_db()
    conn.execute("DELETE FROM Users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ======================================================================
# ERROR HANDLERS
# ======================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Server error", "details": str(error)}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("Smart Health Surveillance System")
    print("=" * 50)
    print("Starting server at http://localhost:5000")
    print("Login with: admin / admin123")
    print("=" * 50)
    app.run(debug=True, host="127.0.0.1", port=5000)
