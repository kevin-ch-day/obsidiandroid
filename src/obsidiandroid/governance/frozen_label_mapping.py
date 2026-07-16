"""Contiguous locked family labels for frozen estimators and probabilities."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload


@dataclass(frozen=True)
class FrozenLabelMapping:
    table: pd.DataFrame
    label_map_hash: str
    probability_column_hash: str

    @property
    def class_indices(self) -> list[int]:
        return self.table["class_index"].tolist()

    def encode(self, values: pd.Series) -> pd.Series:
        lookup = self.table.set_index("family_id")["class_index"]
        encoded = values.map(lookup)
        if encoded.isna().any():
            raise ValueError("A label is absent from the locked family mapping.")
        return encoded.astype(int)

    def decode(self, values: pd.Series | list[int]) -> pd.Series:
        lookup = self.table.set_index("class_index")["family_id"]
        decoded = pd.Series(values).map(lookup)
        if decoded.isna().any():
            raise ValueError("A prediction is absent from the locked family mapping.")
        return decoded.astype(int)


def freeze_label_mapping(cohort: pd.DataFrame) -> FrozenLabelMapping:
    required = {"family_id", "family_canonical"}
    if missing := required.difference(cohort.columns):
        raise ValueError(f"Locked cohort cannot create label mapping; missing {sorted(missing)}")
    table = cohort[["family_id", "family_canonical"]].drop_duplicates().copy()
    if table.groupby("family_id")["family_canonical"].nunique().gt(1).any() or table.groupby("family_canonical")["family_id"].nunique().gt(1).any():
        raise ValueError("Locked family mapping is not one-to-one.")
    table["family_id"] = pd.to_numeric(table["family_id"], errors="raise").astype(int)
    table = table.sort_values(["family_id", "family_canonical"], kind="stable").reset_index(drop=True)
    table["class_index"] = range(len(table))
    records = table[["family_id", "family_canonical", "class_index"]].to_dict("records")
    return FrozenLabelMapping(table, hash_payload(records), hash_payload([f"probability_class_{item['class_index']}__family_{item['family_id']}" for item in records]))
