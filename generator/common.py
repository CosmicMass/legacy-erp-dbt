"""Shared helpers: random streams, calendar, price math and manifest rows."""

from __future__ import annotations

import zlib
from collections.abc import Iterable, Sequence
from datetime import date

import numpy as np
import pandas as pd

from generator import config

PRICE_SCALE = 10**8
"""Prices are carried as integers in units of 1e-8, like a DECIMAL(28, 8) column."""

MANIFEST_COLUMNS = ["trap_id", "case_id", "entity_type", "entity_key", "expected_value", "note"]


def rng_for(component: str) -> np.random.Generator:
    """Returns an independent, reproducible random generator for one component.

    Each component gets its own stream, derived from the global seed and the
    component name. Changing one component therefore never shifts the random
    values of another one.

    Args:
        component: A stable name, for example "products" or "t04".

    Returns:
        A seeded numpy random generator.
    """
    return np.random.default_rng([config.SEED, zlib.crc32(component.encode("utf-8"))])


def business_days(start: date, end: date, weekdays: Iterable[int] = (0, 1, 2, 3, 4)) -> pd.DatetimeIndex:
    """Returns the working days between two dates, both included.

    Args:
        start: First calendar day.
        end: Last calendar day.
        weekdays: Allowed weekdays, Monday = 0.

    Returns:
        The allowed weekdays, without public holidays.
    """
    days = pd.date_range(start, end, freq="D").as_unit("ns")
    holidays = pd.DatetimeIndex([pd.Timestamp(day) for day in config.PUBLIC_HOLIDAYS]).as_unit("ns")
    return days[days.dayofweek.isin(list(weekdays)) & ~days.isin(holidays)]


WORKING_DAYS = business_days(date(config.FISCAL_YEAR, 1, 2), config.YEAR_END)
"""Working days of the fiscal year. 1 January is reserved for opening rows."""


def random_days(rng: np.random.Generator, size: int, start: date | None = None, end: date | None = None) -> np.ndarray:
    """Picks random working days, optionally inside a date window.

    Args:
        rng: Random generator.
        size: Number of days to pick.
        start: Optional first allowed day.
        end: Optional last allowed day.

    Returns:
        An array of datetime64 values.
    """
    days = WORKING_DAYS
    if start is not None:
        days = days[days >= pd.Timestamp(start)]
    if end is not None:
        days = days[days <= pd.Timestamp(end)]
    return days.values[rng.integers(0, len(days), size)]


def random_days_before(limits: pd.Series, rng: np.random.Generator) -> np.ndarray:
    """Picks a random working day strictly before each limit date.

    When no working day exists before a limit, 1 January is used.

    Args:
        limits: One limit date per wanted day.
        rng: Random generator.

    Returns:
        An array of datetime64 values, one per limit.
    """
    values = WORKING_DAYS.values
    limit_values = pd.DatetimeIndex(limits).as_unit("ns").values
    upper = np.searchsorted(values, limit_values, side="left")
    picks = np.floor(rng.random(len(upper)) * upper).astype(np.int64)
    chosen = values[np.minimum(picks, len(values) - 1)]
    fallback = np.datetime64(config.YEAR_START.isoformat()).astype(values.dtype)
    return np.where(upper > 0, chosen, fallback)


def random_days_after(limits: pd.Series, rng: np.random.Generator) -> np.ndarray:
    """Picks a random working day strictly after each limit date.

    Args:
        limits: One limit date per wanted day.
        rng: Random generator.

    Returns:
        An array of datetime64 values, one per limit.

    Raises:
        ValueError: If a limit leaves no working day before the year end.
    """
    values = WORKING_DAYS.values
    limit_values = pd.DatetimeIndex(limits).as_unit("ns").values
    lower = np.searchsorted(values, limit_values, side="right")
    if (lower >= len(values)).any():
        raise ValueError("A limit date leaves no working day before the year end.")
    picks = lower + np.floor(rng.random(len(lower)) * (len(values) - lower)).astype(np.int64)
    return values[picks]


