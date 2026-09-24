"""Product roles: which products carry which trap, decided before the world is built.

Roles never overlap. A product carries at most one role, so every planted count
maps to exactly one cause, and one trap can never hide another.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config


def assign_roles(products: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Assigns one role per product and picks the branch-depot products.

    Args:
        products: Product master.
        rng: Random generator.

    Returns:
        One row per product with ``role`` and ``is_branch`` columns.
    """
    shuffled = rng.permutation(products["product_code"].to_numpy())
    planned = np.repeat(list(config.PRODUCT_ROLES), list(config.PRODUCT_ROLES.values()))
    if len(planned) > len(shuffled):
        raise ValueError("More role slots than products.")
    roles = pd.DataFrame({
        "product_code": shuffled,
        "role": np.concatenate([planned, np.full(len(shuffled) - len(planned), "normal")]),
    })
    eligible = roles.loc[~roles["role"].isin(config.NOT_BRANCH_ROLES), "product_code"].to_numpy()
    branch = rng.choice(eligible, config.BRANCH_PRODUCTS, replace=False)
    roles["is_branch"] = roles["product_code"].isin(branch)
    return roles.sort_values("product_code").reset_index(drop=True)


def role_codes(roles: pd.DataFrame, role: str) -> np.ndarray:
    """Returns the sorted product codes that carry a role."""
    return np.sort(roles.loc[roles["role"] == role, "product_code"].to_numpy())
