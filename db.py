"""
Database initialisation and seed data for the crypto advisor.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "crypto_advisor.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            role TEXT DEFAULT 'user',
            risk_profile TEXT DEFAULT 'moderate',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS portfolios (
            user_id TEXT,
            coin TEXT,
            amount REAL DEFAULT 0,
            avg_entry_price REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, coin)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            coin TEXT,
            direction TEXT,
            amount_usd REAL,
            coins_traded REAL,
            price_at_execution REAL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            session_id TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.executemany(
        "INSERT OR IGNORE INTO users (id, email, name, role, risk_profile) VALUES (?, ?, ?, ?, ?)",
        [
            ("user_001", "alice@demo.com", "Alice Chen", "user", "moderate"),
            ("user_002", "bob@demo.com", "Bob Martinez", "user", "aggressive"),
            ("user_003", "carol@demo.com", "Carol Williams", "admin", "conservative"),
        ],
    )

    conn.executemany(
        "INSERT OR IGNORE INTO portfolios (user_id, coin, amount, avg_entry_price) VALUES (?, ?, ?, ?)",
        [
            ("user_001", "BTC", 0.45, 42000),
            ("user_001", "ETH", 3.20, 2800),
            ("user_001", "SOL", 80.0, 95),
            ("user_001", "USD", 16420.0, 1),
            ("user_002", "BTC", 1.20, 38000),
            ("user_002", "ETH", 5.00, 2200),
            ("user_002", "USD", 8500.0, 1),
            ("user_003", "BTC", 0.10, 55000),
            ("user_003", "USD", 42000.0, 1),
        ],
    )

    conn.commit()
    conn.close()