def weighted_choice(values: Sequence | np.ndarray | pd.Series, weights: Sequence | np.ndarray | pd.Series,
                    size: int, rng: np.random.Generator) -> np.ndarray:
    """Draws values with replacement, with probability proportional to weight.

    Args:
        values: Values to draw from.
        weights: Non-negative weight per value.
        size: Number of draws.
        rng: Random generator.

    Returns:
        An array of drawn values.
    """
    values = np.asarray(values)
    weights = np.asarray(weights, dtype=float)
    return values[rng.choice(len(values), size=size, p=weights / weights.sum())]


def weighted_options(options: Sequence[tuple[float, float]], size: int, rng: np.random.Generator) -> np.ndarray:
    """Draws from a list of (value, weight) pairs.

    Args:
        options: Pairs of value and weight.
        size: Number of draws.
        rng: Random generator.

    Returns:
        An array of drawn values.
    """
    values, weights = zip(*options)
    return weighted_choice(values, weights, size, rng)


def price_level(dates: pd.Series | np.ndarray, currencies: pd.Series | np.ndarray) -> np.ndarray:
    """Returns the price level at each date, relative to the year-end level.

    TL prices rise with monthly inflation. EUR and USD prices stay flat.

    Args:
        dates: Movement dates.
        currencies: Trading currency per row.

    Returns:
        A float array; 1.0 means the year-end price.
    """
    stamps = pd.DatetimeIndex(dates)
    months_to_year_end = (pd.Timestamp(config.YEAR_END) - stamps).days.to_numpy() / 30.4
    tl_level = (1 + config.TL_MONTHLY_INFLATION) ** (-months_to_year_end)
    return np.where(np.asarray(currencies) == "TL", tl_level, 1.0)


