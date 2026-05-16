import os
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://gulfnews.com/gold-forex"
CALLMEBOT_API = "https://api.callmebot.com/whatsapp.php"


def get_gold_prices():
    resp = requests.get(URL, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.select_one("#gold-rate table")
    if not table:
        raise RuntimeError("Could not find gold-rate table on page")
    prices = {}
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        kind = cells[0].get_text(strip=True)
        if kind in ("24 Carat", "22 Carat"):
            prices[kind] = cells[1].get_text(strip=True)
    if len(prices) != 2:
        raise RuntimeError(f"Could not extract both 24K and 22K prices, got: {prices}")
    return prices


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
        prices = get_gold_prices()
        today = datetime.now().strftime("%d %b %Y")
        message = (
            f"Gold Price ({today})\n"
            f"24K: AED {prices['24 Carat']}/g\n"
            f"22K: AED {prices['22 Carat']}/g"
        )
        send_whatsapp(message)
        print(f"OK: {message}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
