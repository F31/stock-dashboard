"""One-time script: backfill ip_location for existing operation_logs rows."""
import sqlite3
import ipaddress
import time
import requests

DB_PATH = "data/stock_dashboard.db"


def get_ip_location(ip: str) -> str:
    if not ip or ip == "unknown":
        return ""
    labels = {"127.0.0.1": "本机", "::1": "本机"}
    if ip in labels:
        return labels[ip]
    try:
        if ipaddress.ip_address(ip).is_private:
            return "内网"
    except ValueError:
        pass
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"lang": "zh-CN", "fields": "status,country,regionName,city"},
            timeout=3,
        )
        d = r.json()
        if d.get("status") == "success":
            parts = [d.get("country", ""), d.get("regionName", ""), d.get("city", "")]
            return " ".join(p for p in parts if p)
    except Exception as e:
        print(f"  [warn] {ip}: {e}")
    return ""


def main():
    conn = sqlite3.connect(DB_PATH)
    # Ensure column exists
    cols = [c[1] for c in conn.execute("PRAGMA table_info(operation_logs)").fetchall()]
    if "ip_location" not in cols:
        conn.execute("ALTER TABLE operation_logs ADD COLUMN ip_location VARCHAR(100) DEFAULT ''")
        conn.commit()
        print("Column ip_location created.")

    rows = conn.execute(
        "SELECT id, ip_address FROM operation_logs WHERE (ip_location IS NULL OR ip_location = '') AND ip_address != ''"
    ).fetchall()

    print(f"Found {len(rows)} rows to backfill...")

    updated = 0
    for row_id, ip in rows:
        loc = get_ip_location(ip)
        conn.execute("UPDATE operation_logs SET ip_location = ? WHERE id = ?", (loc, row_id))
        conn.commit()
        print(f"  #{row_id}  {ip:20s}  →  {loc or '(empty)'}")
        updated += 1
        # ip-api.com free tier: 45 req/min — stay well within limit
        time.sleep(0.5)

    print(f"\nDone. {updated} rows updated.")
    conn.close()


if __name__ == "__main__":
    main()