def price_decimals(currencies: pd.Series | np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Returns how many decimals each stored price keeps (T16).

    FX prices come from discount chains and keep 8 decimals. TL prices are
    almost always typed with 2 decimals.

    Args:
        currencies: Trading currency per row.
        rng: Random generator.

    Returns:
        An integer array of decimals.
    """
    is_tl = np.asarray(currencies) == "TL"
    tl_decimals = np.where(rng.random(len(is_tl)) < config.TL_EXTRA_PRECISION_SHARE,
                           config.TL_EXTRA_PRECISION_DECIMALS, 2)
    return np.where(is_tl, tl_decimals, config.FX_PRICE_DECIMALS)


def to_price_units(prices: np.ndarray | pd.Series, decimals: np.ndarray | int) -> np.ndarray:
    """Rounds prices half-up and returns them as integers in units of 1e-8.

    Args:
        prices: Float prices.
        decimals: Decimals to keep, per row or for all rows.

    Returns:
        An int64 array of price units.
    """
    prices = np.asarray(prices, dtype=float)
    scale = 10.0 ** np.broadcast_to(np.asarray(decimals), prices.shape)
    rounded = np.floor(prices * scale + 0.5)
    return np.round(rounded * (PRICE_SCALE / scale)).astype(np.int64)


def format_fixed(values: np.ndarray | pd.Series, digits: int) -> pd.Series:
    """Formats scaled integers as fixed-point text, for example 1234 -> "12.34".

    Args:
        values: Integers scaled by 10**digits.
        digits: Number of decimals.

    Returns:
        A Series of strings.
    """
    values = np.asarray(values, dtype=np.int64)
    absolute = np.abs(values)
    sign = pd.Series(np.where(values < 0, "-", ""))
    whole = pd.Series(absolute // 10**digits).astype(str)
    fraction = pd.Series(absolute % 10**digits).astype(str).str.zfill(digits)
    return sign + whole + "." + fraction


def split_into_documents(total_lines: int, mean_lines: float, max_lines: int, rng: np.random.Generator) -> np.ndarray:
    """Splits a line total into documents with a random number of lines each.

    Args:
        total_lines: Exact number of lines to split.
        mean_lines: Average lines per document.
        max_lines: Maximum lines per document.
        rng: Random generator.

    Returns:
        Lines per document. The values sum to ``total_lines`` exactly.
    """
    guess = int(total_lines / mean_lines * 2) + 10
    counts = np.clip(rng.poisson(mean_lines - 1, guess) + 1, 1, max_lines)
    cumulative = np.cumsum(counts)
    if cumulative[-1] < total_lines:
        raise RuntimeError("Not enough documents drawn; raise the guess factor.")
    last = int(np.searchsorted(cumulative, total_lines))
    counts = counts[: last + 1].copy()
    counts[-1] -= cumulative[last] - total_lines
    return counts


def allocate_counts(total: int, weights: np.ndarray, caps: np.ndarray, rng: np.random.Generator,
                    minimum: int = 1) -> np.ndarray:
    """Splits a total into per-item counts, each between a minimum and a cap.

    Args:
        total: Exact total to allocate.
        weights: Relative weight per item.
        caps: Maximum count per item.
        rng: Random generator.
        minimum: Minimum count per item.

    Returns:
        An int64 array of counts that sums to ``total``.

    Raises:
        ValueError: If the total cannot fit between the minimums and the caps.
    """
    caps = np.asarray(caps, dtype=np.int64)
    counts = np.full(len(caps), minimum, dtype=np.int64)
    if counts.sum() > total or caps.sum() < total or (caps < minimum).any():
        raise ValueError("The total does not fit between the minimums and the caps.")
    remaining = total - counts.sum()
    weights = np.asarray(weights, dtype=float)
    while remaining > 0:
        room = caps - counts
        probability = np.where(room > 0, weights, 0.0)
        extra = np.minimum(rng.multinomial(remaining, probability / probability.sum()), room)
        counts += extra
        remaining = total - counts.sum()
    return counts


def distribute_integer(group_keys: pd.Series, totals: pd.Series, rng: np.random.Generator) -> np.ndarray:
    """Splits one integer total per group over the group's rows, at least 1 per row.

    Args:
        group_keys: Group key of every row.
        totals: Total per group key.
        rng: Random generator.

    Returns:
        An int64 array with one quantity per row. Each group sums to its total.

    Raises:
        ValueError: If a total is smaller than the number of rows in its group.
    """
    keys = group_keys.reset_index(drop=True)
    frame = pd.DataFrame({"key": keys, "weight": rng.gamma(2.0, 1.0, len(keys))})
    grouped = frame.groupby("key", sort=False)["weight"]
    rows = grouped.transform("size").to_numpy()
    spare = keys.map(totals).to_numpy(dtype=np.int64) - rows
    if (spare < 0).any():
        raise ValueError("A total is smaller than the number of rows in its group.")
    raw = frame["weight"].to_numpy() / grouped.transform("sum").to_numpy() * spare
    frame["base"] = np.floor(raw)
    frame["fraction"] = raw - frame["base"]
    remainder = spare - frame.groupby("key", sort=False)["base"].transform("sum").to_numpy()
    rank = frame.groupby("key", sort=False)["fraction"].rank(method="first", ascending=False).to_numpy() - 1
    return (1 + frame["base"].to_numpy().astype(np.int64) + (rank < remainder)).astype(np.int64)


def manifest_rows(trap_id: str, case_id: str, entity_type: str, entity_keys: Iterable,
                  expected_values: Iterable | str | None = None,
                  notes: Iterable | str | None = None) -> pd.DataFrame:
    """Builds rows for the trap manifest, the generator's answer key.

    Args:
        trap_id: Trap number, for example "T4".
        case_id: Sub-case, for example "T4_same_date_tie".
        entity_type: What the key identifies: product, account, document or metric.
        entity_keys: One key per row.
        expected_values: Expected value per row, one value for all rows, or None.
        notes: Human-readable note per row, one note for all rows, or None.

    Returns:
        A DataFrame with the manifest columns.
    """
    keys = list(entity_keys)
    frame = pd.DataFrame({"entity_key": keys})
    frame["trap_id"] = trap_id
    frame["case_id"] = case_id
    frame["entity_type"] = entity_type
    frame["expected_value"] = _broadcast(expected_values, len(keys))
    frame["note"] = _broadcast(notes, len(keys))
    return frame[MANIFEST_COLUMNS]


def _broadcast(values: Iterable | str | None, length: int) -> list:
    """Repeats a scalar to a list, or converts an iterable to a list."""
    if values is None or isinstance(values, str):
        return [values] * length
    result = [None if pd.isna(value) else str(value) for value in values]
    if len(result) != length:
        raise ValueError("Manifest values and keys have different lengths.")
    return result
