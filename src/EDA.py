from pathlib import Path
import json
import math
import re

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
EDA_DIR = PROJECT_ROOT / "data" / "eda"
NO_BAN_TOKEN = "NO_BAN"
POSITIONS = ("top", "jng", "mid", "bot", "sup")
FIRST_GAME_POSITION_COUNTS = [
    "champion_total_position_games_before",
    *[f"champion_{role}_games_before" for role in POSITIONS],
]

HISTORY_RATE_CHECKS = [
    (f"{side}_{rate}", f"{side}_{count}")
    for side in ("blue", "red")
    for rate, count in (
        ("win_rate_before", "games_before"),
        ("season_win_rate_before", "season_games_before"),
        ("side_win_rate_before", "side_games_before"),
        ("patch_win_rate_before", "patch_games_before"),
        ("h2h_win_rate_before", "h2h_games_before"),
        ("last5_win_rate", "last5_games"),
        ("last10_win_rate", "last10_games"),
    )
]


def project_path(path):
    path = Path(path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def print_table(table, limit=None):
    """긴 표는 지정된 행까지만 출력하고 생략한 행 수를 알린다."""
    if table.empty:
        print("없음")
        return
    shown = table if limit is None else table.head(limit)
    with pd.option_context("display.unicode.east_asian_width", True):
        print(shown.to_string(float_format=lambda value: f"{value:.2f}"))
    if len(shown) < len(table):
        print(f"... 나머지 {len(table) - len(shown)}행 생략")


def print_section(number, title):
    print(f"\n[{number}. {title}]")


def print_missing_report(games, actions, champion_history):
    for name, frame in (
        ("Games", games),
        ("Draft Actions", actions),
        ("Champion History", champion_history),
    ):
        missing = frame.isna().sum().sort_values(ascending=False)
        print(f"\n{name}: 전체 결측값 {int(missing.sum()):,}개")
        print_table(missing[missing > 0].rename("결측치"), limit=30)

    print("\n과거 경기 수가 0인 경우의 승률 결측치는 정상입니다.")
    for rate_col, games_col in HISTORY_RATE_CHECKS:
        bad = games.loc[
            games[rate_col].isna() & (games[games_col] > 0),
            ["game_id", "blue_team", "red_team", "patch", games_col, rate_col],
        ]
        print(f"{rate_col} 이상 결측치: {len(bad)}")
        if not bad.empty:
            print_table(bad, limit=10)


def patch_sort_key(patch):
    # 소수로 비교하면 16.10과 16.1을 구분할 수 없으므로 구성 숫자로 정렬한다.
    return tuple(int(part) for part in re.findall(r"\d+", str(patch)))


def save_bar_chart(values, title, ylabel, output_path, *, horizontal=False,
                   percentage=False, colors="#3875b8"):
    """창을 띄우지 않고 저장해 두 데이터셋의 그래프를 한 번에 생성한다."""
    figure = Figure(figsize=(11, 7), layout="constrained")
    ax = figure.subplots()
    positions = range(len(values))
    labels = values.index.astype(str)
    if horizontal:
        ax.barh(positions, values.to_numpy(), color=colors)
        ax.set_yticks(list(positions), labels=labels)
        ax.invert_yaxis()
        ax.set_xlabel(ylabel)
        ax.xaxis.grid(True, alpha=0.2)
    else:
        ax.bar(positions, values.to_numpy(), color=colors)
        ax.set_xticks(list(positions), labels=labels, rotation=45 if len(values) > 4 else 0)
        if len(values) > 4:
            for label in ax.get_xticklabels():
                label.set_horizontalalignment("right")
        ax.set_ylabel(ylabel)
        ax.yaxis.grid(True, alpha=0.2)
    if percentage:
        axis = ax.xaxis if horizontal else ax.yaxis
        axis.set_major_formatter(PercentFormatter(xmax=100))
        if horizontal:
            ax.set_xlim(0, 100)
        else:
            ax.set_ylim(0, 100)
    if values.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title, fontsize=15, pad=16)
    figure.savefig(output_path, dpi=160)
    figure.clear()


