from __future__ import annotations

import unittest
from copy import deepcopy

from pipeline.loader import _validate, load_ctq_data


class DataValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid = load_ctq_data()

    def validate(self, data: dict) -> None:
        _validate(
            data["timeline"],
            data["selected"],
            data["canonical"],
            data["statuses"],
            data["relations"],
            data["sources"],
            data["viewpoint_mapping"],
        )

    def test_current_dataset_is_valid(self) -> None:
        self.validate(deepcopy(self.valid))

    def test_duplicate_relation_id_is_rejected(self) -> None:
        data = deepcopy(self.valid)
        data["relations"][1]["relation_id"] = data["relations"][0]["relation_id"]
        with self.assertRaisesRegex(ValueError, "Relation ID trùng"):
            self.validate(data)

    def test_invalid_interval_is_rejected(self) -> None:
        data = deepcopy(self.valid)
        data["canonical"][0]["valid_from"] = "2026-12-31"
        data["canonical"][0]["valid_to"] = "2026-01-01"
        with self.assertRaisesRegex(ValueError, "valid_from sau valid_to"):
            self.validate(data)

    def test_missing_active_status_is_rejected(self) -> None:
        data = deepcopy(self.valid)
        data["statuses"] = [
            row
            for row in data["statuses"]
            if not (row["arg_id"] == "CTQ-A001" and row["timestamp_id"] == "t1")
        ]
        with self.assertRaisesRegex(ValueError, "CTQ-A001 thiếu status active"):
            self.validate(data)

    def test_accepted_reference_requires_verified_official_document(self) -> None:
        data = deepcopy(self.valid)
        row = next(
            row
            for row in data["statuses"]
            if row["arg_id"] == "CTQ-A001" and row["timestamp_id"] == "t1"
        )
        row["grounded_by"] = "CTQ-S031"
        with self.assertRaisesRegex(ValueError, "accepted A_K thiếu official_document"):
            self.validate(data)

    def test_argument_may_belong_to_multiple_viewpoints(self) -> None:
        data = deepcopy(self.valid)
        argument_id = data["viewpoint_mapping"]["viewpoints"][0]["argument_ids"][0]
        data["viewpoint_mapping"]["viewpoints"][1]["argument_ids"].append(argument_id)
        self.validate(data)

    def test_argument_may_not_repeat_inside_one_viewpoint(self) -> None:
        data = deepcopy(self.valid)
        arguments = data["viewpoint_mapping"]["viewpoints"][0]["argument_ids"]
        arguments.append(arguments[0])
        with self.assertRaisesRegex(ValueError, "lặp argument"):
            self.validate(data)


if __name__ == "__main__":
    unittest.main()
