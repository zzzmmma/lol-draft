from pathlib import Path
from datetime import datetime
import pandas as pd
import json
import hashlib
import shutil
import re


# ============================================================
# 설정
# ============================================================

TARGET_YEAR = 2026
TARGET_LEAGUE = "LCK"

# 현재 수집 범위를 Fearless Draft 적용 이후로 잡는다면 True
USE_FEARLESS = True

# 같은 두 팀의 경기가 이 시간보다 멀리 떨어져 있으면
# 다른 시리즈로 판단
MAX_SERIES_GAP_HOURS = 12

# Oracle 파일이 이전 실행과 동일하면
# 다시 데이터셋을 만들지 않음
SKIP_IF_SOURCE_UNCHANGED = False


# ============================================================
# 경로
# ============================================================

RAW_DIR = Path("data/raw")
ARCHIVE_DIR = Path("data/raw_archive")
PROCESSED_DIR = Path("data/processed")

RAW_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


RAW_FILE = (
    RAW_DIR
    / f"{TARGET_YEAR}_LoL_esports_match_data_from_OraclesElixir.csv"
)

METADATA_FILE = (
    PROCESSED_DIR
    / "dataset_metadata.json"
)

SOURCE_PAGE = (
    "https://oracleselixir.com/tools/downloads"
)


# ============================================================
# 기본 함수
# ============================================================

def clean_value(value):

    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def find_column(df, *names):

    lower_map = {
        column.lower(): column
        for column in df.columns
    }

    for name in names:

        if name in df.columns:
            return name

        if name.lower() in lower_map:
            return lower_map[
                name.lower()
            ]

    return None


def win_rate(wins, games):

    if games == 0:
        return None

    return wins / games


# ============================================================
# 파일 SHA256
# ============================================================

def calculate_sha256(path):

    sha = hashlib.sha256()

    with open(path, "rb") as file:

        while True:

            chunk = file.read(
                1024 * 1024
            )

            if not chunk:
                break

            sha.update(chunk)

    return sha.hexdigest()


# ============================================================
# 이전 데이터와 같은지 확인
# ============================================================

def source_is_unchanged(
    current_hash
):

    if not METADATA_FILE.exists():
        return False

    try:

        with open(
            METADATA_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            metadata = json.load(file)

        previous_hash = (
            metadata.get(
                "source_sha256"
            )
        )

        return (
            previous_hash
            == current_hash
        )

    except Exception:

        return False


# ============================================================
# Oracle 원본 보관
# ============================================================

def archive_raw_file(
    path,
    file_hash
):

    today = datetime.now().strftime(
        "%Y%m%d"
    )

    filename = (
        f"{TARGET_YEAR}_OE_"
        f"{today}_"
        f"{file_hash[:8]}.csv"
    )

    archive_path = (
        ARCHIVE_DIR
        / filename
    )

    if not archive_path.exists():

        shutil.copy2(
            path,
            archive_path
        )

        print(
            "원본 백업:",
            archive_path
        )


# ============================================================
# 챔피언 5개 가져오기
# ============================================================

def get_champions(
    row,
    prefix
):

    champions = []

    for i in range(1, 6):

        column = (
            f"{prefix}{i}"
        )

        if column not in row.index:

            champions.append(None)

        else:

            champions.append(
                clean_value(
                    row[column]
                )
            )

    return champions


# ============================================================
# First Pick 판별
# ============================================================

def is_first_pick(
    row,
    column
):

    if column is None:
        return False

    value = row[column]

    if pd.isna(value):
        return False

    value = (
        str(value)
        .strip()
        .lower()
    )

    return value in {
        "1",
        "1.0",
        "true",
        "yes"
    }


# ============================================================
# 실제 Draft 20단계 복원
# ============================================================

def reconstruct_draft_actions(
    blue_bans,
    red_bans,
    blue_picks,
    red_picks,
    first_pick_side
):

    """
    우리가 영상으로 검증한 순서.

    First Pick = BLUE

    1차 BAN
    B R B R B R

    1차 PICK
    B R R B B R

    2차 BAN
    R B R B

    2차 PICK
    R B B R


    First Pick = RED

    위 구조의 BLUE/RED 반대.
    """

    if first_pick_side == "BLUE":

        first_side = "BLUE"
        second_side = "RED"

        first_bans = blue_bans
        second_bans = red_bans

        first_picks = blue_picks
        second_picks = red_picks

    elif first_pick_side == "RED":

        first_side = "RED"
        second_side = "BLUE"

        first_bans = red_bans
        second_bans = blue_bans

        first_picks = red_picks
        second_picks = blue_picks

    else:

        return []


    actions = []


    def add(
        phase,
        side,
        action,
        champion
    ):

        actions.append({

            "phase": phase,

            "side": side,

            "action": action,

            "champion": champion
        })


    # --------------------------------------------------------
    # 1차 밴
    # --------------------------------------------------------

    for i in range(3):

        add(
            "BAN_PHASE_1",
            first_side,
            "BAN",
            first_bans[i]
        )

        add(
            "BAN_PHASE_1",
            second_side,
            "BAN",
            second_bans[i]
        )


    # --------------------------------------------------------
    # 1차 픽
    # --------------------------------------------------------

    add(
        "PICK_PHASE_1",
        first_side,
        "PICK",
        first_picks[0]
    )

    add(
        "PICK_PHASE_1",
        second_side,
        "PICK",
        second_picks[0]
    )

    add(
        "PICK_PHASE_1",
        second_side,
        "PICK",
        second_picks[1]
    )

    add(
        "PICK_PHASE_1",
        first_side,
        "PICK",
        first_picks[1]
    )

    add(
        "PICK_PHASE_1",
        first_side,
        "PICK",
        first_picks[2]
    )

    add(
        "PICK_PHASE_1",
        second_side,
        "PICK",
        second_picks[2]
    )


    # --------------------------------------------------------
    # 2차 밴
    # --------------------------------------------------------

    add(
        "BAN_PHASE_2",
        second_side,
        "BAN",
        second_bans[3]
    )

    add(
        "BAN_PHASE_2",
        first_side,
        "BAN",
        first_bans[3]
    )

    add(
        "BAN_PHASE_2",
        second_side,
        "BAN",
        second_bans[4]
    )

    add(
        "BAN_PHASE_2",
        first_side,
        "BAN",
        first_bans[4]
    )


    # --------------------------------------------------------
    # 2차 픽
    # --------------------------------------------------------

    add(
        "PICK_PHASE_2",
        second_side,
        "PICK",
        second_picks[3]
    )

    add(
        "PICK_PHASE_2",
        first_side,
        "PICK",
        first_picks[3]
    )

    add(
        "PICK_PHASE_2",
        first_side,
        "PICK",
        first_picks[4]
    )

    add(
        "PICK_PHASE_2",
        second_side,
        "PICK",
        second_picks[4]
    )


    # 순서
    for order, action in enumerate(
        actions,
        start=1
    ):

        action["order"] = order


    return actions


# ============================================================
# Series용 이름 정리
# ============================================================

def safe_name(text):

    text = str(text)

    text = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        text
    )

    return text.strip("_")


