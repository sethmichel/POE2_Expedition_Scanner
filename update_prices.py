"""Re-download prices from poe.ninja into data/prices.json.

Usage: python update_prices.py [--league "League Name"]
"""
import argparse

import config
from prices import fetch_prices, save_prices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default=config.LEAGUE)
    args = parser.parse_args()

    print(f"Downloading {args.league} prices from poe.ninja...")
    data = fetch_prices(args.league)
    save_prices(data, config.PRICES_FILE)
    print(f"Saved {len(data['items'])} prices to {config.PRICES_FILE} "
          f"(1 div = {data['exalted_per_div']:.0f} ex)")


if __name__ == "__main__":
    main()
