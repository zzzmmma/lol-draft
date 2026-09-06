import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from src import build_dataset as builder


def oracle_game(game_id, date, varus_role="bot", patch_version="16.1"):
    rows = []
    for side, champions in (
        ("Blue", ["Rumble", "Vi", "Ahri", "Varus", "Leona"]),
        ("Red", ["Gnar", "Lee Sin", "Azir", "Ashe", "Nautilus"]),
    ):
        team = f"Team {side}"
        common = {
            "gameid": game_id, "league": "LCK", "year": int(date[:4]),
            "date": date, "game": 1, "side": side, "teamname": team,
            "teamid": side, "result": int(side == "Blue"),
            "firstpick": int(side == "Blue"), "patch": patch_version,
        }
        team_row = {**common, "position": "team", "champion": None}
        for index, champion in enumerate(champions, 1):
            team_row[f"pick{index}"] = champion
            team_row[f"ban{index}"] = f"{side}Ban{index}"
        rows.append(team_row)
        played = champions.copy()
        if side == "Blue" and varus_role == "top":
            played[0], played[3] = played[3], played[0]
        for role, champion in zip(builder.POSITIONS, played):
            rows.append({**common, "position": role, "champion": champion})
    return rows


class RoleDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.output_patch = patch.object(builder, "PROCESSED_DIR", self.output)
        self.output_patch.start()
        self.addCleanup(self.output_patch.stop)

    def base(self, rows):
        raw = pd.DataFrame(rows)
        games, failed, _ = builder.build_base_games(raw, builder.get_schema(raw))
        self.assertTrue(failed.empty, failed.to_dict("records"))
        return games

    def dataset(self, rows):
        dataset = builder.process_dataset(self.base(rows))
        self.assertTrue(dataset["role_qa"]["passed"], dataset["role_qa"])
        return dataset

    def test_history_snapshots_flex_patch_team_and_independent_2026(self):
        rows = []
        for day in range(1, 7):
            rows += oracle_game(f"g{day}", f"2025-12-{day:02}T10:00:00Z", "top" if day <= 3 else "bot")
        rows += oracle_game("next", "2026-01-01T10:00:00Z", patch_version="16.2")
        base = self.base(rows)
        combined = builder.process_dataset(base.copy())
        only = builder.process_dataset(base[base["year"] == 2026].copy())
        self.assertTrue(combined["role_qa"]["passed"])
        self.assertTrue(only["role_qa"]["passed"])
        history = combined["champion_position_history"]
        varus = history[(history["game_id"] == "next") & (history["champion"] == "Varus")].iloc[0]
        self.assertEqual(varus["champion_top_games_before"], 3)
        self.assertEqual(varus["champion_bot_games_before"], 3)
        self.assertEqual(varus["team_champion_top_games_before"], 3)
        self.assertEqual(varus["champion_patch_position_games_before"], 0)
        self.assertEqual(varus["champion_top_rate_before"], 0.5)
        self.assertEqual(json.loads(varus["possible_roles_before"]), ["top", "bot"])
        self.assertTrue(varus["is_flex_before"])
        self.assertEqual(varus["final_position"], "bot")
        counts = [c for c in only["champion_position_history"] if c.endswith("_games_before")]
        self.assertTrue(only["champion_position_history"][counts].eq(0).all().all())
        first = history[history["game_id"] == "g1"]
        self.assertTrue(first["possible_roles_before"].eq("[]").all())
        # 팀이 바뀌어도 챔피언 전체/패치 이력은 유지하고 새 팀 이력만 0이다.
        changed = base.copy(deep=True)
        last_index = changed.index[changed["game_id"] == "next"][0]
        changed.loc[last_index, "blue_team"] = "New Team"
        changed.loc[last_index, "blue_team_id"] = "new"
        changed = builder.process_dataset(changed)["champion_position_history"]
        changed = changed[(changed["game_id"] == "next") & (changed["champion"] == "Varus")].iloc[0]
        self.assertEqual(changed["team_champion_position_games_before"], 0)
        self.assertEqual(changed["champion_total_position_games_before"], 6)

    def test_current_and_future_role_labels_cannot_change_current_features(self):
        rows = sum((oracle_game(f"g{i}", f"2026-01-{i:02}T10:00:00Z") for i in range(1, 5)), [])
        original = self.dataset(rows)
        changed_rows = copy.deepcopy(rows)
        for row in changed_rows:
            if row["gameid"] in ("g3", "g4") and row["side"] == "Blue" and row["position"] in ("top", "bot"):
                row["position"] = "bot" if row["position"] == "top" else "top"
        changed = self.dataset(changed_rows)
        for key, columns in (
            ("champion_position_history", [c for c in original["champion_position_history"] if c != "final_position"]),
            ("training", ["draft_state", "blue_role_state", "red_role_state"]),
        ):
            left = original[key][original[key]["game_id"].isin(["g1", "g2", "g3"])][columns]
            right = changed[key][changed[key]["game_id"].isin(["g1", "g2", "g3"])][columns]
            pd.testing.assert_frame_equal(left, right)
        self.assertFalse(original["training"]["target_position"].equals(changed["training"]["target_position"]))

    def test_same_timestamp_not_counted_as_prior_game(self):
        dataset = self.dataset(oracle_game("a", "2026-01-01T10:00:00Z") + oracle_game("b", "2026-01-01T10:00:00Z"))
        self.assertTrue(dataset["champion_position_history"]["champion_total_position_games_before"].eq(0).all())

    def test_no_ban_and_pre_action_role_states(self):
        rows = oracle_game("g", "2026-01-01T10:00:00Z")
        rows[0]["ban1"] = None
        dataset = self.dataset(rows)
        actions, training = dataset["actions"], dataset["training"]
        self.assertEqual(len(actions), 20)
        self.assertEqual(actions.iloc[0]["champion"], builder.NO_BAN_TOKEN)
        self.assertTrue(actions.loc[actions["action"] == "BAN", "picked_final_position"].isna().all())
        self.assertEqual(actions["picked_final_position"].notna().sum(), 10)
        self.assertTrue(training.loc[training["next_action"] == "BAN", "target_position"].isna().all())
        self.assertEqual(training["target_position"].notna().sum(), 10)
        for row in training.itertuples():
            expected = sum(action["action"] == "PICK" for action in json.loads(row.draft_state))
            self.assertEqual(len(json.loads(row.blue_role_state)) + len(json.loads(row.red_role_state)), expected)
        self.assertEqual(training.iloc[6]["blue_role_state"], "[]")
        self.assertEqual(training.iloc[6]["red_role_state"], "[]")
        for state in json.loads(training.iloc[-1]["blue_role_state"]):
            self.assertEqual(state["possible_roles"], [])
            self.assertNotIn("final_position", state)

    def test_role_mapping_failures_visible_and_do_not_drop_legacy_rows(self):
        for fault in ("missing_player", "duplicate_role", "duplicate_pick", "wrong_champion", "wrong_team", "unknown_role", "missing_champion_column"):
            with self.subTest(fault=fault):
                rows = oracle_game("bad", "2026-01-01T10:00:00Z")
                if fault == "missing_player":
                    rows.pop(1)
                elif fault == "duplicate_role":
                    rows[1]["position"] = "jng"
                elif fault == "duplicate_pick":
                    rows[0]["pick2"] = rows[0]["pick1"]
                elif fault == "wrong_champion":
                    rows[1]["champion"] = "Unknown"
                elif fault == "wrong_team":
                    rows[1]["teamname"] = "Other"
                elif fault == "unknown_role":
                    rows[1]["position"] = "adc"
                else:
                    for row in rows:
                        row.pop("champion")
                dataset = self.dataset(rows)
                self.assertEqual(len(dataset["games"]), 1)
                self.assertEqual(len(dataset["actions"]), 20)
                self.assertEqual(len(dataset["role_mapping_failures"]), 1)
                self.assertTrue(dataset["champion_position_history"]["final_position"].isna().all())
                self.assertTrue(dataset["training"]["target_position"].isna().all())
                builder.save_dataset(dataset, "test")
                self.assertEqual(pd.read_csv(self.output / "role_mapping_failures_test.csv").iloc[0]["year"], 2026)

    def test_bad_mapping_does_not_contribute_to_later_history(self):
        rows = oracle_game("bad", "2026-01-01T10:00:00Z")
        rows[1]["champion"] = "Mismatch"
        dataset = self.dataset(rows + oracle_game("good", "2026-01-02T10:00:00Z"))
        good = dataset["champion_position_history"].query("game_id == 'good'")
        self.assertTrue(good["champion_total_position_games_before"].eq(0).all())

    def test_qa_detects_corrupted_counts_labels_and_states(self):
        original = self.dataset(oracle_game("g", "2026-01-01T10:00:00Z"))
        source = self.base(oracle_game("g", "2026-01-01T10:00:00Z"))
        for key, column, value in (
            ("champion_position_history", "champion_top_games_before", 99),
            ("champion_position_history", "possible_roles_before", '["adc"]'),
            ("champion_position_history", "possible_role_count_before", 5),
            ("actions", "picked_final_position", "top"),
            ("training", "target_position", "top"),
            ("training", "blue_role_state", '[{"final_position": "bot"}]'),
        ):
            with self.subTest(column=column):
                bad = copy.deepcopy(original)
                role_sources = source.set_index("game_id")[builder.ROLE_SOURCE_COLUMNS].to_dict("index")
                bad[key].loc[0, column] = value
                self.assertFalse(builder.validate_role_dataset(bad, role_sources)["passed"])

    def test_existing_columns_and_2025_only_processing_are_unchanged(self):
        rows = oracle_game("old", "2025-12-01T10:00:00Z") + oracle_game("next", "2025-12-02T10:00:00Z")
        base = self.base(rows)
        extended = builder.process_dataset(base.copy())
        legacy_games = builder.add_team_history(builder.add_fearless_information(
            builder.assign_series_ids(base.drop(columns=builder.ROLE_SOURCE_COLUMNS)),
        ))
        legacy_actions = builder.build_actions(legacy_games)
        legacy = {
            "games": legacy_games,
            "actions": legacy_actions,
            "training": builder.build_training_samples(legacy_actions),
            "champion_history": builder.build_champion_history(legacy_games),
        }
        for key, expected in legacy.items():
            pd.testing.assert_frame_equal(extended[key][expected.columns], expected, check_exact=True)
        self.assertTrue(extended["role_qa"]["passed"])

    def test_red_first_pick_preserves_order_and_position_labels(self):
        rows = oracle_game("red_first", "2026-01-01T10:00:00Z")
        for row in rows:
            row["firstpick"] = int(row["side"] == "Red")
        dataset = self.dataset(rows)
        picks = dataset["actions"].query("action == 'PICK'")
        self.assertEqual(picks["side"].tolist(), ["RED", "BLUE", "BLUE", "RED", "RED", "BLUE", "BLUE", "RED", "RED", "BLUE"])
        self.assertEqual(picks["order"].tolist(), [7, 8, 9, 10, 11, 12, 17, 18, 19, 20])
        self.assertEqual(picks["picked_final_position"].tolist(), ["top", "top", "jng", "jng", "mid", "mid", "bot", "bot", "sup", "sup"])

    def test_missing_required_pick_still_records_failed_game(self):
        rows = oracle_game("bad_pick", "2026-01-01T10:00:00Z")
        rows[0]["pick1"] = None
        raw = pd.DataFrame(rows)
        games, failed, _ = builder.build_base_games(raw, builder.get_schema(raw))
        self.assertTrue(games.empty)
        self.assertEqual(failed.iloc[0]["year"], 2026)
        self.assertEqual(failed.iloc[0]["game_id"], "bad_pick")
        self.assertIn("픽 정보 누락", failed.iloc[0]["reason"])

    def test_flex_requires_minimum_games_and_rate(self):
        rows = sum((oracle_game(f"g{i}", f"2026-01-{i:02}T10:00:00Z", "top" if i <= 2 else "bot") for i in range(1, 8)), [])
        dataset = self.dataset(rows)
        last = dataset["champion_position_history"].query("game_id == 'g7' and champion == 'Varus'").iloc[0]
        self.assertEqual(json.loads(last["possible_roles_before"]), ["bot"])
        self.assertFalse(last["is_flex_before"])
        with patch.object(builder, "MIN_ROLE_GAMES", 1), patch.object(builder, "MIN_ROLE_RATE", 0.5):
            dataset = self.dataset(rows)
            last = dataset["champion_position_history"].query("game_id == 'g7' and champion == 'Varus'").iloc[0]
            self.assertEqual(json.loads(last["possible_roles_before"]), ["bot"])