# ============================================================
# Oracle → 경기 단위 데이터
# ============================================================

def build_games(df):

    league_col = find_column(
        df,
        "league"
    )

    year_col = find_column(
        df,
        "year"
    )

    game_id_col = find_column(
        df,
        "gameid"
    )

    date_col = find_column(
        df,
        "date"
    )

    game_number_col = find_column(
        df,
        "game"
    )

    position_col = find_column(
        df,
        "position"
    )

    side_col = find_column(
        df,
        "side"
    )

    team_col = find_column(
        df,
        "teamname"
    )

    team_id_col = find_column(
        df,
        "teamid"
    )

    result_col = find_column(
        df,
        "result"
    )

    first_pick_col = find_column(
        df,
        "firstPick",
        "firstpick"
    )

    patch_col = find_column(
        df,
        "patch"
    )

    split_col = find_column(
        df,
        "split"
    )

    playoffs_col = find_column(
        df,
        "playoffs"
    )

    completeness_col = find_column(
        df,
        "datacompleteness"
    )

    url_col = find_column(
        df,
        "url"
    )


    required = {

        "league": league_col,

        "gameid": game_id_col,

        "date": date_col,

        "game": game_number_col,

        "position": position_col,

        "side": side_col,

        "teamname": team_col,

        "result": result_col,

        "firstPick": first_pick_col
    }


    missing = [
        name
        for name, column
        in required.items()
        if column is None
    ]


    if missing:

        raise ValueError(
            "필수 컬럼 없음: "
            + str(missing)
        )


    df = df.copy()

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
        utc=True
    )


    # --------------------------------------------------------
    # LCK
    # --------------------------------------------------------

    lck = df[
        df[league_col]
        .astype(str)
        .str.upper()
        == TARGET_LEAGUE
    ].copy()


    # --------------------------------------------------------
    # 연도
    # --------------------------------------------------------

    if year_col:

        year_values = pd.to_numeric(
            lck[year_col],
            errors="coerce"
        )

        lck = lck[
            year_values
            == TARGET_YEAR
        ].copy()

    else:

        lck = lck[
            lck[date_col].dt.year
            == TARGET_YEAR
        ].copy()


    # ========================================================
    # 중요:
    # LCK 원본을 컬럼 하나도 삭제하지 않고 저장
    # ========================================================

    lck.to_csv(
        PROCESSED_DIR
        / "lck_raw_latest.csv",
        index=False,
        encoding="utf-8-sig"
    )


    # --------------------------------------------------------
    # Team 행
    # --------------------------------------------------------

    team_rows = lck[
        lck[position_col]
        .astype(str)
        .str.lower()
        == "team"
    ].copy()


    games = []
    failed = []


    # 경기 후 통계 중 나중에 사용할 가능성이 높은 것들
    # 존재하는 컬럼만 자동 보존
    useful_postgame_columns = [

        "gamelength",

        "kills",
        "deaths",
        "assists",

        "teamkills",
        "teamdeaths",

        "firstblood",

        "firstdragon",
        "dragons",

        "heralds",
        "void_grubs",

        "firstbaron",
        "barons",

        "firsttower",
        "towers",

        "inhibitors",

        "damagetochampions",

        "wardsplaced",
        "wardskilled",
        "visionscore",

        "totalgold",
        "earnedgold",
        "goldspent"
    ]


    for game_id, group in (
        team_rows.groupby(
            game_id_col
        )
    ):

        try:

            blue_rows = group[
                group[side_col]
                .astype(str)
                .str.lower()
                == "blue"
            ]

            red_rows = group[
                group[side_col]
                .astype(str)
                .str.lower()
                == "red"
            ]


            if (
                len(blue_rows) != 1
                or len(red_rows) != 1
            ):

                raise ValueError(
                    "Blue/Red 팀 행 오류"
                )


            blue = blue_rows.iloc[0]
            red = red_rows.iloc[0]


            blue_bans = get_champions(
                blue,
                "ban"
            )

            red_bans = get_champions(
                red,
                "ban"
            )

            blue_picks = get_champions(
                blue,
                "pick"
            )

            red_picks = get_champions(
                red,
                "pick"
            )


            # 완성 경기만 Draft dataset에 사용
            complete_draft = (

                blue_bans
                + red_bans
                + blue_picks
                + red_picks
            )


            if any(
                champion is None
                for champion
                in complete_draft
            ):

                raise ValueError(
                    "밴/픽 누락"
                )


            # ------------------------------------------------
            # First Pick
            # ------------------------------------------------

            blue_first = is_first_pick(
                blue,
                first_pick_col
            )

            red_first = is_first_pick(
                red,
                first_pick_col
            )


            if blue_first and not red_first:

                first_pick_side = "BLUE"

            elif red_first and not blue_first:

                first_pick_side = "RED"

            else:

                raise ValueError(
                    "First Pick 확인 실패"
                )


            # ------------------------------------------------
            # 승패
            # ------------------------------------------------

            blue_result = int(
                float(
                    blue[result_col]
                )
            )

            red_result = int(
                float(
                    red[result_col]
                )
            )


            winner_side = (
                "BLUE"
                if blue_result == 1
                else "RED"
            )


            blue_team = clean_value(
                blue[team_col]
            )

            red_team = clean_value(
                red[team_col]
            )


            winner_team = (
                blue_team
                if winner_side == "BLUE"
                else red_team
            )


            # ------------------------------------------------
            # 기본 데이터
            # ------------------------------------------------

            record = {

                "game_id":
                    str(game_id),

                "date":
                    blue[date_col],

                "league":
                    TARGET_LEAGUE,

                "year":
                    TARGET_YEAR,

                "split":
                    clean_value(
                        blue[split_col]
                    )
                    if split_col
                    else None,

                "playoffs":
                    clean_value(
                        blue[playoffs_col]
                    )
                    if playoffs_col
                    else None,

                "game_number":
                    int(
                        float(
                            blue[
                                game_number_col
                            ]
                        )
                    ),

                "patch":
                    clean_value(
                        blue[patch_col]
                    )
                    if patch_col
                    else None,

                "datacompleteness":
                    clean_value(
                        blue[
                            completeness_col
                        ]
                    )
                    if completeness_col
                    else None,

                "source_url":
                    clean_value(
                        blue[url_col]
                    )
                    if url_col
                    else None,

                "blue_team":
                    blue_team,

                "blue_team_id":
                    clean_value(
                        blue[team_id_col]
                    )
                    if team_id_col
                    else None,

                "red_team":
                    red_team,

                "red_team_id":
                    clean_value(
                        red[team_id_col]
                    )
                    if team_id_col
                    else None,

                # --------------------------------------------
                # 결과
                # --------------------------------------------

                "blue_result":
                    blue_result,

                "red_result":
                    red_result,

                "winner_side":
                    winner_side,

                "winner_team":
                    winner_team,

                # --------------------------------------------
                # 드래프트
                # --------------------------------------------

                "first_pick_side":
                    first_pick_side
            }


            # ------------------------------------------------
            # Ban / Pick
            # ------------------------------------------------

            for i in range(5):

                record[
                    f"blue_ban{i + 1}"
                ] = blue_bans[i]

                record[
                    f"red_ban{i + 1}"
                ] = red_bans[i]

                record[
                    f"blue_pick{i + 1}"
                ] = blue_picks[i]

                record[
                    f"red_pick{i + 1}"
                ] = red_picks[i]


            # ------------------------------------------------
            # 경기 후 통계도 삭제하지 않고 추가
            # ------------------------------------------------

            for column_name in (
                useful_postgame_columns
            ):

                actual_column = (
                    find_column(
                        df,
                        column_name
                    )
                )

                if actual_column:

                    record[
                        f"blue_{column_name}"
                    ] = blue[
                        actual_column
                    ]

                    record[
                        f"red_{column_name}"
                    ] = red[
                        actual_column
                    ]


            games.append(
                record
            )


        except Exception as e:

            failed.append({

                "game_id":
                    game_id,

                "reason":
                    str(e)
            })


    return (
        pd.DataFrame(games),
        pd.DataFrame(failed),
        lck
    )