def run_eda(dataset_name, games_path, actions_path, champion_history_path,
            output_dir=None):
    games_path = project_path(games_path)
    games = pd.read_csv(games_path, dtype={"patch": "string"})
    actions = pd.read_csv(project_path(actions_path), dtype={"patch": "string"})
    champion_history = pd.read_csv(
        project_path(champion_history_path), dtype={"patch": "string"}
    )
    if output_dir is None:
        output_dir = EDA_DIR / games_path.stem.removeprefix("lck_games_")
    output_dir = project_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 64)
    print(f"EDA: {dataset_name}")
    print("=" * 64)

    teams = pd.concat([games["blue_team"], games["red_team"]], ignore_index=True)
    average_actions = len(actions) / len(games) if len(games) else 0.0
    print_section(1, "기본 정보")
    print(f"전체 경기 수: {len(games):,}")
    print("연도별 경기 수:")
    print_table(games["year"].value_counts().sort_index().rename("경기 수"))
    print(f"고유 Game ID 수: {games['game_id'].nunique():,}")
    print(f"고유 팀 수: {teams.nunique()}")
    print(f"Draft Action 수: {len(actions):,}")
    print(f"경기당 평균 Draft Action 수: {average_actions:.2f}")
    print(f"Champion History 행 수: {len(champion_history):,}")
    print(f"Games 열 수: {len(games.columns)} / 자료형별 열 수:")
    print_table(games.dtypes.astype(str).value_counts().rename("열 수"))
    print("Games 미리보기 (주요 열, 최대 5행):")
    print_table(games[["game_id", "year", "patch", "blue_team", "red_team", "winner_side"]], limit=5)

    print_section(2, "결측치 및 과거 승률 검증")
    print_missing_report(games, actions, champion_history)

    # 결측치 검사 반복문과 독립적으로 한 번만 계산한다.
    side_win_rate = (
        games["winner_side"].value_counts(normalize=True)
        .reindex(["BLUE", "RED"], fill_value=0) * 100
    )
    print_section(3, "Side 승률 (%)")
    print_table(side_win_rate.rename("승률 (%)"))

    print_section(4, "팀별 경기 수 및 승 / 패 / 승률")
    print("팀별 경기 수 (내림차순):")
    print_table(teams.value_counts().rename("경기 수"))
    team_results = pd.concat([
        games[[f"{side}_team", f"{side}_result"]].rename(
            columns={f"{side}_team": "team", f"{side}_result": "win"}
        )
        for side in ("blue", "red")
    ], ignore_index=True)
    team_stats = team_results.groupby("team").agg(
        games=("win", "count"), wins=("win", "sum"), win_rate=("win", "mean")
    )
    team_stats["losses"] = team_stats["games"] - team_stats["wins"]
    team_stats["win_rate"] *= 100
    team_stats = team_stats[["games", "wins", "losses", "win_rate"]].sort_values(
        ["win_rate", "games"], ascending=False
    )
    print("\n팀 성적 (승률 내림차순, %):")
    print_table(team_stats)

    pick_counts = champion_history["champion"].value_counts()
    ban_counts = actions.loc[actions["action"] == "BAN", "champion"].value_counts()
    no_ban_count = int(actions["champion"].eq(NO_BAN_TOKEN).sum())
    draft_counts = actions["champion"].value_counts()
    print_section(5, "Champion Pick Top 20")
    print_table(pick_counts.head(20).rename("Pick 횟수"))
    print_section(6, "Champion Ban Top 20 및 NO_BAN")
    print_table(ban_counts.head(20).rename("Ban 횟수"))
    print(f"NO_BAN 횟수: {no_ban_count}")
    print_section(7, "Pick + Ban 총 등장 횟수 Top 30")
    print_table(draft_counts.head(30).rename("등장 횟수"))
    print("기존 집계 방식대로 NO_BAN도 Ban / 총 등장 횟수에 포함합니다.")

    champion_stats = champion_history.groupby("champion").agg(
        picks=("picked_side_won", "count"),
        wins=("picked_side_won", "sum"),
        win_rate=("picked_side_won", "mean"),
    )
    champion_stats["win_rate"] *= 100
    champion_stats = champion_stats.loc[champion_stats["picks"] >= 20].sort_values(
        ["win_rate", "picks"], ascending=False
    )
    print_section(8, "Champion 승률 Top 20 (최소 Pick 20회, %)")
    print_table(champion_stats.head(20))

    patch_counts = games["patch"].value_counts()
    patch_counts = patch_counts.reindex(sorted(patch_counts.index, key=patch_sort_key))
    print_section(9, "Patch별 경기 수")
    print_table(patch_counts.rename("경기 수"))
    print_section(10, "Fearless unavailable count 분포")
    print_table(games["fearless_unavailable_count"].value_counts().sort_index().rename("경기 수"))
    series_size = games.groupby("series_id").size()
    print_section(11, "Series별 경기 수 분포")
    print_table(series_size.value_counts().sort_index().rename_axis("Series 경기 수").rename("Series 수"))

    chart_specs = [
        (side_win_rate, "Blue vs Red Win Rate", "Win Rate", "side_win_rate.png",
         {"percentage": True, "colors": ["#3875b8", "#d35d65"]}),
        (pick_counts.head(20), "Top 20 Most Picked Champions", "Pick Count", "top20_picks.png",
         {"horizontal": True}),
        (ban_counts.head(20), "Top 20 Most Banned Champions", "Ban Count", "top20_bans.png",
         {"horizontal": True, "colors": "#c77842"}),
        (patch_counts, "Games by Patch", "Number of Games", "patch_games.png", {}),
        (team_stats["win_rate"], "Team Win Rate", "Win Rate", "team_win_rate.png",
         {"horizontal": True, "percentage": True}),
    ]
    for values, title, ylabel, filename, options in chart_specs:
        save_bar_chart(values, f"{dataset_name} - {title}", ylabel, output_dir / filename, **options)
    print(f"\n그래프 5개 저장: {output_dir}")

    return pd.Series({
        "경기 수": len(games),
        "팀 수": teams.nunique(),
        "챔피언 수 (Pick)": pick_counts.index.nunique(),
        "Draft Action 수": len(actions),
        "평균 Draft Action 수": average_actions,
        "Blue 승률 (%)": side_win_rate.loc["BLUE"],
        "Red 승률 (%)": side_win_rate.loc["RED"],
        "NO_BAN": no_ban_count,
        "Series 수": len(series_size),
        "평균 Series 경기 수": series_size.mean() if len(series_size) else 0.0,
    }, name=dataset_name)


