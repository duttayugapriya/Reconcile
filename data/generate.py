"""
Reconcile — Synthetic Financial Dataset Generator
==================================================

DESIGN INTENT
-------------
This module produces a *deterministic, reproducible* dataset for one fiscal
period across three sources that a real month-end close reconciles:

    1. General Ledger (GL) entries
    2. Bank statement transactions
    3. Vendor invoices

We use a FIXED RANDOM SEED so judges can re-run the exact scenario and get
byte-identical results. Reproducibility is a deliberate scoring choice: it lets
the "Reconciliation Showdown" demo be verified, not just watched.

NO API KEYS, NO EXTERNAL CALLS. Everything is generated locally and written to a
SQLite file. In a real deployment, this synthetic store is swapped for the
company's ERP *behind the same MCP interface* — the agents never know the
difference.

PLANTED ANOMALIES (the three the demo must catch)
-------------------------------------------------
    A) DUPLICATE PAYMENT      — same invoice paid twice (~$12,400).
    B) MISCATEGORIZED EXPENSE — a ~$40,000 entry booked to the wrong account.
    C) VENDOR-NAME MISMATCH   — "Acme Corp." vs "ACME Corporation Inc."
Plus several LEGITIMATE-BUT-UNUSUAL entries that must NOT be flagged, to prove
the system is precise rather than trigger-happy.
"""

from __future__ import annotations

import sqlite3
import random
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path

# --- Reproducibility -------------------------------------------------------
# A single seed governs the entire dataset. Change it and you get a different
# (but still internally consistent) close. Keep it fixed for the demo.
SEED = 20260601
PERIOD = "2026-05"  # the fiscal period we are closing
DB_PATH = Path(__file__).parent / "reconcile.db"

# A small vendor master. Note "Acme Corp." — the canonical name. The anomaly
# generator will intentionally introduce a variant spelling that fuzzy lookup
# must resolve back to this entry.
VENDOR_MASTER = [
    {"vendor_id": "V001", "name": "Acme Corp.",          "category": "supplies"},
    {"vendor_id": "V002", "name": "Northwind Logistics", "category": "shipping"},
    {"vendor_id": "V003", "name": "Globex Industries",   "category": "equipment"},
    {"vendor_id": "V004", "name": "Initech LLC",         "category": "software"},
    {"vendor_id": "V005", "name": "Soylent Foods",       "category": "catering"},
]

# Chart of accounts (account_code -> human label). Used to plant and detect the
# miscategorization anomaly.
ACCOUNTS = {
    "5000": "Cost of Goods Sold",
    "6000": "Office Supplies",
    "6100": "Shipping & Freight",
    "6200": "Software Subscriptions",
    "7000": "Capital Equipment",
    "8000": "Meals & Entertainment",
}


@dataclass
class Txn:
    """One financial transaction. The same shape is reused, with a `source`
    field, across GL / bank / invoice tables so matching logic stays simple."""
    txn_id: str
    source: str          # "ledger" | "bank" | "invoice"
    period: str
    txn_date: str        # ISO date
    vendor_id: str
    vendor_name: str     # as recorded at the source (may be a variant spelling!)
    amount_cents: int    # integer cents — never use float for money
    account_code: str
    memo: str
    invoice_ref: str     # links invoice <-> payment; "" if none


def _rng() -> random.Random:
    """Return a seeded RNG. Isolated in its own function so every run that
    imports this module shares the exact same sequence."""
    return random.Random(SEED)


def _dates(rng: random.Random, n: int) -> list[str]:
    """n random dates within the period month, sorted, ISO formatted."""
    start = date(2026, 5, 1)
    out = [start + timedelta(days=rng.randint(0, 30)) for _ in range(n)]
    return [d.isoformat() for d in sorted(out)]