# ============================================================
# BO3 / BO5 시리즈 묶기
# ============================================================

def assign_series_ids(
    games
):

    games = games.copy()


    def team_key(row, side):

        team_id = row[
            f"{side}_team_id"
        ]

        if team_id:

            return str(team_id)

        return str(
            row[
                f"{side}_team"
            ]
        )


    games["team_pair"] = games.apply(

        lambda row:

            "|".join(
                sorted([
                    team_key(
                        row,
                        "blue"
                    ),

                    team_key(
                        row,
                        "red"
                    )
                ])
            ),

        axis=1
    )


    games = games.sort_values(
        [
            "team_pair",
            "date",
            "game_number"
        ]
    ).reset_index(drop=True)


    series_ids = {}


    for pair, group in games.groupby(
        "team_pair",
        sort=False
    ):

        series_number = 0

        previous_game_number = None
        previous_date = None

        current_series_id = None


        for index, row in (
            group.iterrows()
        ):

            current_date = (
                row["date"]
            )

            game_number = (
                row["game_number"]
            )


            new_series = False


            if previous_game_number is None:

                new_series = True

            elif game_number == 1:

                new_series = True

            elif (
                game_number
                <= previous_game_number
            ):

                new_series = True

            elif (
                previous_date
                is not None
                and pd.notna(current_date)
            ):

                hours = (
                    current_date
                    - previous_date
                ).total_seconds() / 3600

                if (
                    hours
                    > MAX_SERIES_GAP_HOURS
                ):

                    new_series = True


            if new_series:

                series_number += 1

                date_text = (
                    current_date.strftime(
                        "%Y%m%d"
                    )
                    if pd.notna(
                        current_date
                    )
                    else "unknown"
                )

                team_names = sorted([

                    safe_name(
                        row["blue_team"]
                    ),

                    safe_name(
                        row["red_team"]
                    )
                ])


                current_series_id = (

                    f"{TARGET_LEAGUE}_"
                    f"{date_text}_"
                    f"{team_names[0]}_vs_"
                    f"{team_names[1]}_"
                    f"S{series_number}"
                )


            series_ids[index] = (
                current_series_id
            )

            previous_game_number = (
                game_number
            )

            previous_date = (
                current_date
            )


    games["series_id"] = (
        games.index.map(
            series_ids
        )
    )

    return games


