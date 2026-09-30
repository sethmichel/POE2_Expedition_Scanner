"""Price data: fetching from poe.ninja, manual overrides, and name matching."""
import difflib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

NINJA_API = "https://poe.ninja/poe2/api/economy"
USER_AGENT = "poe2-expedition-price-checker/0.1 (personal overlay tool)"
# Every PoE2 currency-exchange category poe.ninja publishes.
EXCHANGE_TYPES = [
    "Currency", "Fragments", "Abyss", "UncutGems", "LineageSupportGems",
    "Essences", "SoulCores", "Idols", "Runes", "Ritual", "Expedition",
    "Delirium", "Breach", "Verisium",
]

UNIT_ALIASES = {
    "div": "div", "divs": "div", "divine": "div", "divines": "div", "d": "div",
    "ex": "ex", "exalt": "ex", "exalted": "ex", "exalts": "ex", "e": "ex",
    "c": "chaos", "chaos": "chaos",
}


# --- Fetching -----------------------------------------------------------------

def fetch_prices(league):
    """Download every exchange category for a league. Values are in divines."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    leagues = session.get(f"{NINJA_API}/leagues", timeout=30).json()
    league_names = [entry["name"] for entry in leagues]
    if league not in league_names:
        raise ValueError(f"League {league!r} not found. Available: {', '.join(league_names)}")

    items = {}
    rates = None
    for exchange_type in EXCHANGE_TYPES:
        try:
            response = session.get(
                f"{NINJA_API}/exchange/current/overview",
                params={"league": league, "type": exchange_type},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            print(f"  {exchange_type:<20} failed: {error}")
            continue

        core = data.get("core", {})
        if core.get("primary") != "divine":
            print(f"  {exchange_type:<20} skipped: prices not in divines ({core.get('primary')})")
            continue
        rates = rates or core.get("rates")

        names = {item["id"]: item["name"] for item in data.get("items", [])}
        count = 0
        for line in data.get("lines", []):
            name = names.get(line.get("id"))
            value = line.get("primaryValue")
            if name and value is not None:
                items[name] = {"div": value, "category": exchange_type}
                count += 1
        print(f"  {exchange_type:<20} {count} items")
        time.sleep(0.5)  # poe.ninja is a community resource; don't hammer it

    if not items or not rates:
        raise RuntimeError("No prices could be fetched from poe.ninja")

    # The reference currencies themselves aren't always listed as lines.
    items.setdefault("Divine Orb", {"div": 1.0, "category": "Currency"})
    items.setdefault("Exalted Orb", {"div": 1 / rates["exalted"], "category": "Currency"})
    items.setdefault("Chaos Orb", {"div": 1 / rates["chaos"], "category": "Currency"})

    return {
        "league": league,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "exalted_per_div": rates["exalted"],
        "chaos_per_div": rates["chaos"],
        "items": items,
    }


def save_prices(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


# --- Lookup -------------------------------------------------------------------

def normalize(name):
    name = name.replace("’", "'").replace("‘", "'").lower()
    return re.sub(r"\s+", " ", name).strip(" .")


def _numbers(text):
    return re.findall(r"\d+", text)


class PriceBook:
    def __init__(self, prices_file, manual_file, fuzzy_cutoff):
        data = json.loads(Path(prices_file).read_text(encoding="utf-8"))
        self.league = data["league"]
        self.fetched_at = data["fetched_at"]
        self.ex_per_div = data["exalted_per_div"]
        self.chaos_per_div = data["chaos_per_div"]
        self.fuzzy_cutoff = fuzzy_cutoff

        # normalized name -> (display name, value in divines)
        self._prices = {normalize(name): (name, entry["div"]) for name, entry in data["items"].items()}
        self.manual_count = self._load_manual(Path(manual_file))

    def __len__(self):
        return len(self._prices)

    def _load_manual(self, path):
        if not path.is_file():
            return 0
        count = 0
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            name, sep, amount = line.rpartition("=")
            try:
                if not sep:
                    raise ValueError("expected 'Item Name = amount unit'")
                self._prices[normalize(name)] = (name.strip(), self.to_div(amount))
                count += 1
            except ValueError as error:
                print(f"{path.name} line {number} ignored: {error}")
        return count

    def to_div(self, amount):
        """Parse a price like '100 ex', '0.5 div' or '3 chaos' into divines."""
        match = re.fullmatch(r"\s*([\d.]+)\s*([a-zA-Z]+)\s*", amount)
        unit = UNIT_ALIASES.get(match.group(2).lower()) if match else None
        if not unit:
            raise ValueError(f"can't read price {amount.strip()!r} (use e.g. '100 ex' or '0.5 div')")
        value = float(match.group(1))
        if unit == "ex":
            return value / self.ex_per_div
        if unit == "chaos":
            return value / self.chaos_per_div
        return value

    def format(self, div):
        if div >= 1:
            return f"{div:.1f} div" if div >= 10 else f"{div:.2f} div"
        ex = div * self.ex_per_div
        return f"{ex:.0f} ex" if ex >= 10 else f"{ex:.1f} ex"

    def lookup(self, name):
        """Return (display name, divines, was_fuzzy) or None."""
        key = normalize(name)
        if key in self._prices:
            display, div = self._prices[key]
            return display, div, False
        for candidate in difflib.get_close_matches(key, self._prices.keys(), n=3, cutoff=self.fuzzy_cutoff):
            if _numbers(candidate) == _numbers(key):
                display, div = self._prices[candidate]
                return display, div, True
        return None


# --- Evaluating a scan --------------------------------------------------------

@dataclass
class Reward:
    text: str             # exactly what was read off the screen
    name: str             # text without quantity / label prefix
    quantity: int
    matched_name: str | None = None
    unit_div: float | None = None
    fuzzy: bool = False

    @property
    def total_div(self):
        return None if self.unit_div is None else self.unit_div * self.quantity


def parse_reward_text(text, strip_before_colon):
    """'3x Support: Foo' -> (3, 'Support: Foo', 'Foo')."""
    quantity = 1
    match = re.match(r"^\s*(\d+)\s*[x×]\s+(.+)$", text, re.IGNORECASE)
    if match:
        quantity, text = int(match.group(1)), match.group(2)
    full = text.strip()
    short = full.split(":", 1)[1].strip() if strip_before_colon and ":" in full else full
    return quantity, full, short


def evaluate_rewards(lines, book, strip_before_colon):
    """Price each transcribed line. Sorted most valuable first, unknowns last."""
    rewards = []
    for text in lines:
        quantity, full, short = parse_reward_text(text, strip_before_colon)
        reward = Reward(text=text, name=short, quantity=quantity)
        found = book.lookup(full) or (book.lookup(short) if short != full else None)
        if found:
            reward.matched_name, reward.unit_div, reward.fuzzy = found
        rewards.append(reward)
    rewards.sort(key=lambda r: -1 if r.total_div is None else r.total_div, reverse=True)
    return rewards
