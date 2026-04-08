import sqlite3
import os

DB_PATH = "db/signals.db"

def _add_column_if_missing(cursor, table, column, col_type):
    """Safely add a column only if it doesn't already exist."""
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass  # Column already exists

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── Signals table ──────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        action TEXT,
        confidence INTEGER,
        limit_price REAL,
        target_price REAL,
        trailing_sl REAL,
        status TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── Settings table (single-row config) ─────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id            INTEGER PRIMARY KEY,
        ai_enabled    INTEGER DEFAULT 0,
        sandbox_mode  INTEGER DEFAULT 1,
        auto_execute  INTEGER DEFAULT 0,
        max_trades_daily INTEGER DEFAULT 5,
        trade_amount  REAL    DEFAULT 10000.0,
        max_ai_stocks INTEGER DEFAULT 10
    )''')

    # Migrate existing DBs that may be missing newer columns (each one independent)
    _add_column_if_missing(c, "settings", "sandbox_mode",     "INTEGER DEFAULT 1")
    _add_column_if_missing(c, "settings", "auto_execute",     "INTEGER DEFAULT 0")
    _add_column_if_missing(c, "settings", "max_trades_daily", "INTEGER DEFAULT 5")
    _add_column_if_missing(c, "settings", "trade_amount",     "REAL DEFAULT 10000.0")
    _add_column_if_missing(c, "settings", "max_ai_stocks",    "INTEGER DEFAULT 10")

    # ── Paper trades table ─────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        action TEXT,
        qty REAL,
        avg_price REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # ── Orders table ───────────────────────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        action TEXT,
        quantity REAL,
        order_type TEXT,
        price REAL,
        trailing_sl REAL DEFAULT 0.0,
        source TEXT DEFAULT 'USER',
        status TEXT DEFAULT 'PENDING_APPROVAL',
        signal_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # Default settings row (IGNORE if already exists)
    c.execute("""INSERT OR IGNORE INTO settings
        (id, ai_enabled, sandbox_mode, auto_execute, max_trades_daily, trade_amount, max_ai_stocks)
        VALUES (1, 0, 1, 0, 5, 10000.0, 10)""")

    conn.commit()
    conn.close()


def get_ai_status():
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT ai_enabled FROM settings WHERE id = 1")
        res = c.fetchone()
        conn.close()
        return bool(res[0]) if res else False
    except Exception:
        return False


def toggle_ai_status(enabled):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE settings SET ai_enabled=? WHERE id=1", (1 if enabled else 0,))
    conn.commit()
    conn.close()


def get_sim_config():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT sandbox_mode, auto_execute, max_trades_daily,
                        trade_amount, max_ai_stocks
                 FROM settings WHERE id = 1""")
    res = c.fetchone()
    conn.close()
    if res:
        return {
            'sandbox_mode':    bool(res[0]),
            'auto_execute':    bool(res[1]),
            'max_trades_daily': int(res[2]),
            'trade_amount':    float(res[3]),
            'max_ai_stocks':   int(res[4]) if res[4] is not None else 10,
        }
    return {
        'sandbox_mode': True, 'auto_execute': False,
        'max_trades_daily': 5, 'trade_amount': 10000.0, 'max_ai_stocks': 10
    }


def update_sim_config(sandbox_mode, auto_execute, max_trades_daily, trade_amount, max_ai_stocks=10):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE settings
                 SET sandbox_mode=?, auto_execute=?, max_trades_daily=?,
                     trade_amount=?, max_ai_stocks=?
                 WHERE id=1""",
              (int(sandbox_mode), int(auto_execute), int(max_trades_daily),
               float(trade_amount), int(max_ai_stocks)))
    conn.commit()
    conn.close()


def get_pending_signals():
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT id, symbol, action, confidence, limit_price,
                            target_price, trailing_sl, timestamp
                     FROM signals WHERE status='PENDING'
                     ORDER BY timestamp DESC""")
        cols = [d[0] for d in c.description]
        rows = [dict(zip(cols, r)) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def mark_signal_done(signal_id, new_status="EXECUTED"):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE signals SET status=? WHERE id=?", (new_status, signal_id))
    conn.commit()
    conn.close()


def add_order(symbol, action, quantity, order_type, price,
              trailing_sl=0.0, source='USER', signal_id=None):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO orders
                     (symbol, action, quantity, order_type, price,
                      trailing_sl, source, status, signal_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?)""",
              (symbol, action, quantity, order_type, price,
               trailing_sl, source, signal_id))
    conn.commit()
    conn.close()


def get_orders(source=None, status=None):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = """SELECT id, symbol, action, quantity, order_type, price,
                      trailing_sl, source, status, timestamp
               FROM orders"""
    conditions, params = [], []
    if source:
        conditions.append("source=?"); params.append(source)
    if status:
        conditions.append("status=?"); params.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp DESC"
    c.execute(query, params)
    cols = [d[0] for d in c.description]
    rows = [dict(zip(cols, r)) for r in c.fetchall()]
    conn.close()
    return rows


def update_order_status(order_id, new_status):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
    conn.commit()
    conn.close()