# ============================================================
# Fearless 정보
# ============================================================

def add_fearless_info(
    games
):

    games = games.copy()

    games[
        "fearless_unavailable_before_game"
    ] = None

    games[
        "fearless_unavailable_count"
    ] = 0

    games[
        "fearless_repeat_detected"
    ] = False


    for series_id, group in (
        games.groupby(
            "series_id"
        )
    ):

        group = group.sort_values(
            "game_number"
        )

        previously_picked = []


        for index, game in (
            group.iterrows()
        ):

            if USE_FEARLESS:

                unavailable = list(
                    previously_picked
                )

            else:

                unavailable = []


            games.at[
                index,
                "fearless_unavailable_before_game"
            ] = json.dumps(
                unavailable,
                ensure_ascii=False
            )


            games.at[
                index,
                "fearless_unavailable_count"
            ] = len(unavailable)


            current_picks = []

            for i in range(1, 6):

                current_picks.append(
                    game[
                        f"blue_pick{i}"
                    ]
                )

                current_picks.append(
                    game[
                        f"red_pick{i}"
                    ]
                )


            repeats = [

                champion

                for champion
                in current_picks

                if champion
                in previously_picked
            ]


            if (
                USE_FEARLESS
                and repeats
            ):

                games.at[
                    index,
                    "fearless_repeat_detected"
                ] = True


            for champion in (
                current_picks
            ):

                if (
                    champion
                    not in previously_picked
                ):

                    previously_picked.append(
                        champion
                    )


    return games


# ============================================================
# 경기 시작 전 팀 승률 계산
#
# 현재 경기 결과는 포함하지 않는다.
# ============================================================