def print_role_issue(label, frame, mask, columns):
    """정상인 경우 건수만 출력하며 상세 오류 행은 최대 10개로 제한한다."""
    bad = frame.loc[mask, [column for column in columns if column in frame]]
    print(f"{label}: {len(bad):,}행")
    if not bad.empty:
        shown = bad.head(10).copy()
        for column in shown.select_dtypes(include=["object", "string"]):
            shown[column] = shown[column].map(
                lambda value: str(value)[:180] + "…" if len(str(value)) > 180 else value
            )
        print_table(shown)
        if len(bad) > 10:
            print(f"... 나머지 {len(bad) - 10:,}개 오류 행 생략")
    return len(bad)


def missing_role(values):
    return values.isna() | values.astype("string").str.strip().eq("").fillna(False)


def audit_role_data(history, actions, training, *, only_2026=False):
    checks = {}
    details = ["game_id", "side", "champion", "step", "target_champion"]
    print_section("R6", "Position label 및 possible_roles QA")
    for name, frame, action_column, label_column in (
        ("Actions", actions, "action", "picked_final_position"),
        ("Training", training, "next_action", "target_position"),
    ):
        missing = missing_role(frame[label_column])
        checks[f"{name} PICK Position 누락"] = print_role_issue(
            f"{name} PICK Position 누락", frame,
            frame[action_column].eq("PICK") & missing, details + [action_column, label_column],
        )
        checks[f"{name} BAN Position 존재"] = print_role_issue(
            f"{name} BAN Position 존재", frame,
            frame[action_column].eq("BAN") & ~missing, details + [action_column, label_column],
        )
    for name, frame, column in (
        ("Position History", history, "final_position"),
        ("Actions", actions, "picked_final_position"),
        ("Training", training, "target_position"),
    ):
        checks[f"{name} 허용되지 않은 Position"] = print_role_issue(
            f"{name} 허용되지 않은 Position", frame,
            ~missing_role(frame[column]) & ~frame[column].isin(POSITIONS), details + [column],
        )
    checks["final_position 누락"] = print_role_issue(
        "final_position 누락", history, missing_role(history["final_position"]), details + ["final_position"],
    )

    parse_errors, invalid_roles, mismatched_counts, duplicate_roles = [], [], [], []
    counts = pd.to_numeric(history["possible_role_count_before"], errors="coerce")
    for raw, count in zip(history["possible_roles_before"], counts):
        try:
            roles = json.loads(raw) if isinstance(raw, str) else None
        except (ValueError, TypeError):
            roles = None
        is_list = isinstance(roles, list)
        valid = is_list and all(isinstance(role, str) and role in POSITIONS for role in roles)
        parse_errors.append(not is_list)
        invalid_roles.append(is_list and not valid)
        duplicate_roles.append(valid and len(roles) != len(set(roles)))
        mismatched_counts.append(not is_list or pd.isna(count) or count != len(roles))
    for label, mask in (
        ("possible_roles JSON 파싱/리스트 형식 오류", parse_errors),
        ("possible_roles 허용되지 않은 Role", invalid_roles),
        ("possible_roles 중복 Role", duplicate_roles),
        ("possible_role_count와 리스트 길이 불일치", mismatched_counts),
    ):
        checks[label] = print_role_issue(label, history, mask, details + ["possible_roles_before", "possible_role_count_before"])
    flags = history["is_flex_before"].astype("string").str.lower().map({"true": True, "false": False})
    checks["is_flex_before 형식 오류"] = print_role_issue(
        "is_flex_before 형식 오류", history, flags.isna(), details + ["is_flex_before"],
    )
    checks["Flex 여부와 Role 개수 불일치"] = print_role_issue(
        "Flex 여부와 Role 개수 불일치", history,
        flags.notna() & flags.ne(counts.ge(2)), details + ["is_flex_before", "possible_role_count_before"],
    )

    # 중단된 Builder 실행 등으로 새 History와 기존 CSV가 다른 경기 집합인지 확인한다.
    for name, frame, action_column in (("Actions", actions, "action"), ("Training", training, "next_action")):
        sizes = pd.concat([
            history.groupby("game_id").size().rename("position_rows"),
            frame.loc[frame[action_column].eq("PICK")].groupby("game_id").size().rename("pick_rows"),
        ], axis=1)
        checks[f"{name} 경기별 Position/PICK 행 수 불일치"] = print_role_issue(
            f"{name} 경기별 Position/PICK 행 수 불일치", sizes,
            sizes["position_rows"].ne(sizes["pick_rows"]) | sizes["position_rows"].ne(10),
            ["position_rows", "pick_rows"],
        )

    print_section("R7", "Training Draft Role 상태 QA")
    for side in ("BLUE", "RED"):
        column = f"{side.lower()}_role_state"
        if column not in training:
            print(f"{column}: 컬럼 없음 — 상태 QA를 수행할 수 없습니다.")
            checks[f"{column} 컬럼 누락"] = 1
            continue
        errors, label_leaks, pick_mismatches = [], [], []
        for row in training.itertuples():
            try:
                state = json.loads(getattr(row, column))
                draft = json.loads(row.draft_state)
                valid = isinstance(state, list) and all(
                    isinstance(entry, dict) and entry.get("side") == side
                    and isinstance(entry.get("champion"), str)
                    and isinstance(entry.get("possible_roles"), list)
                    and all(isinstance(role, str) and role in POSITIONS for role in entry["possible_roles"])
                    and isinstance(entry.get("role_rates"), dict)
                    and all(role in POSITIONS and isinstance(rate, (int, float))
                            and not isinstance(rate, bool) and math.isfinite(rate) and 0 <= rate <= 1
                            for role, rate in entry["role_rates"].items())
                    for entry in state
                )
                leaks = isinstance(state, list) and any(
                    isinstance(entry, dict) and {"final_position", "picked_final_position", "target_position"}.intersection(entry)
                    for entry in state
                )
                prior_picks = [entry["champion"] for entry in draft
                               if entry["action"] == "PICK" and entry["side"] == side]
                mismatch = not valid or [entry["champion"] for entry in state] != prior_picks
            except (ValueError, TypeError, KeyError):
                valid, leaks, mismatch = False, False, True
            errors.append(not valid)
            label_leaks.append(bool(leaks))
            pick_mismatches.append(mismatch)
        for label, mask in (("JSON/Role/비율 형식 오류", errors), ("정답 Position 입력 노출", label_leaks), ("이전 Draft Pick과 상태 불일치", pick_mismatches)):
            checks[f"{column} {label}"] = print_role_issue(f"{column} {label}", training, mask, details + [column])

    leakage_checked = False
    first_game_ids = []
    if only_2026:
        print_section("R8", "2026-only 연도 및 첫 경기 Position History 누수 검사")
        for name, frame in (("History", history), ("Actions", actions), ("Training", training)):
            checks[f"2026-only {name} 다른 연도/연도 누락"] = print_role_issue(
                f"2026-only {name} 다른 연도/연도 누락", frame,
                pd.to_numeric(frame["year"], errors="coerce").ne(2026), details + ["year"],
            )
        dates = pd.to_datetime(history["date"], errors="coerce", utc=True)
        checks["2026-only 날짜 누락/파싱 오류"] = print_role_issue(
            "2026-only 날짜 누락/파싱 오류", history, dates.isna(), details + ["date"],
        )
        first = history.loc[dates.eq(dates.min())]
        first_game_ids = first["game_id"].drop_duplicates().tolist()
        leakage_checked = not first.empty
        print(f"첫 경기: {first_game_ids}; 검사 대상 Pick: {len(first):,}행")
        if first.empty:
            print("검사 실패: 첫 경기를 식별할 수 없습니다.")
            checks["2026-only 첫 경기 식별 불가"] = 1
        for column in FIRST_GAME_POSITION_COUNTS:
            checks[f"첫 경기 {column} 0 아님/누락"] = print_role_issue(
                f"첫 경기 {column} 0 아님/누락", first,
                pd.to_numeric(first[column], errors="coerce").ne(0), details + [column],
            )
        print("검사 범위: 2026-only 연도 구성과 첫 경기 전체 챔피언 Position 이력의 0 시작 여부")
    return {"passed": not any(checks.values()), "issue_counts": checks,
            "first_game_leakage_checked": leakage_checked, "first_game_ids": first_game_ids}


