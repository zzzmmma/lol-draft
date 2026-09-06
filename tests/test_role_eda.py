import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from src import EDA as eda


def role_frames():
    history = []
    for side in ("BLUE", "RED"):
        for role in eda.POSITIONS:
            history.append({
                "game_id": "first", "year": 2026, "date": "2026-01-01T10:00:00Z",
                "patch": "16.10", "side": side, "team": side + " Team",
                "champion": side + "_" + role, "final_position": role,
                "possible_roles_before": "[]", "possible_role_count_before": 0,
                "is_flex_before": False,
                **{column: 0 for column in eda.FIRST_GAME_POSITION_COUNTS},
            })
    actions, training, draft = [], [], []
    states = {"BLUE": [], "RED": []}
    for index in range(20):
        pick = index >= 10
        champion = history[index - 10]["champion"] if pick else "Ban" + str(index)
        side = history[index - 10]["side"] if pick else ("BLUE" if index % 2 else "RED")
        position = history[index - 10]["final_position"] if pick else None
        action = {
            "game_id": "first", "year": 2026, "side": side, "order": index + 1,
            "action": "PICK" if pick else "BAN", "champion": champion,
            "picked_final_position": position,
        }
        actions.append(action)
        training.append({
            "game_id": "first", "year": 2026, "step": index + 1,
            "next_action": action["action"], "target_champion": champion,
            "target_position": position, "draft_state": json.dumps(draft),
            **{f"{side.lower()}_role_state": json.dumps(state) for side, state in states.items()},
        })
        draft.append({key: action[key] for key in ("order", "side", "action", "champion")})
        if pick:
            states[side].append({"side": side, "champion": champion, "possible_roles": [],
                                 "role_rates": {role: 0.0 for role in eda.POSITIONS}})
    return pd.DataFrame(history), pd.DataFrame(actions), pd.DataFrame(training)


class RoleEdaTests(unittest.TestCase):
    def audit(self, frames, **kwargs):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            qa = eda.audit_role_data(*frames, **kwargs)
        return qa, stream.getvalue()

    def test_normal_data_passes_and_does_not_print_detail_rows(self):
        qa, output = self.audit(role_frames(), only_2026=True)
        self.assertTrue(qa["passed"], qa)
        self.assertTrue(qa["first_game_leakage_checked"])
        self.assertEqual(qa["first_game_ids"], ["first"])
        self.assertNotIn("BLUE_top", output)

    def test_position_labels_missing_ban_labels_and_unknown_roles(self):
        history, actions, training = role_frames()
        history.loc[0, "final_position"] = "adc"
        actions.loc[0, "picked_final_position"] = "sup"
        actions.loc[10, "picked_final_position"] = " "
        training.loc[0, "target_position"] = "mid"
        training.loc[10, "target_position"] = None
        qa, _ = self.audit((history, actions, training))
        for check in ("Actions PICK Position 누락", "Actions BAN Position 존재",
                      "Training PICK Position 누락", "Training BAN Position 존재",
                      "Position History 허용되지 않은 Position"):
            self.assertEqual(qa["issue_counts"][check], 1)

    def test_malformed_json_non_list_invalid_roles_duplicates_and_counts(self):
        history, actions, training = role_frames()
        history.loc[0, "possible_roles_before"] = "not json"
        history.loc[1, "possible_roles_before"] = '{"top": 1}'
        history.loc[2, "possible_roles_before"] = '["adc", {}]'
        history.loc[3, "possible_roles_before"] = '["top", "top"]'
        history.loc[4, "possible_roles_before"] = '["top"]'
        qa, _ = self.audit((history, actions, training))
        self.assertEqual(qa["issue_counts"]["possible_roles JSON 파싱/리스트 형식 오류"], 2)
        self.assertEqual(qa["issue_counts"]["possible_roles 허용되지 않은 Role"], 1)
        self.assertEqual(qa["issue_counts"]["possible_roles 중복 Role"], 1)
        self.assertEqual(qa["issue_counts"]["possible_role_count와 리스트 길이 불일치"], 5)

    def test_first_game_is_chronological_and_leakage_is_reported(self):
        history, actions, training = role_frames()
        later = history.copy()
        later["game_id"] = "later"
        later["date"] = "2026-01-02T10:00:00Z"
        later[eda.FIRST_GAME_POSITION_COUNTS] = 5
        combined = pd.concat([later, history], ignore_index=True)
        qa, _ = self.audit((combined, actions, training), only_2026=True)
        self.assertEqual(qa["first_game_ids"], ["first"])
        self.assertTrue(all(value == 0 for key, value in qa["issue_counts"].items() if key.startswith("첫 경기")))
        combined.loc[10, "champion_top_games_before"] = 3
        qa, _ = self.audit((combined, actions, training), only_2026=True)
        self.assertEqual(qa["issue_counts"]["첫 경기 champion_top_games_before 0 아님/누락"], 1)

    def test_unknown_date_or_non2026_year_cannot_pass_leakage_check(self):
        history, actions, training = role_frames()
        history["date"] = "invalid"
        history.loc[0, "year"] = 2025
        qa, _ = self.audit((history, actions, training), only_2026=True)
        self.assertFalse(qa["passed"])
        self.assertFalse(qa["first_game_leakage_checked"])
        self.assertEqual(qa["issue_counts"]["2026-only History 다른 연도/연도 누락"], 1)

    def test_role_state_label_exposure_and_unpicked_champion_are_detected(self):
        history, actions, training = role_frames()
        training.loc[0, "blue_role_state"] = json.dumps([
            {"side": "BLUE", "champion": "BLUE_top", "possible_roles": ["top"],
             "role_rates": {"top": 1}, "final_position": "top"},
        ])
        qa, _ = self.audit((history, actions, training))
        self.assertEqual(qa["issue_counts"]["blue_role_state 정답 Position 입력 노출"], 1)
        self.assertEqual(qa["issue_counts"]["blue_role_state 이전 Draft Pick과 상태 불일치"], 1)

    def test_graphs_summaries_boolean_strings_and_read_only_inputs(self):
        history, actions, training = role_frames()
        history.loc[0, "possible_roles_before"] = '["top", "bot"]'
        history.loc[0, "possible_role_count_before"] = 2
        history["is_flex_before"] = "False"
        history.loc[0, "is_flex_before"] = "True"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("history.csv", "actions.csv", "training.csv")]
            for path, frame in zip(paths, (history, actions, training)):
                frame.to_csv(path, index=False)
            before = [path.read_bytes() for path in paths]
            with contextlib.redirect_stdout(io.StringIO()):
                summary = eda.run_role_eda("Test Dataset", *paths, root / "charts", only_2026=True)
            self.assertEqual(summary["Flex Pick 수"], 1)
            self.assertEqual(summary["Flex Pick 비율 (%)"], 10)
            self.assertEqual(summary["Flex Champion 수"], 1)
            self.assertEqual(summary["TOP Pick 수"], 2)
            self.assertEqual([path.read_bytes() for path in paths], before)
            self.assertEqual(len(list((root / "charts").glob("*.png"))), 5)


if __name__ == "__main__":
    unittest.main()