def add_team_history(
    games
):

    games = games.sort_values(
        [
            "date",
            "series_id",
            "game_number"
        ]
    ).reset_index(drop=True)


    overall = {}
    side_stats = {}
    patch_stats = {}
    h2h_stats = {}


    def team_key(
        row,
        prefix
    ):

        team_id = row[
            f"{prefix}_team_id"
        ]

        if team_id:

            return str(team_id)

        return str(
            row[
                f"{prefix}_team"
            ]
        )


    for index, game in (
        games.iterrows()
    ):

        blue = team_key(
            game,
            "blue"
        )

        red = team_key(
            game,
            "red"
        )

        patch = game["patch"]


        overall.setdefault(
            blue,
            [0, 0]
        )

        overall.setdefault(
            red,
            [0, 0]
        )


        side_stats.setdefault(
            (blue, "BLUE"),
            [0, 0]
        )

        side_stats.setdefault(
            (red, "RED"),
            [0, 0]
        )


        patch_stats.setdefault(
            (blue, patch),
            [0, 0]
        )

        patch_stats.setdefault(
            (red, patch),
            [0, 0]
        )


        pair = tuple(
            sorted([
                blue,
                red
            ])
        )

        h2h_stats.setdefault(
            pair,
            {}
        )

        h2h_stats[pair].setdefault(
            blue,
            [0, 0]
        )

        h2h_stats[pair].setdefault(
            red,
            [0, 0]
        )


        # ----------------------------------------------------
        # BLUE 과거 승률
        # ----------------------------------------------------

        games.at[
            index,
            "blue_games_before"
        ] = overall[blue][0]

        games.at[
            index,
            "blue_wins_before"
        ] = overall[blue][1]

        games.at[
            index,
            "blue_win_rate_before"
        ] = win_rate(
            overall[blue][1],
            overall[blue][0]
        )


        games.at[
            index,
            "blue_side_games_before"
        ] = side_stats[
            (blue, "BLUE")
        ][0]

        games.at[
            index,
            "blue_side_win_rate_before"
        ] = win_rate(
            side_stats[
                (blue, "BLUE")
            ][1],

            side_stats[
                (blue, "BLUE")
            ][0]
        )


        games.at[
            index,
            "blue_patch_games_before"
        ] = patch_stats[
            (blue, patch)
        ][0]

        games.at[
            index,
            "blue_patch_win_rate_before"
        ] = win_rate(
            patch_stats[
                (blue, patch)
            ][1],

            patch_stats[
                (blue, patch)
            ][0]
        )


        # ----------------------------------------------------
        # RED 과거 승률
        # ----------------------------------------------------

        games.at[
            index,
            "red_games_before"
        ] = overall[red][0]

        games.at[
            index,
            "red_wins_before"
        ] = overall[red][1]

        games.at[
            index,
            "red_win_rate_before"
        ] = win_rate(
            overall[red][1],
            overall[red][0]
        )


        games.at[
            index,
            "red_side_games_before"
        ] = side_stats[
            (red, "RED")
        ][0]

        games.at[
            index,
            "red_side_win_rate_before"
        ] = win_rate(
            side_stats[
                (red, "RED")
            ][1],

            side_stats[
                (red, "RED")
            ][0]
        )


        games.at[
            index,
            "red_patch_games_before"
        ] = patch_stats[
            (red, patch)
        ][0]

        games.at[
            index,
            "red_patch_win_rate_before"
        ] = win_rate(
            patch_stats[
                (red, patch)
            ][1],

            patch_stats[
                (red, patch)
            ][0]
        )


        # ----------------------------------------------------
        # 상대전적
        # ----------------------------------------------------

        blue_h2h = (
            h2h_stats[pair][blue]
        )

        red_h2h = (
            h2h_stats[pair][red]
        )


        games.at[
            index,
            "blue_h2h_games_before"
        ] = blue_h2h[0]

        games.at[
            index,
            "blue_h2h_win_rate_before"
        ] = win_rate(
            blue_h2h[1],
            blue_h2h[0]
        )


        games.at[
            index,
            "red_h2h_games_before"
        ] = red_h2h[0]

        games.at[
            index,
            "red_h2h_win_rate_before"
        ] = win_rate(
            red_h2h[1],
            red_h2h[0]
        )


        # ====================================================
        # 여기서 현재 경기 결과 반영
        #
        # 즉 위의 *_before에는 현재 결과가 절대 포함되지 않음
        # ====================================================

        blue_win = (
            game["blue_result"]
            == 1
        )

        red_win = (
            game["red_result"]
            == 1
        )


        overall[blue][0] += 1
        overall[red][0] += 1

        overall[blue][1] += int(
            blue_win
        )

        overall[red][1] += int(
            red_win
        )


        side_stats[
            (blue, "BLUE")
        ][0] += 1

        side_stats[
            (red, "RED")
        ][0] += 1


        side_stats[
            (blue, "BLUE")
        ][1] += int(
            blue_win
        )

        side_stats[
            (red, "RED")
        ][1] += int(
            red_win
        )


        patch_stats[
            (blue, patch)
        ][0] += 1

        patch_stats[
            (red, patch)
        ][0] += 1


        patch_stats[
            (blue, patch)
        ][1] += int(
            blue_win
        )

        patch_stats[
            (red, patch)
        ][1] += int(
            red_win
        )


        h2h_stats[
            pair
        ][blue][0] += 1

        h2h_stats[
            pair
        ][red][0] += 1


        h2h_stats[
            pair
        ][blue][1] += int(
            blue_win
        )

        h2h_stats[
            pair
        ][red][1] += int(
            red_win
        )


    return games


# ============================================================
# 챔피언의 경기 전 승률 데이터
# ============================================================

