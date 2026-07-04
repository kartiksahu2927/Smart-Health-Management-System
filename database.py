"""
database.py
==================================================
Creates the SQLite database and tables, and seeds it with:
  - One Village row for every location in health_data.py (38 total,
    covering every Indian state and union territory) so the Register
    page dropdown has a complete list to choose from.
  - One demo user per role (Admin, Health Officer, ASHA Worker,
    Community Volunteer) so you can log in immediately and try every
    part of the app.

This file is safe to re-run -- it drops and recreates tables each time,
which is intentional for a student/demo project so you always start from
a clean, working state.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

from health_data import LOCATIONS

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
DATABASE_PATH = os.path.join(DB_DIR, "health_system.db")


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database(force=False):
    """Create tables. If force=True (or the DB file doesn't exist yet),
    rebuild everything from scratch and reseed."""
    os.makedirs(DB_DIR, exist_ok=True)
    fresh = force or not os.path.exists(DATABASE_PATH)

    conn = get_connection()
    cursor = conn.cursor()

    if fresh:
        cursor.executescript("""
            DROP TABLE IF EXISTS Alerts;
            DROP TABLE IF EXISTS Predictions;
            DROP TABLE IF EXISTS WaterQuality;
            DROP TABLE IF EXISTS HealthReports;
            DROP TABLE IF EXISTS Users;
            DROP TABLE IF EXISTS Villages;
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Villages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            state TEXT NOT NULL,
            region TEXT NOT NULL,
            district TEXT,
            population INTEGER,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            water_source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            mobile TEXT,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'Health Officer', 'ASHA Worker', 'Community Volunteer')),
            village_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES Villages(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS HealthReports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_id INTEGER NOT NULL,
            user_id INTEGER,
            report_date DATE DEFAULT CURRENT_DATE,
            diarrhea INTEGER DEFAULT 0,
            fever INTEGER DEFAULT 0,
            vomiting INTEGER DEFAULT 0,
            typhoid INTEGER DEFAULT 0,
            cholera INTEGER DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES Villages(id),
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS WaterQuality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_id INTEGER NOT NULL,
            user_id INTEGER,
            water_source_name TEXT,
            ph REAL,
            turbidity REAL,
            temperature REAL,
            bacteria_present TEXT CHECK(bacteria_present IN ('Yes', 'No')),
            test_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES Villages(id),
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_id INTEGER NOT NULL,
            risk_level TEXT CHECK(risk_level IN ('Low', 'Medium', 'High')),
            probability REAL,
            prediction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES Villages(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_id INTEGER NOT NULL,
            alert_type TEXT,
            message TEXT,
            status TEXT DEFAULT 'Active' CHECK(status IN ('Active', 'Resolved')),
            alert_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (village_id) REFERENCES Villages(id)
        )
    """)

    conn.commit()

    if fresh:
        _seed_villages(cursor, conn)
        _seed_users(cursor, conn)
        _seed_sample_reports(cursor, conn)

    conn.close()
    return fresh


def _seed_villages(cursor, conn):
    rows = [
        (loc["name"], loc["state"], loc["region"], loc["state"], loc["population"],
         loc["lat"], loc["lon"], loc["water_source"])
        for loc in LOCATIONS
    ]
    cursor.executemany("""
        INSERT INTO Villages (name, state, region, district, population, latitude, longitude, water_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def _seed_users(cursor, conn):
    # Pick a few specific villages for the demo accounts so each role has
    # somewhere meaningful to belong to.
    village = cursor.execute("SELECT id FROM Villages WHERE name = 'Shillong'").fetchone()
    shillong_id = village["id"] if village else 1
    village = cursor.execute("SELECT id FROM Villages WHERE name = 'Varanasi'").fetchone()
    varanasi_id = village["id"] if village else 1
    village = cursor.execute("SELECT id FROM Villages WHERE name = 'Lucknow'").fetchone()
    lucknow_id = village["id"] if village else 1
    village = cursor.execute("SELECT id FROM Villages WHERE name = 'Delhi'").fetchone()
    delhi_id = village["id"] if village else 1

    demo_users = [
        ("System Administrator", "admin@healthwatch.in", "admin", "admin123", "9000000001", "Admin", delhi_id),
        ("Dr. Anjali Sharma", "officer1@healthwatch.in", "officer1", "pass123", "9000000002", "Health Officer", lucknow_id),
        ("Mary Lyngdoh", "asha1@healthwatch.in", "asha1", "pass123", "9000000003", "ASHA Worker", shillong_id),
        ("Ravi Kumar", "volunteer1@healthwatch.in", "volunteer1", "pass123", "9000000004", "Community Volunteer", varanasi_id),
    ]

    for name, email, username, password, mobile, role, village_id in demo_users:
        cursor.execute("""
            INSERT INTO Users (name, email, username, password, mobile, role, village_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, email, username, generate_password_hash(password), mobile, role, village_id))

    conn.commit()


def _seed_sample_reports(cursor, conn):
    """A handful of historical-looking reports/water tests/alerts so the
    Reports and Admin pages aren't empty on first run."""
    admin_user = cursor.execute("SELECT id FROM Users WHERE username = 'admin'").fetchone()
    user_id = admin_user["id"] if admin_user else None

    villages = cursor.execute("SELECT id, name FROM Villages LIMIT 6").fetchall()
    today = datetime.now()

    for i, v in enumerate(villages):
        days_ago = i * 2
        report_date = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO HealthReports (village_id, user_id, report_date, diarrhea, fever, vomiting, typhoid, cholera, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (v["id"], user_id, report_date, 5 + i, 3 + i, 2, 1, 0, "Routine field report"))

        cursor.execute("""
            INSERT INTO WaterQuality (village_id, user_id, water_source_name, ph, turbidity, temperature, bacteria_present, test_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (v["id"], user_id, "Primary Source", 7.0 - (i * 0.1), 3.0 + i, 26.5, "Yes" if i % 3 == 0 else "No", report_date))

    conn.commit()


def get_db_stats():
    conn = get_connection()
    stats = {}
    for table in ["Villages", "Users", "HealthReports", "WaterQuality", "Predictions", "Alerts"]:
        stats[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return stats


if __name__ == "__main__":
    init_database(force=True)
    print("Database created and seeded successfully.")
    for table, count in get_db_stats().items():
        print(f"  {table}: {count} rows")
