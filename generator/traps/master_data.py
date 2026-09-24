"""Master-data traps T13 and T15: flags that lie and codes that are dirty."""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config
from generator.common import manifest_rows

EN_DASH = "–"
NO_BREAK_SPACE = " "
# "x" typed as the multiplication sign, then read with the wrong code page:
# U+00D7 in UTF-8 is C3 97, which cp1252 shows as "Ã—".
MOJIBAKE_TIMES = "×".encode("utf-8").decode("cp1252")


def plant_t13_currency_flags(products: pd.DataFrame, roles: pd.DataFrame,
                             rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """T13: sets currency flags in the product master that do not match reality.

    One brand is traded in USD everywhere, but every master row flags it EUR.
    EUR and USD prices are about the same size, so only the movement currency
    reveals it. A few single products are flagged TL while their prices are
    FX-sized; a magnitude check catches those.

    Args:
        products: Product master.
        roles: Product roles.
        rng: Random generator.

    Returns:
        The products with a changed ``master_currency``, and the manifest rows.
    """
    products = products.copy()
    mislabeled = products["brand"] == config.MISLABELED_BRAND
    products.loc[mislabeled, "master_currency"] = config.MISLABELED_BRAND_FLAG

    role = products["product_code"].map(roles.set_index("product_code")["role"])
    eligible = products[products["brand"].isin(config.MAGNITUDE_OUTLIER_BRANDS)
                        & ~role.isin(config.NO_MOVEMENT_ROLES)]
    outliers = np.sort(rng.choice(eligible["product_code"].to_numpy(), config.MAGNITUDE_OUTLIERS, replace=False))
    products.loc[products["product_code"].isin(outliers), "master_currency"] = config.MAGNITUDE_OUTLIER_FLAG

    brand_rows = products[mislabeled]
    outlier_rows = products[products["product_code"].isin(outliers)]
    manifest = pd.concat([
        manifest_rows("T13", "T13a_brand_flag_mismatch", "product", brand_rows["product_code"],
                      brand_rows["currency"],
                      f"Brand {config.MISLABELED_BRAND}: master flags {config.MISLABELED_BRAND_FLAG}, "
                      "every movement is USD. Expected value: true currency."),
        manifest_rows("T13", "T13b_magnitude_outlier", "product", outlier_rows["product_code"],
                      outlier_rows["currency"],
                      f"Master flags {config.MAGNITUDE_OUTLIER_FLAG} but the price is FX-sized. "
                      "Expected value: true currency."),
    ], ignore_index=True)
    return products, manifest


def _dirty(codes: pd.Series, kind: str) -> pd.Series:
    """Applies one kind of dirt to clean product codes."""
    if kind == "double_dash":
        return codes.str.replace("-", "--", n=1, regex=False)
    if kind == "trailing_space":
        return codes + " "
    if kind == "leading_space":
        return " " + codes
    if kind == "non_breaking_space":
        return codes + NO_BREAK_SPACE
    if kind == "en_dash":
        return codes.str.replace("-", EN_DASH, n=1, regex=False)
    if kind == "mojibake":
        return codes.str.replace("x", MOJIBAKE_TIMES, regex=False)
    raise ValueError(f"Unknown dirt kind: {kind}")


def clean_code(codes: pd.Series) -> pd.Series:
    """Reverses every kind of dirt that T15 plants. Staging will need the same logic."""
    return (codes.str.replace(MOJIBAKE_TIMES, "x", regex=False)
            .str.replace(EN_DASH, "-", regex=False)
            .str.replace(NO_BREAK_SPACE, " ", regex=False)
            .str.strip()
            .str.replace(r"-{2,}", "-", regex=True))


def plant_t15_dirty_codes(products: pd.DataFrame, rng: np.random.Generator) -> tuple[dict[str, str], pd.DataFrame]:
    """T15: makes some product codes dirty and records the near-duplicate families.

    The raw code stays the ERP key, so the same dirty code appears in the
    master, the movements and both balance sources.

    Args:
        products: Product master with clean codes.
        rng: Random generator.

    Returns:
        A mapping from clean code to raw code, and the manifest rows.
    """
    seals = products.loc[products["group_code"] == "SEL", "product_code"].to_numpy()
    mojibake = rng.choice(seals, config.DIRTY_CODES["mojibake"], replace=False)
    others = products.loc[~products["product_code"].isin(mojibake), "product_code"].to_numpy()
    other_kinds = {kind: count for kind, count in config.DIRTY_CODES.items() if kind != "mojibake"}
    picked = rng.choice(others, sum(other_kinds.values()), replace=False)
    kinds = pd.Series(np.concatenate([np.repeat(list(other_kinds), list(other_kinds.values())),
                                      np.full(len(mojibake), "mojibake")]))
    clean = pd.Series(np.concatenate([picked, mojibake]))
    raw = pd.concat([_dirty(clean[kinds == kind], kind) for kind in config.DIRTY_CODES]).sort_index()
    if (clean_code(raw) != clean).any():
        raise RuntimeError("clean_code does not reverse every planted dirty code.")

    families = (products.groupby(["group_code", "base_code"]).size().rename("members").reset_index()
                .query("members > 1").sort_values("base_code"))
    manifest = pd.concat([
        manifest_rows("T15", "T15a_dirty_code", "product", raw, clean,
                      kinds.str.replace("_", " ") + ". Expected value: cleaned code."),
        manifest_rows("T15", "T15b_near_duplicate_family", "base_code", families["base_code"], families["members"],
                      "Same size, different brand or material: a base-code match is not a product match."),
    ], ignore_index=True)
    return dict(zip(clean, raw)), manifest


def apply_code_mapping(frame: pd.DataFrame, mapping: dict[str, str], column: str = "product_code") -> pd.DataFrame:
    """Replaces clean product codes with their raw ERP codes."""
    frame = frame.copy()
    frame[column] = frame[column].map(lambda code: mapping.get(code, code))
    return frame