def build_champion_history(
    games
):

    stats = {}
    patch_stats = {}
    team_champion_stats = {}

    records = []


    games = games.sort_values(
        [
            "date",
            "series_id",
            "game_number"
        ]
    )


    for _, game in games.iterrows():

        current = []


        for side in [
            "BLUE",
            "RED"
        ]:

            prefix = side.lower()

            team = game[
                f"{prefix}_team"
            ]

            team_id = game[
                f"{prefix}_team_id"
            ]

            team_key = (
                str(team_id)
                if team_id
                else str(team)
            )


            won = int(
                game["winner_side"]
                == side
            )


            for pick_index in range(
                1,
                6
            ):

                champion = game[
                    f"{prefix}_pick"
                    f"{pick_index}"
                ]


                stats.setdefault(
                    champion,
                    [0, 0]
                )


                patch_key = (
                    champion,
                    game["patch"]
                )

                patch_stats.setdefault(
                    patch_key,
                    [0, 0]
                )


                tc_key = (
                    team_key,
                    champion
                )

                team_champion_stats.setdefault(
                    tc_key,
                    [0, 0]
                )


                # --------------------------------------------
                # 현재 경기 전 통계
                # --------------------------------------------

                records.append({

                    "game_id":
                        game["game_id"],

                    "series_id":
                        game["series_id"],

                    "game_number":
                        game["game_number"],

                    "date":
                        game["date"],

                    "patch":
                        game["patch"],

                    "side":
                        side,

                    "team":
                        team,

                    "champion":
                        champion,

                    "pick_index":
                        pick_index,

                    "champion_games_before":
                        stats[
                            champion
                        ][0],

                    "champion_wins_before":
                        stats[
                            champion
                        ][1],

                    "champion_win_rate_before":
                        win_rate(
                            stats[
                                champion
                            ][1],

                            stats[
                                champion
                            ][0]
                        ),

                    "champion_patch_games_before":
                        patch_stats[
                            patch_key
                        ][0],

                    "champion_patch_win_rate_before":
                        win_rate(
                            patch_stats[
                                patch_key
                            ][1],

                            patch_stats[
                                patch_key
                            ][0]
                        ),

                    "team_champion_games_before":
                        team_champion_stats[
                            tc_key
                        ][0],

                    "team_champion_win_rate_before":
                        win_rate(
                            team_champion_stats[
                                tc_key
                            ][1],

                            team_champion_stats[
                                tc_key
                            ][0]
                        ),

                    # 결과 라벨
                    # 모델 입력으로 직접 사용하면 안 됨
                    "picked_side_won":
                        won
                })


                current.append(
                    (
                        champion,
                        patch_key,
                        tc_key,
                        won
                    )
                )


        # ====================================================
        # 경기 전 통계 기록이 끝난 뒤 현재 경기 반영
        # ====================================================

        for (
            champion,
            patch_key,
            tc_key,
            won
        ) in current:

            stats[
                champion
            ][0] += 1

            stats[
                champion
            ][1] += won


            patch_stats[
                patch_key
            ][0] += 1

            patch_stats[
                patch_key
            ][1] += won


            team_champion_stats[
                tc_key
            ][0] += 1

            team_champion_stats[
                tc_key
            ][1] += won


    return pd.DataFrame(
        records
    )


# ============================================================
# 실제 밴픽 Action 데이터
# ============================================================

def build_actions(
    games
):

    actions_all = []


    for _, game in (
        games.iterrows()
    ):

        blue_bans = [

            game[
                f"blue_ban{i}"
            ]

            for i in range(
                1,
                6
            )
        ]


        red_bans = [

            game[
                f"red_ban{i}"
            ]

            for i in range(
                1,
                6
            )
        ]


        blue_picks = [

            game[
                f"blue_pick{i}"
            ]

            for i in range(
                1,
                6
            )
        ]


        red_picks = [

            game[
                f"red_pick{i}"
            ]

            for i in range(
                1,
                6
            )
        ]


        actions = (
            reconstruct_draft_actions(
                blue_bans,
                red_bans,
                blue_picks,
                red_picks,
                game[
                    "first_pick_side"
                ]
            )
        )


        for action in actions:

            acting_side = (
                action["side"]
            )

            acting_prefix = (
                acting_side.lower()
            )


            action.update({

                "game_id":
                    game["game_id"],

                "series_id":
                    game["series_id"],

                "game_number":
                    game["game_number"],

                "date":
                    game["date"],

                "patch":
                    game["patch"],

                "blue_team":
                    game["blue_team"],

                "red_team":
                    game["red_team"],

                "first_pick_side":
                    game[
                        "first_pick_side"
                    ],

                "fearless_unavailable":
                    game[
                        "fearless_unavailable_before_game"
                    ],

                # --------------------------------------------
                # 예측 당시 사용 가능한 과거 승률
                # --------------------------------------------

                "blue_win_rate_before":
                    game[
                        "blue_win_rate_before"
                    ],

                "red_win_rate_before":
                    game[
                        "red_win_rate_before"
                    ],

                "blue_side_win_rate_before":
                    game[
                        "blue_side_win_rate_before"
                    ],

                "red_side_win_rate_before":
                    game[
                        "red_side_win_rate_before"
                    ],

                "blue_patch_win_rate_before":
                    game[
                        "blue_patch_win_rate_before"
                    ],

                "red_patch_win_rate_before":
                    game[
                        "red_patch_win_rate_before"
                    ],

                "blue_h2h_win_rate_before":
                    game[
                        "blue_h2h_win_rate_before"
                    ],

                "red_h2h_win_rate_before":
                    game[
                        "red_h2h_win_rate_before"
                    ],

                # --------------------------------------------
                # 경기 결과
                # 이것들은 LABEL
                # --------------------------------------------

                "winner_side":
                    game[
                        "winner_side"
                    ],

                "winner_team":
                    game[
                        "winner_team"
                    ],

                "acting_side_won":
                    int(
                        acting_side
                        == game[
                            "winner_side"
                        ]
                    )
            })


            actions_all.append(
                action
            )


    return pd.DataFrame(
        actions_all
    )