def generate() -> list[Txn]:
    """Build the full transaction set: clean matches + planted anomalies +
    benign-unusual entries. Returns a flat list across all three sources."""
    rng = _rng()
    txns: list[Txn] = []
    seq = 0

    def nid(prefix: str) -> str:
        nonlocal seq
        seq += 1
        return f"{prefix}{seq:05d}"

    # --- 1. CLEAN, RECONCILING TRANSACTIONS --------------------------------
    # ~100 invoices, each with a matching ledger entry AND a matching bank
    # payment. These should reconcile 3-way with zero findings.
    clean_dates = _dates(rng, 100)
    for d in clean_dates:
        v = rng.choice(VENDOR_MASTER)
        amount = rng.randint(5_00, 9_000_00)  # $5.00 .. $9,000.00 in cents
        ref = nid("INV")
        acct = {
            "supplies": "6000", "shipping": "6100", "equipment": "7000",
            "software": "6200", "catering": "8000",
        }[v["category"]]
        for src, pfx in (("invoice", "I"), ("ledger", "L"), ("bank", "B")):
            txns.append(Txn(
                txn_id=nid(pfx), source=src, period=PERIOD, txn_date=d,
                vendor_id=v["vendor_id"], vendor_name=v["name"],
                amount_cents=amount, account_code=acct,
                memo=f"Payment to {v['name']}", invoice_ref=ref,
            ))

    # --- 2. PLANTED ANOMALY A: DUPLICATE PAYMENT ---------------------------
    # Northwind invoice paid TWICE in the bank/ledger. The invoice exists once;
    # there are two identical $12,400 payments. AnomalyAgent must catch the
    # second payment as a duplicate and propose a reversal (post_adjustment).
    dup_ref = nid("INV")
    dup_amount = 12_400_00
    dup_date = "2026-05-12"
    txns.append(Txn(nid("I"), "invoice", PERIOD, dup_date, "V002",
                    "Northwind Logistics", dup_amount, "6100",
                    "Freight — bulk shipment", dup_ref))
    for _ in range(2):  # two identical payments => one is a duplicate
        txns.append(Txn(nid("L"), "ledger", PERIOD, dup_date, "V002",
                        "Northwind Logistics", dup_amount, "6100",
                        "Freight — bulk shipment", dup_ref))
        txns.append(Txn(nid("B"), "bank", PERIOD, dup_date, "V002",
                        "Northwind Logistics", dup_amount, "6100",
                        "ACH Northwind", dup_ref))

    # --- 3. PLANTED ANOMALY B: MISCATEGORIZED LARGE EXPENSE ----------------
    # A ~$40,000 Globex equipment purchase wrongly booked to 8000
    # (Meals & Entertainment) instead of 7000 (Capital Equipment).
    # AnomalyAgent must flag the category mismatch on a HIGH-VALUE item.
    mis_ref = nid("INV")
    mis_amount = 40_127_00  # gives the demo a precise dollar figure
    mis_date = "2026-05-22"
    txns.append(Txn(nid("I"), "invoice", PERIOD, mis_date, "V003",
                    "Globex Industries", mis_amount, "7000",
                    "Server rack purchase", mis_ref))
    txns.append(Txn(nid("L"), "ledger", PERIOD, mis_date, "V003",
                    "Globex Industries", mis_amount, "8000",  # WRONG account
                    "Server rack purchase", mis_ref))
    txns.append(Txn(nid("B"), "bank", PERIOD, mis_date, "V003",
                    "Globex Industries", mis_amount, "8000",
                    "WIRE Globex", mis_ref))

    # --- 4. PLANTED ANOMALY C: VENDOR-NAME MISMATCH ------------------------
    # Acme invoice recorded under a VARIANT spelling. lookup_vendor's fuzzy
    # match must resolve "ACME Corporation Inc." -> V001 ("Acme Corp.").
    acme_ref = nid("INV")
    acme_amount = 3_250_00
    acme_date = "2026-05-08"
    txns.append(Txn(nid("I"), "invoice", PERIOD, acme_date, "V001",
                    "ACME Corporation Inc.",  # variant spelling
                    acme_amount, "6000", "Office supplies Q2", acme_ref))
    txns.append(Txn(nid("L"), "ledger", PERIOD, acme_date, "V001",
                    "Acme Corp.", acme_amount, "6000",
                    "Office supplies Q2", acme_ref))
    txns.append(Txn(nid("B"), "bank", PERIOD, acme_date, "V001",
                    "Acme Corp.", acme_amount, "6000",
                    "ACH Acme", acme_ref))

    # --- 5. BENIGN-BUT-UNUSUAL (MUST NOT BE FLAGGED) -----------------------
    # A single legitimately large software renewal and an off-cycle catering
    # bill. These look unusual but are correct. If the AnomalyAgent flags
    # these, precision is poor — the demo highlights that it does NOT.
    benign_ref = nid("INV")
    for src, pfx, memo in (("invoice", "I", "Annual SaaS renewal"),
                           ("ledger", "L", "Annual SaaS renewal"),
                           ("bank", "B", "ACH Initech")):
        txns.append(Txn(nid(pfx), src, PERIOD, "2026-05-30", "V004",
                        "Initech LLC", 28_000_00, "6200", memo, benign_ref))

    return txns


def write_db(txns: list[Txn]) -> None:
    """Persist vendor master + transactions to SQLite. The MCP server reads
    from this file. Rebuilt from scratch each run for determinism."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""CREATE TABLE vendors(
        vendor_id TEXT PRIMARY KEY, name TEXT, category TEXT)""")
    cur.execute("""CREATE TABLE accounts(code TEXT PRIMARY KEY, label TEXT)""")
    cur.execute("""CREATE TABLE transactions(
        txn_id TEXT PRIMARY KEY, source TEXT, period TEXT, txn_date TEXT,
        vendor_id TEXT, vendor_name TEXT, amount_cents INTEGER,
        account_code TEXT, memo TEXT, invoice_ref TEXT)""")
    # Append-only audit log table — written ONLY via the MCP write_audit_log
    # tool. Kept here so the schema lives in one place.
    cur.execute("""CREATE TABLE audit_log(
        ts TEXT, actor TEXT, action TEXT, detail TEXT)""")

    cur.executemany("INSERT INTO vendors VALUES (?,?,?)",
                    [(v["vendor_id"], v["name"], v["category"]) for v in VENDOR_MASTER])
    cur.executemany("INSERT INTO accounts VALUES (?,?)", list(ACCOUNTS.items()))
    cur.executemany(
        "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
        [tuple(asdict(t).values()) for t in txns],
    )
    con.commit()
    con.close()


if __name__ == "__main__":
    data = generate()
    write_db(data)
    print(f"Wrote {len(data)} transactions to {DB_PATH} "
          f"(seed={SEED}, period={PERIOD}).")
    print("Planted anomalies: duplicate $12,400, miscategorized $40,127, "
          "vendor-name mismatch $3,250.")
        con.commit()
    con.close()
    print(f"Wrote {len(txns)} transactions + {len(VENDOR_MASTER)} vendors "
          f"to {DB_PATH}")


if __name__ == "__main__":
    # Deterministic rebuild. Safe to run repeatedly; the DB is dropped first.
    write_db(generate())