class DownloadRegressionTests(unittest.TestCase):
    def test_existing_missing_unchanged_updated_and_failed_downloads(self):
        payload = b"a,b,c,d,e\n1,2,3,4,5\n"
        for scenario in ("new", "unchanged", "updated", "failure_with_local", "failure_without_local", "corrupt_with_local"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "archive").mkdir()
                output = root / "2026.csv"
                before = payload if scenario == "unchanged" else b"old local bytes"
                if scenario not in ("new", "failure_without_local"):
                    output.write_bytes(before)
                def download(**kwargs):
                    self.assertNotIn("fuzzy", kwargs)
                    if scenario.startswith("failure"):
                        raise OSError("simulated network failure")
                    Path(kwargs["output"]).write_bytes(b"broken" if scenario == "corrupt_with_local" else payload)
                    return kwargs["output"]
                with patch.object(builder, "RAW_DIR", root), patch.object(builder, "RAW_FILES", {2026: output}), patch.object(builder, "ARCHIVE_DIR", root / "archive"), patch.object(builder.gdown, "download", side_effect=download), contextlib.redirect_stdout(io.StringIO()):
                    if scenario == "failure_without_local":
                        with self.assertRaisesRegex(RuntimeError, "기존 로컬 CSV도 없습니다"):
                            builder.download_latest_2026()
                    else:
                        builder.download_latest_2026()
                        self.assertEqual(output.read_bytes(), before if scenario in ("failure_with_local", "corrupt_with_local") else payload)
                        if scenario == "updated":
                            self.assertTrue(any(path.read_bytes() == before for path in (root / "archive").rglob("*.csv")))
                    self.assertFalse((root / "2026_oracle_download_temp.csv").exists())


if __name__ == "__main__":
    unittest.main()