def flex_group_statistics(history, column):
    stats = history.groupby(column, dropna=False).agg(picks=("champion", "size"), flex_picks=("_is_flex", "sum"))
    stats["flex_rate_pct"] = stats["flex_picks"] / stats["picks"] * 100
    return stats


def save_patch_flex_chart(stats, dataset_name, output_path):
    figure = Figure(figsize=(13, 9), layout="constrained")
    count_ax, rate_ax = figure.subplots(2, 1, sharex=True)
    positions = list(range(len(stats)))
    count_ax.bar(positions, stats["flex_picks"], color="#3875b8")
    rate_ax.bar(positions, stats["flex_rate_pct"], color="#39836c")
    count_ax.set_ylabel("Flex Pick Count")
    rate_ax.set_ylabel("Flex Pick Rate")
    rate_ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    rate_ax.set_ylim(0, 100)
    rate_ax.set_xticks(positions, labels=stats.index.astype(str), rotation=60, ha="right")
    for ax in (count_ax, rate_ax):
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        if stats.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    figure.suptitle(f"{dataset_name} - Flex Picks by Patch", fontsize=15)
    figure.savefig(output_path, dpi=160)
    figure.clear()


def run_role_eda(dataset_name, history_path, actions_path, training_path, output_dir, *, only_2026=False):
    frames = []
    required_columns = (
        ["game_id", "year", "date", "patch", "team", "champion", "final_position",
         "possible_roles_before", "possible_role_count_before", "is_flex_before", *FIRST_GAME_POSITION_COUNTS],
        ["game_id", "year", "action", "picked_final_position"],
        ["game_id", "year", "next_action", "target_position", "draft_state"],
    )
    for path, required in zip((history_path, actions_path, training_path), required_columns):
        path = project_path(path)
        frame = pd.read_csv(path, dtype={"patch": "string"})
        missing = sorted(set(required) - set(frame.columns))
        if missing:
            raise ValueError(f"Role EDA 필수 컬럼 누락: {path}; {missing}")
        frames.append(frame)
    history, actions, training = frames
    output_dir = project_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 20} {dataset_name} - Role / Position / Flex EDA {'=' * 20}")
    total = len(history)
    history["_is_flex"] = history["is_flex_before"].astype("string").str.lower().eq("true").fillna(False)
    positions = history["final_position"].value_counts().reindex(POSITIONS, fill_value=0)
    print_section("R1", "Position별 Pick 수 / 비율 (%)")
    print_table(pd.DataFrame({"picks": positions, "rate_pct": positions / total * 100 if total else positions.astype(float)}))
    print("비율 분모: 전체 Position History Pick 행. 잘못된/누락된 Position은 QA에 별도 표시합니다.")

    valid = history.loc[history["final_position"].isin(POSITIONS)]
    actual_counts = pd.crosstab(valid["champion"], valid["final_position"]).reindex(columns=POSITIONS, fill_value=0)
    actual_total = actual_counts.sum(axis=1)
    actual_rates = actual_counts.div(actual_total, axis=0) * 100
    actual_rates["picks"] = actual_total
    actual_rates["position_count"] = actual_counts.gt(0).sum(axis=1)
    print_section("R2", "챔피언별 실제 Position 분포 (%) — Pick Top 20")
    print_table(actual_rates.sort_values("picks", ascending=False), limit=20)
    multi = actual_rates[actual_rates["position_count"] >= 2].sort_values(["position_count", "picks"], ascending=False)
    print(f"\n실제로 여러 Position에서 사용된 챔피언: {len(multi)}종 (최대 20종 출력)")
    print_table(multi, limit=20)
    print("실제 Position 분포는 정상 Position 기록 기준의 사후 분석입니다. 경기 이전 Flex 판단과 구분합니다.")

    role_counts = pd.to_numeric(history["possible_role_count_before"], errors="coerce")
    distribution = pd.Series({"0 roles": int(role_counts.eq(0).sum()), "1 role": int(role_counts.eq(1).sum()),
                              "2 roles": int(role_counts.eq(2).sum()),
                              "3+ roles": int((role_counts.ge(3) & role_counts.le(5) & role_counts.mod(1).eq(0)).sum())})
    flex = history.loc[history["_is_flex"]]
    flex_count = len(flex)
    flex_rate = flex_count / total * 100 if total else 0.0
    flex_champions = flex["champion"].value_counts()
    print_section("R3", "경기 이전 Possible Role 개수 및 Flex Pick")
    print_table(distribution.rename("Pick 수"))
    print(f"Role 개수 분포에서 제외된 비정상 값: {total - int(distribution.sum()):,}행")
    print(f"Flex Pick 수: {flex_count:,} / 전체 Pick: {total:,}")
    print(f"Flex Pick 비율: {flex_rate:.2f}% / Flex Champion 수: {len(flex_champions)}")
    print("표본 부족 등으로 0 roles인 경우 Role 미확인 상태이며, 확정 단일 Role로 취급하지 않습니다.")
    print("\nFlex Champion Top 20 (경기 이전 is_flex_before=True 횟수):")
    print_table(flex_champions.rename("Flex Pick 수"), limit=20)
    print("\nChampion별 possible role 예시 (복수 Role 우선, 최대 20개 조합):")
    examples = history.groupby(["champion", "possible_roles_before", "possible_role_count_before"], dropna=False).size().rename("Pick 수").reset_index()
    examples["_multi"] = pd.to_numeric(examples["possible_role_count_before"], errors="coerce").ge(2)
    examples = examples.sort_values(["_multi", "Pick 수"], ascending=False).drop(columns="_multi")
    print_table(examples, limit=20)

    target_champions = ["Ambessa", "Aurora", "Anivia"]
    target_champion_columns = [
        "date",
        "patch",
        "team",
        "champion",
        "final_position",
        "champion_top_games_before",
        "champion_jng_games_before",
        "champion_mid_games_before",
        "champion_bot_games_before",
        "champion_sup_games_before",
        "champion_top_rate_before",
        "champion_jng_rate_before",
        "champion_mid_rate_before",
        "champion_bot_rate_before",
        "champion_sup_rate_before",
        "possible_roles_before",
        "possible_role_count_before",
        "is_flex_before",
    ]
    for champion in target_champions:
        print("\n" + "=" * 60)
        print(champion)
        print("=" * 60)
        rows = history.loc[history["champion"].eq(champion)].reindex(columns=target_champion_columns)
        print(rows.tail(20).to_string(index=False))

    patch_stats = flex_group_statistics(history, "patch")
    patch_stats = patch_stats.reindex(sorted(patch_stats.index, key=patch_sort_key))
    team_stats = flex_group_statistics(history, "team").sort_values(["flex_rate_pct", "flex_picks"], ascending=False)
    print_section("R4", "Patch별 Flex Pick 수 / 비율 (%)")
    print_table(patch_stats, limit=20)
    print_section("R5", "팀별 Flex Pick 사용 수 / 비율 (%)")
    print_table(team_stats, limit=20)
    print("Patch/팀별 Flex 비율 분모: 해당 Patch/팀의 전체 Pick 수")

    qa = audit_role_data(history, actions, training, only_2026=only_2026)
    (output_dir / "role_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Role QA: {'통과' if qa['passed'] else '이상 발견 — 위 오류 행과 role_qa.json 확인'}")
    charts = [
        (positions.rename(index=str.upper), "Position Pick Distribution", "Pick Count", "position_distribution.png", {}),
        (flex_champions.head(20), "Flex Champion Top 20", "Flex Pick Count", "flex_champions_top20.png", {"horizontal": True}),
        (distribution, "Possible Role Count Distribution", "Pick Count", "possible_role_count.png", {}),
        (team_stats["flex_rate_pct"], "Team Flex Pick Rate", "Flex Pick Rate", "team_flex_rate.png", {"horizontal": True, "percentage": True}),
    ]
    for values, title, ylabel, filename, options in charts:
        save_bar_chart(values, f"{dataset_name} - {title}", ylabel, output_dir / filename, **options)
    save_patch_flex_chart(patch_stats, dataset_name, output_dir / "flex_by_patch.png")
    print(f"Role/Flex 그래프 5개 및 QA 보고서 저장: {output_dir}")
    return pd.Series({"Flex Pick 수": flex_count, "Flex Pick 비율 (%)": flex_rate,
                      "Flex Champion 수": len(flex_champions),
                      **{f"{role.upper()} Pick 수": int(positions[role]) for role in POSITIONS}}, name=dataset_name)