# ============================================================
# ML용
# 현재 Draft → 다음 Pick/Ban
# ============================================================

def build_training_samples(
    actions
):

    samples = []


    for game_id, group in (
        actions.groupby(
            "game_id",
            sort=False
        )
    ):

        group = group.sort_values(
            "order"
        )

        state = []


        for _, action in (
            group.iterrows()
        ):

            samples.append({

                "game_id":
                    game_id,

                "series_id":
                    action[
                        "series_id"
                    ],

                "game_number":
                    action[
                        "game_number"
                    ],

                "date":
                    action[
                        "date"
                    ],

                "patch":
                    action[
                        "patch"
                    ],

                "blue_team":
                    action[
                        "blue_team"
                    ],

                "red_team":
                    action[
                        "red_team"
                    ],

                "first_pick_side":
                    action[
                        "first_pick_side"
                    ],

                # --------------------------------------------
                # 현재 Draft 진행 상황
                # --------------------------------------------

                "step":
                    action[
                        "order"
                    ],

                "draft_state":
                    json.dumps(
                        state,
                        ensure_ascii=False
                    ),

                "fearless_unavailable":
                    action[
                        "fearless_unavailable"
                    ],

                # --------------------------------------------
                # 과거 승률 Feature
                # --------------------------------------------

                "blue_win_rate_before":
                    action[
                        "blue_win_rate_before"
                    ],

                "red_win_rate_before":
                    action[
                        "red_win_rate_before"
                    ],

                "blue_side_win_rate_before":
                    action[
                        "blue_side_win_rate_before"
                    ],

                "red_side_win_rate_before":
                    action[
                        "red_side_win_rate_before"
                    ],

                "blue_patch_win_rate_before":
                    action[
                        "blue_patch_win_rate_before"
                    ],

                "red_patch_win_rate_before":
                    action[
                        "red_patch_win_rate_before"
                    ],

                "blue_h2h_win_rate_before":
                    action[
                        "blue_h2h_win_rate_before"
                    ],

                "red_h2h_win_rate_before":
                    action[
                        "red_h2h_win_rate_before"
                    ],

                # --------------------------------------------
                # 다음 행동 예측 정답
                # --------------------------------------------

                "next_side":
                    action[
                        "side"
                    ],

                "next_action":
                    action[
                        "action"
                    ],

                "target_champion":
                    action[
                        "champion"
                    ],

                # --------------------------------------------
                # 추천/승률 모델 평가용 Label
                #
                # Feature로 바로 넣으면 안 됨
                # --------------------------------------------

                "winner_side":
                    action[
                        "winner_side"
                    ],

                "winner_team":
                    action[
                        "winner_team"
                    ],

                "next_side_eventually_won":
                    action[
                        "acting_side_won"
                    ]
            })


            # 현재 action을 상태에 추가
            state.append({

                "order":
                    int(
                        action[
                            "order"
                        ]
                    ),

                "phase":
                    action[
                        "phase"
                    ],

                "side":
                    action[
                        "side"
                    ],

                "action":
                    action[
                        "action"
                    ],

                "champion":
                    action[
                        "champion"
                    ]
            })


    return pd.DataFrame(
        samples
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "======================================"
    )

    print(
        "Oracle's Elixir → LCK Dataset"
    )

    print(
        "======================================"
    )


    # --------------------------------------------------------
    # 파일 확인
    # --------------------------------------------------------

    if not RAW_FILE.exists():

        raise FileNotFoundError(

            "\nOracle 파일이 없습니다.\n\n"

            "Oracle's Elixir에서 받은 CSV를\n"

            f"{RAW_FILE}\n"

            "위치에 넣어주세요."
        )


    # --------------------------------------------------------
    # 원본 변경 여부
    # --------------------------------------------------------

    file_hash = (
        calculate_sha256(
            RAW_FILE
        )
    )


    print(
        "Source SHA256:",
        file_hash[:16]
    )


    if (
        SKIP_IF_SOURCE_UNCHANGED
        and source_is_unchanged(
            file_hash
        )
    ):

        print()
        print(
            "Oracle 원본이 이전 실행과 동일합니다."
        )

        print(
            "새 데이터가 없으므로 종료합니다."
        )

        return


    # --------------------------------------------------------
    # 원본 백업
    # --------------------------------------------------------

    archive_raw_file(
        RAW_FILE,
        file_hash
    )


    # --------------------------------------------------------
    # Oracle 읽기
    # --------------------------------------------------------

    print()
    print(
        "Oracle CSV 읽는 중..."
    )


    df = pd.read_csv(
        RAW_FILE,
        low_memory=False
    )


    print(
        "Oracle 전체 행:",
        len(df)
    )


    # --------------------------------------------------------
    # Game Dataset
    # --------------------------------------------------------

    games, failed, raw_lck = (
        build_games(
            df
        )
    )


    print(
        "완성 LCK 경기:",
        len(games)
    )


    # --------------------------------------------------------
    # Series
    # --------------------------------------------------------

    games = (
        assign_series_ids(
            games
        )
    )


    # --------------------------------------------------------
    # Fearless
    # --------------------------------------------------------

    games = (
        add_fearless_info(
            games
        )
    )


    # --------------------------------------------------------
    # 팀 과거 승률
    # --------------------------------------------------------

    games = (
        add_team_history(
            games
        )
    )


    # --------------------------------------------------------
    # Champion History
    # --------------------------------------------------------

    champion_history = (
        build_champion_history(
            games
        )
    )


    # --------------------------------------------------------
    # Draft Actions
    # --------------------------------------------------------

    actions = (
        build_actions(
            games
        )
    )


    # --------------------------------------------------------
    # Training Sample
    # --------------------------------------------------------

    training = (
        build_training_samples(
            actions
        )
    )


    # ========================================================
    # 저장
    # ========================================================

    today = datetime.now().strftime(
        "%Y%m%d"
    )


    # 최신
    games.to_csv(
        PROCESSED_DIR
        / "lck_games_latest.csv",
        index=False,
        encoding="utf-8-sig"
    )


    actions.to_csv(
        PROCESSED_DIR
        / "lck_draft_actions_latest.csv",
        index=False,
        encoding="utf-8-sig"
    )


    training.to_csv(
        PROCESSED_DIR
        / "lck_training_samples_latest.csv",
        index=False,
        encoding="utf-8-sig"
    )


    champion_history.to_csv(
        PROCESSED_DIR
        / "lck_champion_history_latest.csv",
        index=False,
        encoding="utf-8-sig"
    )


    # --------------------------------------------------------
    # 날짜별 Snapshot
    # --------------------------------------------------------

    games.to_csv(
        PROCESSED_DIR
        / f"lck_games_{today}.csv",
        index=False,
        encoding="utf-8-sig"
    )


    actions.to_csv(
        PROCESSED_DIR
        / f"lck_draft_actions_{today}.csv",
        index=False,
        encoding="utf-8-sig"
    )


    # --------------------------------------------------------
    # 실패 경기
    # --------------------------------------------------------

    if not failed.empty:

        failed.to_csv(
            PROCESSED_DIR
            / "failed_games.csv",
            index=False,
            encoding="utf-8-sig"
        )


    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = {

        "processed_at":
            datetime.now().isoformat(),

        "source":
            "Oracle's Elixir",

        "source_page":
            SOURCE_PAGE,

        "source_file":
            str(RAW_FILE),

        "source_sha256":
            file_hash,

        "year":
            TARGET_YEAR,

        "league":
            TARGET_LEAGUE,

        "fearless_enabled":
            USE_FEARLESS,

        "raw_lck_rows":
            len(raw_lck),

        "games":
            len(games),

        "draft_actions":
            len(actions),

        "training_samples":
            len(training),

        "champion_history_rows":
            len(
                champion_history
            ),

        "failed_games":
            len(failed)
    }


    with open(
        METADATA_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2
        )


    # ========================================================
    # 완료
    # ========================================================

    print()
    print(
        "======================================"
    )

    print(
        "완료"
    )

    print(
        "======================================"
    )

    print(
        "LCK 경기:",
        len(games)
    )

    print(
        "Draft Actions:",
        len(actions)
    )

    print(
        "Training Samples:",
        len(training)
    )

    print(
        "Champion History:",
        len(
            champion_history
        )
    )

    print(
        "실패 경기:",
        len(failed)
    )

    print()

    print(
        "생성 파일:"
    )

    print(
        "data/processed/lck_raw_latest.csv"
    )

    print(
        "data/processed/lck_games_latest.csv"
    )

    print(
        "data/processed/lck_draft_actions_latest.csv"
    )

    print(
        "data/processed/lck_training_samples_latest.csv"
    )

    print(
        "data/processed/lck_champion_history_latest.csv"
    )


if __name__ == "__main__":

    main()