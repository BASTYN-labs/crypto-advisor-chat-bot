"""
Portfolio management — read/write user holdings and cash positions.
"""
import sqlite3
from db import get_conn


def get_holdings(user_id: str) -> dict:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT coin, amount, avg_entry_price FROM portfolios WHERE user_id = ?",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return {r["coin"]: {"amount": r["amount"], "avg_price": r["avg_entry_price"]} for r in rows}


def get_cash(user_id: str) -> float:
    holdings = get_holdings(user_id)
    return holdings.get("USD", {}).get("amount", 0.0)


def update_holding(user_id: str, coin: str, amount_delta: float, price: float) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT amount, avg_entry_price FROM portfolios WHERE user_id = ? AND coin = ?",
        (user_id, coin),
    ).fetchone()

    if existing:
        new_amount = existing["amount"] + amount_delta
        if amount_delta > 0 and existing["amount"] >= 0:
            total_cost = existing["amount"] * existing["avg_entry_price"] + amount_delta * price
            new_avg = total_cost / new_amount if new_amount > 0 else price
        else:
            new_avg = existing["avg_entry_price"]
        conn.execute(
            "UPDATE portfolios SET amount = ?, avg_entry_price = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND coin = ?",
            (max(new_amount, 0), new_avg, user_id, coin),
        )
    else:
        conn.execute(
            "INSERT INTO portfolios (user_id, coin, amount, avg_entry_price) VALUES (?, ?, ?, ?)",
            (user_id, coin, max(amount_delta, 0), price),
        )

    conn.commit()
    conn.close()


def record_transaction(
    user_id: str,
    coin: str,
    direction: str,
    amount_usd: float,
    coins_traded: float,
    price: float,
) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO transactions (user_id, coin, direction, amount_usd, coins_traded, price_at_execution) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, coin, direction, amount_usd, coins_traded, price),
    )
    conn.commit()
    conn.close()


def execute_trade(
    user_id: str,
    coin: str,
    direction: str,
    amount_usd: float,
    coins_traded: float,
    price: float,
) -> dict:
    if direction == "buy":
        update_holding(user_id, "USD", -amount_usd, 1.0)
        update_holding(user_id, coin, coins_traded, price)
    elif direction == "sell":
        update_holding(user_id, coin, -coins_traded, price)
        update_holding(user_id, "USD", amount_usd, 1.0)

    record_transaction(user_id, coin, direction, amount_usd, coins_traded, price)
    return get_holdings(user_id)