def main():
    summaries = []
    for dataset_name, suffix in (("2025 + 2026", "2025_2026"), ("2026 Only", "2026_only")):
        summary = run_eda(
            dataset_name,
            PROCESSED_DIR / f"lck_games_{suffix}.csv",
            PROCESSED_DIR / f"lck_draft_actions_{suffix}.csv",
            PROCESSED_DIR / f"lck_champion_history_{suffix}.csv",
        )
        role_summary = run_role_eda(
            dataset_name,
            PROCESSED_DIR / f"lck_champion_position_history_{suffix}.csv",
            PROCESSED_DIR / f"lck_draft_actions_{suffix}.csv",
            PROCESSED_DIR / f"lck_training_samples_{suffix}.csv",
            EDA_DIR / suffix,
            only_2026=suffix == "2026_only",
        )
        summaries.append(pd.concat([summary, role_summary]))
    comparison = pd.concat(summaries, axis=1)
    decimal_rows = {"평균 Draft Action 수", "Blue 승률 (%)", "Red 승률 (%)", "평균 Series 경기 수"}
    decimal_rows.add("Flex Pick 비율 (%)")
    formatted = comparison.astype(object)
    for item in comparison.index:
        formatted.loc[item] = comparison.loc[item].map(
            lambda value: f"{value:,.2f}" if item in decimal_rows else f"{value:,.0f}"
        )
    print("\n" + "=" * 22 + " EDA 비교 요약 " + "=" * 22)
    print_table(formatted)
    return comparison


if __name__ == "__main__":
    main()
