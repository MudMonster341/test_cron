import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

URL = "https://gulfnews.com/gold-forex"
CALLMEBOT_API = "https://api.callmebot.com/whatsapp.php"
HISTORY_FILE = "gold_history.json"
UAE_OFFSET = timedelta(hours=4)
COLUMN_INDEX = {"morning": 1, "afternoon": 2, "evening": 3}
PERIOD_NAMES = {"morning": "Morning", "afternoon": "Afternoon", "evening": "Evening"}


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE) as f:
        return json.load(f)


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
        f.write("\n")


def detect_period(hour):
    if hour < 12:
        return "morning"
    if hour < 16:
        return "afternoon"
    return "evening"


def get_gold_prices(period):
    resp = requests.get(URL, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.select_one("#gold-rate table")
    if not table:
        raise RuntimeError("Could not find gold-rate table")
    col = COLUMN_INDEX[period]
    prices = {}
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) <= col:
            continue
        kind = cells[0].get_text(strip=True)
        if kind in ("24 Carat", "22 Carat"):
            prices[kind] = cells[col].get_text(strip=True)
    if len(prices) != 2:
        raise RuntimeError(f"Could not extract prices, got: {prices}")
    return prices


def get_nth_previous_price(history, today, n=1):
    dates = sorted(history.keys(), reverse=True)
    count = 0
    for d in dates:
        if d >= today:
            continue
        for period in ("Evening", "Afternoon", "Morning"):
            if period in history[d]:
                count += 1
                if count == n:
                    return float(history[d][period]["24k"]), history[d][period]["read_at"]
                break
    return None, None


def format_message(date_str, period_name, prices, diff_1d, diff_3d, diff_7d):
    lines = []
    lines.append(f"Gold Price \u2014 {date_str}")
    lines.append(f"{period_name} \u00b7 AED/g")
    lines.append("")

    for label, key in [("24K", "24 Carat"), ("22K", "22 Carat")]:
        p = prices[key]
        lines.append(f"{label}: AED {p}/g")

    lines.append("")
    diffs = [
        ("vs Yesterday", diff_1d),
        ("vs 3 days ago", diff_3d),
        ("vs Week ago", diff_7d),
    ]
    for label, diff in diffs:
        if diff is not None:
            arrow = "\u2191" if diff > 0 else "\u2193"
            pct = abs(round((diff / (float(prices["24 Carat"]) - diff)) * 100, 1)) if diff != 0 else 0
            lines.append(f"{label}: {arrow} AED {abs(diff):.2f} ({'+' if diff > 0 else ''}{diff:.2f}%)")
        else:
            lines.append(f"{label}: \u2014")

    return "\n".join(lines)


def send_whatsapp(message):
    phone = os.environ["CALLMEBOT_PHONE"]
    apikey = os.environ["CALLMEBOT_APIKEY"]
    resp = requests.get(
        CALLMEBOT_API,
        params={"phone": phone, "text": message, "apikey": apikey},
        timeout=15,
    )
    resp.raise_for_status()


def main():
    try:
        now_uae = datetime.now(timezone.utc) + UAE_OFFSET
        period = detect_period(now_uae.hour)
        period_name = PERIOD_NAMES[period]
        date_str = now_uae.strftime("%Y-%m-%d")
        read_at = now_uae.isoformat()

        prices = get_gold_prices(period)
        history = load_history()

        if date_str not in history:
            history[date_str] = {}

        if period_name in history[date_str]:
            existing = history[date_str][period_name]
            if existing["24k"] == float(prices["24 Carat"]) and existing["22k"] == float(prices["22 Carat"]):
                print(f"Unchanged for {period_name}, skipping")
                return

        history[date_str][period_name] = {
            "24k": float(prices["24 Carat"]),
            "22k": float(prices["22 Carat"]),
            "read_at": read_at,
        }
        save_history(history)

        curr_24k = float(prices["24 Carat"])
        prev_1, _ = get_nth_previous_price(history, date_str, 1)
        prev_3, _ = get_nth_previous_price(history, date_str, 3)
        prev_7, _ = get_nth_previous_price(history, date_str, 7)

        diff_1d = round(curr_24k - prev_1, 2) if prev_1 is not None else None
        diff_3d = round(curr_24k - prev_3, 2) if prev_3 is not None else None
        diff_7d = round(curr_24k - prev_7, 2) if prev_7 is not None else None

        message = format_message(date_str, period_name, prices, diff_1d, diff_3d, diff_7d)
        send_whatsapp(message)
        print(f"Sent: {message}")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
