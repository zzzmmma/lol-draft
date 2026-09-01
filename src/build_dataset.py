from pathlib import Path
from datetime import datetime
import hashlib
import json
import re
import shutil

import gdown
import pandas as pd


# ============================================================
# 0. 기본 설정
# ============================================================

TARGET_YEAR = 2026
TARGET_LEAGUE = "LCK"

# 실행할 때마다 Oracle 최신 파일 확인
AUTO_DOWNLOAD = True

# 개발 중에는 False 권장
# 나중에 완성 후 자동 운영할 때 True
SKIP_IF_SOURCE_UNCHANGED = False

# 2026 LCK Fearless Draft 사용
USE_FEARLESS = True

# 같은 두 팀의 경기 간격이 너무 멀면 다른 시리즈로 판단
MAX_SERIES_GAP_HOURS = 12


# ============================================================
# Oracle's Elixir 2026 Google Drive
# ============================================================

ORACLE_FILE_ID = (
    "1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm"
)

ORACLE_DIRECT_URL = (
    f"https://drive.google.com/uc?id={ORACLE_FILE_ID}"
)


# ============================================================
# 1. 프로젝트 경로 설정
#
# build_dataset.py가
#
# lol-draft/src/build_dataset.py
#
# 에 있어도 정상적으로 프로젝트 루트를 찾음
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

if SCRIPT_DIR.name.lower() == "src":
    PROJECT_ROOT = SCRIPT_DIR.parent
else:
    PROJECT_ROOT = SCRIPT_DIR


DATA_DIR = PROJECT_ROOT / "data"

RAW_DIR = DATA_DIR / "raw"

RAW_ARCHIVE_DIR = (
    DATA_DIR / "raw_archive"
)

PROCESSED_DIR = (
    DATA_DIR / "processed"
)


RAW_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RAW_ARCHIVE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

PROCESSED_DIR.mkdir(
    parents=True,
    exist_ok=True
)


RAW_FILE = (
    RAW_DIR
    / (
        f"{TARGET_YEAR}_"
        "LoL_esports_match_data_"
        "from_OraclesElixir.csv"
    )
)


METADATA_FILE = (
    PROCESSED_DIR
    / "dataset_metadata.json"
)


# ============================================================
# 2. 기본 유틸 함수
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

        str(column).lower():
            column

        for column in df.columns
    }

    for name in names:

        if name in df.columns:
            return name

        lower_name = (
            name.lower()
        )

        if lower_name in lower_map:

            return lower_map[
                lower_name
            ]

    return None


def safe_win_rate(
    wins,
    games
):

    if games == 0:
        return None

    return wins / games


def recent_win_rate(
    history,
    n
):

    recent = history[-n:]

    if not recent:
        return None

    return (
        sum(recent)
        / len(recent)
    )


def safe_name(text):

    text = str(text)

    text = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        text
    )

    return text.strip("_")


# ============================================================
# result 값 처리
# ============================================================

def parse_result(value):

    if pd.isna(value):

        raise ValueError(
            "result 값이 비어 있음"
        )

    text = (
        str(value)
        .strip()
        .lower()
    )


    if text in {
        "1",
        "1.0",
        "true",
        "win",
        "w"
    }:

        return 1


    if text in {
        "0",
        "0.0",
        "false",
        "loss",
        "lose",
        "l"
    }:

        return 0


    try:

        numeric = int(
            float(text)
        )

        if numeric in {
            0,
            1
        }:

            return numeric

    except ValueError:

        pass


    raise ValueError(
        f"알 수 없는 result 값: {value}"
    )


# ============================================================
# 3. CSV 안전 저장
#
# Windows에서 Excel이 CSV를 열고 있으면
# PermissionError가 발생한다.
#
# 그 경우 프로그램을 종료하지 않고
# 새로운 timestamp 파일로 저장한다.
# ============================================================

def safe_write_csv(
    df,
    path
):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    try:

        df.to_csv(
            path,
            index=False,
            encoding="utf-8-sig"
        )

        return path


    except PermissionError:

        timestamp = (
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )


        fallback = (

            path.parent

            / (
                f"{path.stem}_"
                f"{timestamp}_NEW"
                f"{path.suffix}"
            )
        )


        df.to_csv(
            fallback,
            index=False,
            encoding="utf-8-sig"
        )


        print()
        print(
            "[주의]"
        )

        print(
            f"{path.name} 파일이 "
            "Excel 등에 열려 있어서 "
            "덮어쓰지 못했습니다."
        )

        print(
            "대신 다음 파일에 저장했습니다:"
        )

        print(
            fallback
        )


        return fallback


# ============================================================
# 4. SHA256
# ============================================================

def calculate_sha256(path):

    sha = hashlib.sha256()


    with open(
        path,
        "rb"
    ) as file:

        while True:

            chunk = file.read(
                1024 * 1024
            )

            if not chunk:
                break

            sha.update(
                chunk
            )


    return sha.hexdigest()


# ============================================================
# 이전 실행과 Oracle 파일이 같은지 확인
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

            metadata = json.load(
                file
            )


        return (

            metadata.get(
                "source_sha256"
            )

            == current_hash
        )


    except Exception:

        return False


# ============================================================
# 5. 이전 Oracle 원본 백업
# ============================================================

def archive_raw_file(path):

    if not path.exists():
        return None


    file_hash = (
        calculate_sha256(
            path
        )
    )


    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )


    archive_path = (

        RAW_ARCHIVE_DIR

        / (
            f"{TARGET_YEAR}_OE_"
            f"{timestamp}_"
            f"{file_hash[:8]}.csv"
        )
    )


    shutil.copy2(
        path,
        archive_path
    )


    print(
        "이전 Oracle 원본 백업:",
        archive_path
    )


    return archive_path


# ============================================================
# 6. Oracle 최신 CSV 자동 다운로드
# ============================================================

def download_latest_oracle_data():

    print()
    print("========================================")
    print("Oracle 최신 데이터 다운로드")
    print("========================================")

    temp_file = (
        RAW_DIR
        / "oracle_download_temp.csv"
    )

    if temp_file.exists():
        temp_file.unlink()

    print(
        "2026 Oracle 파일 다운로드 중..."
    )

    try:

        downloaded_path = gdown.download(
            id=ORACLE_FILE_ID,
            output=str(temp_file),
            quiet=False
        )

    except Exception as e:

        error_message = str(e)

        # ================================================
        # Google Drive 다운로드 쿼터 초과
        # ================================================

        quota_keywords = [
            "Too many users",
            "download quota",
            "Quota exceeded",
            "Failed to retrieve file url"
        ]

        if any(
            keyword.lower()
            in error_message.lower()
            for keyword
            in quota_keywords
        ):

            print()
            print(
                "[Oracle 다운로드 제한]"
            )

            print(
                "Google Drive 다운로드 쿼터가 "
                "초과되었습니다."
            )

            print(
                "기존 Oracle 원본이 있으면 "
                "그 파일을 사용합니다."
            )

            temp_file.unlink(
                missing_ok=True
            )

            return False

        raise


    if (
        downloaded_path is None
        or not temp_file.exists()
    ):

        print()
        print(
            "Oracle 다운로드 실패"
        )

        return False


    # ================================================
    # CSV 확인
    # ================================================

    try:

        test_df = pd.read_csv(
            temp_file,
            nrows=5
        )

    except Exception as e:

        temp_file.unlink(
            missing_ok=True
        )

        print(
            "다운로드한 파일이 "
            "정상 CSV가 아닙니다."
        )

        print(e)

        return False


    required_columns = {
        "gameid",
        "league",
        "side"
    }


    if not required_columns.issubset(
        set(test_df.columns)
    ):

        temp_file.unlink(
            missing_ok=True
        )

        print(
            "Oracle CSV 필수 컬럼이 없습니다."
        )

        return False


    # ================================================
    # Hash 비교
    # ================================================

    new_hash = calculate_sha256(
        temp_file
    )


    print(
        "다운로드 파일 SHA256:",
        new_hash[:16]
    )


    if RAW_FILE.exists():

        old_hash = calculate_sha256(
            RAW_FILE
        )


        print(
            "기존 파일 SHA256:",
            old_hash[:16]
        )


        # Oracle 파일 변경 없음
        if new_hash == old_hash:

            print(
                "Oracle 원본 데이터 변경 없음"
            )

            temp_file.unlink()

            return False


        # 기존 파일 백업
        archive_raw_file(
            RAW_FILE
        )


    # ================================================
    # 최신 파일로 교체
    # ================================================

    shutil.move(
        str(temp_file),
        str(RAW_FILE)
    )


    print()
    print(
        "Oracle 최신 데이터 다운로드 성공"
    )

    print(
        "새 원본으로 교체했습니다."
    )


    return True


# ============================================================
# 7. 챔피언 Ban / Pick 데이터
# ============================================================

def get_champions(
    row,
    prefix
):

    champions = []


    for number in range(
        1,
        6
    ):

        column = (
            f"{prefix}{number}"
        )


        if column not in row.index:

            champions.append(
                None
            )

            continue


        champions.append(

            clean_value(
                row[column]
            )
        )


    return champions


# ============================================================
# First Pick
# ============================================================

def is_first_pick(
    row,
    column
):

    if column is None:
        return False


    value = row[
        column
    ]


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
# 8. 실제 20단계 밴픽 순서 복원
#
# 우리가 영상으로 확인했던 순서
#
# First Pick BLUE
#
# BAN1:
# B R B R B R
#
# PICK1:
# B R R B B R
#
# BAN2:
# R B R B
#
# PICK2:
# R B B R
#
# First Pick RED면 반대
# ============================================================

def reconstruct_draft_actions(

    blue_bans,
    red_bans,

    blue_picks,
    red_picks,

    first_pick_side
):


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


    def add_action(

        phase,
        side,
        action,
        champion
    ):

        actions.append({

            "phase":
                phase,

            "side":
                side,

            "action":
                action,

            "champion":
                champion
        })


    # ========================================================
    # 1차 밴
    # ========================================================

    for i in range(3):

        add_action(
            "BAN_PHASE_1",
            first_side,
            "BAN",
            first_bans[i]
        )

        add_action(
            "BAN_PHASE_1",
            second_side,
            "BAN",
            second_bans[i]
        )


    # ========================================================
    # 1차 픽
    # ========================================================

    add_action(
        "PICK_PHASE_1",
        first_side,
        "PICK",
        first_picks[0]
    )


    add_action(
        "PICK_PHASE_1",
        second_side,
        "PICK",
        second_picks[0]
    )


    add_action(
        "PICK_PHASE_1",
        second_side,
        "PICK",
        second_picks[1]
    )


    add_action(
        "PICK_PHASE_1",
        first_side,
        "PICK",
        first_picks[1]
    )


    add_action(
        "PICK_PHASE_1",
        first_side,
        "PICK",
        first_picks[2]
    )


    add_action(
        "PICK_PHASE_1",
        second_side,
        "PICK",
        second_picks[2]
    )


    # ========================================================
    # 2차 밴
    # ========================================================

    add_action(
        "BAN_PHASE_2",
        second_side,
        "BAN",
        second_bans[3]
    )


    add_action(
        "BAN_PHASE_2",
        first_side,
        "BAN",
        first_bans[3]
    )


    add_action(
        "BAN_PHASE_2",
        second_side,
        "BAN",
        second_bans[4]
    )


    add_action(
        "BAN_PHASE_2",
        first_side,
        "BAN",
        first_bans[4]
    )


    # ========================================================
    # 2차 픽
    # ========================================================

    add_action(
        "PICK_PHASE_2",
        second_side,
        "PICK",
        second_picks[3]
    )


    add_action(
        "PICK_PHASE_2",
        first_side,
        "PICK",
        first_picks[3]
    )


    add_action(
        "PICK_PHASE_2",
        first_side,
        "PICK",
        first_picks[4]
    )


    add_action(
        "PICK_PHASE_2",
        second_side,
        "PICK",
        second_picks[4]
    )


    # ========================================================
    # 순서 번호
    # ========================================================

    for order, action in enumerate(
        actions,
        start=1
    ):

        action[
            "order"
        ] = order


    return actions


# ============================================================
# 9. Oracle → LCK 경기 단위 데이터
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


    gameid_col = find_column(
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
        "teamname",
        "team"
    )


    teamid_col = find_column(
        df,
        "teamid"
    )


    result_col = find_column(
        df,
        "result"
    )


    firstpick_col = find_column(
        df,
        "firstpick",
        "firstPick"
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


    tournament_col = find_column(
        df,
        "tournament",
        "tournamentname"
    )


    bestof_col = find_column(
        df,
        "bestof",
        "best_of"
    )


    # ========================================================
    # 필수 컬럼 확인
    # ========================================================

    required = {

        "league":
            league_col,

        "gameid":
            gameid_col,

        "date":
            date_col,

        "game":
            game_number_col,

        "position":
            position_col,

        "side":
            side_col,

        "teamname":
            team_col,

        "result":
            result_col,

        "firstpick":
            firstpick_col
    }


    missing = [

        name

        for name, column
        in required.items()

        if column is None
    ]


    if missing:

        raise ValueError(

            "Oracle CSV 필수 컬럼 없음: "

            + str(
                missing
            )
        )


    # ========================================================
    # Ban / Pick 컬럼 확인
    # ========================================================

    for prefix in (
        "ban",
        "pick"
    ):

        for i in range(
            1,
            6
        ):

            column = (
                f"{prefix}{i}"
            )


            if column not in df.columns:

                raise ValueError(
                    f"Oracle CSV 컬럼 없음: "
                    f"{column}"
                )


    # ========================================================
    # 날짜 처리
    # ========================================================

    df = df.copy()


    df[
        date_col
    ] = pd.to_datetime(

        df[
            date_col
        ],

        errors="coerce",

        utc=True
    )


    # ========================================================
    # LCK 필터
    # ========================================================

    lck = df[

        df[
            league_col
        ]
        .astype(str)
        .str.upper()

        == TARGET_LEAGUE

    ].copy()


    # ========================================================
    # 2026 필터
    # ========================================================

    if year_col:

        years = pd.to_numeric(

            lck[
                year_col
            ],

            errors="coerce"
        )


        lck = lck[

            years
            == TARGET_YEAR

        ].copy()


    else:

        lck = lck[

            lck[
                date_col
            ].dt.year

            == TARGET_YEAR

        ].copy()


    # ========================================================
    # Team 행만
    # ========================================================

    team_rows = lck[

        lck[
            position_col
        ]
        .astype(str)
        .str.lower()

        == "team"

    ].copy()


    games = []

    failed = []


    # ========================================================
    # 나중에 승리 예측에 사용할 수도 있는
    # 경기 후 통계
    #
    # 실제 Oracle에 있는 컬럼만 자동 저장
    # ========================================================

    postgame_candidates = [

        "gamelength",

        "kills",
        "deaths",
        "assists",

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
        "goldspent",

        "golddiffat10",
        "golddiffat15",
        "golddiffat20",

        "xpdiffat10",
        "xpdiffat15",
        "xpdiffat20",

        "csdiffat10",
        "csdiffat15",
        "csdiffat20"
    ]


    actual_postgame_columns = {}


    for candidate in (
        postgame_candidates
    ):

        found = find_column(
            df,
            candidate
        )

        if found:

            actual_postgame_columns[
                candidate
            ] = found


    # ========================================================
    # gameid별 처리
    # ========================================================

    for game_id, group in (

        team_rows.groupby(
            gameid_col
        )

    ):

        try:

            blue_rows = group[

                group[
                    side_col
                ]
                .astype(str)
                .str.lower()

                == "blue"

            ]


            red_rows = group[

                group[
                    side_col
                ]
                .astype(str)
                .str.lower()

                == "red"

            ]


            if (

                len(blue_rows) != 1

                or len(red_rows) != 1

            ):

                raise ValueError(
                    "Blue/Red team row가 "
                    "각각 1개가 아님"
                )


            blue = (
                blue_rows.iloc[0]
            )

            red = (
                red_rows.iloc[0]
            )


            # =================================================
            # Ban / Pick
            # =================================================

            blue_bans = (
                get_champions(
                    blue,
                    "ban"
                )
            )


            red_bans = (
                get_champions(
                    red,
                    "ban"
                )
            )


            blue_picks = (
                get_champions(
                    blue,
                    "pick"
                )
            )


            red_picks = (
                get_champions(
                    red,
                    "pick"
                )
            )


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
                    "밴/픽 데이터 누락"
                )


            # =================================================
            # First Pick
            # =================================================

            blue_first = (
                is_first_pick(
                    blue,
                    firstpick_col
                )
            )


            red_first = (
                is_first_pick(
                    red,
                    firstpick_col
                )
            )


            if (
                blue_first
                and not red_first
            ):

                first_pick_side = (
                    "BLUE"
                )


            elif (
                red_first
                and not blue_first
            ):

                first_pick_side = (
                    "RED"
                )


            else:

                raise ValueError(
                    "First Pick 확인 실패"
                )


            # =================================================
            # 승패
            # =================================================

            blue_result = (
                parse_result(
                    blue[
                        result_col
                    ]
                )
            )


            red_result = (
                parse_result(
                    red[
                        result_col
                    ]
                )
            )


            if (

                blue_result
                + red_result

                != 1

            ):

                raise ValueError(
                    "승패 result가 "
                    "정상적이지 않음"
                )


            blue_team = (
                clean_value(
                    blue[
                        team_col
                    ]
                )
            )


            red_team = (
                clean_value(
                    red[
                        team_col
                    ]
                )
            )


            winner_side = (

                "BLUE"

                if blue_result == 1

                else "RED"
            )


            winner_team = (

                blue_team

                if winner_side
                == "BLUE"

                else red_team
            )


            game_number_value = (
                pd.to_numeric(

                    blue[
                        game_number_col
                    ],

                    errors="coerce"
                )
            )


            if pd.isna(
                game_number_value
            ):

                raise ValueError(
                    "game_number 없음"
                )


            # =================================================
            # 경기 기본 데이터
            # =================================================

            record = {

                "game_id":
                    str(
                        game_id
                    ),

                "date":
                    blue[
                        date_col
                    ],

                "league":
                    TARGET_LEAGUE,

                "year":
                    TARGET_YEAR,

                "game_number":
                    int(
                        game_number_value
                    ),

                "tournament":

                    clean_value(
                        blue[
                            tournament_col
                        ]
                    )

                    if tournament_col

                    else None,

                "split":

                    clean_value(
                        blue[
                            split_col
                        ]
                    )

                    if split_col

                    else None,

                "playoffs":

                    clean_value(
                        blue[
                            playoffs_col
                        ]
                    )

                    if playoffs_col

                    else None,

                "best_of":

                    clean_value(
                        blue[
                            bestof_col
                        ]
                    )

                    if bestof_col

                    else None,

                "patch":

                    clean_value(
                        blue[
                            patch_col
                        ]
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
                        blue[
                            url_col
                        ]
                    )

                    if url_col

                    else None,


                # --------------------------------------------
                # 팀
                # --------------------------------------------

                "blue_team":
                    blue_team,

                "blue_team_id":

                    clean_value(
                        blue[
                            teamid_col
                        ]
                    )

                    if teamid_col

                    else None,

                "red_team":
                    red_team,

                "red_team_id":

                    clean_value(
                        red[
                            teamid_col
                        ]
                    )

                    if teamid_col

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
                # Draft
                # --------------------------------------------

                "first_pick_side":
                    first_pick_side
            }


            # =================================================
            # Ban / Pick 저장
            # =================================================

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


            # =================================================
            # 경기 후 통계 보존
            # =================================================

            for (
                output_name,
                source_column
            ) in (
                actual_postgame_columns.items()
            ):

                record[
                    f"blue_{output_name}"
                ] = blue[
                    source_column
                ]

                record[
                    f"red_{output_name}"
                ] = red[
                    source_column
                ]


            games.append(
                record
            )


        except Exception as e:

            failed.append({

                "game_id":
                    str(
                        game_id
                    ),

                "reason":
                    str(e)
            })


    return (

        pd.DataFrame(
            games
        ),

        pd.DataFrame(
            failed
        ),

        lck
    )


# ============================================================
# 10. BO3 / BO5 시리즈 묶기
# ============================================================

def assign_series_ids(games):

    games = games.copy()


    def get_team_key(
        row,
        prefix
    ):

        team_id = row[
            f"{prefix}_team_id"
        ]


        if team_id:

            return str(
                team_id
            )


        return str(
            row[
                f"{prefix}_team"
            ]
        )


    games[
        "team_pair"
    ] = games.apply(

        lambda row:

        "|".join(
            sorted([

                get_team_key(
                    row,
                    "blue"
                ),

                get_team_key(
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

    ).reset_index(
        drop=True
    )


    series_ids = [

        None

    ] * len(
        games
    )


    for _, group in (
        games.groupby(
            "team_pair",
            sort=False
        )
    ):

        series_number = 0

        previous_game_number = None

        previous_date = None

        current_series_id = None


        for index, row in (
            group.iterrows()
        ):

            current_date = (
                row[
                    "date"
                ]
            )


            game_number = (
                row[
                    "game_number"
                ]
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

                and pd.notna(
                    current_date
                )

            ):

                hours = (

                    (
                        current_date
                        - previous_date
                    )
                    .total_seconds()

                    / 3600
                )


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


                teams = sorted([

                    safe_name(
                        row[
                            "blue_team"
                        ]
                    ),

                    safe_name(
                        row[
                            "red_team"
                        ]
                    )
                ])


                current_series_id = (

                    f"{TARGET_LEAGUE}_"
                    f"{date_text}_"
                    f"{teams[0]}_vs_"
                    f"{teams[1]}_"
                    f"S{series_number}"
                )


            series_ids[
                index
            ] = (
                current_series_id
            )


            previous_game_number = (
                game_number
            )


            previous_date = (
                current_date
            )


    games[
        "series_id"
    ] = series_ids


    return games


# ============================================================
# 11. 시리즈 스코어
# ============================================================

def add_series_context(
    games
):

    games = games.copy()


    games[
        "blue_series_wins_before"
    ] = 0


    games[
        "red_series_wins_before"
    ] = 0


    games[
        "series_games_before"
    ] = 0


    for _, group in (
        games.groupby(
            "series_id"
        )
    ):

        group = group.sort_values(
            [
                "game_number",
                "date"
            ]
        )


        team_wins = {}

        games_played = 0


        for index, row in (
            group.iterrows()
        ):

            blue_team = (
                row[
                    "blue_team"
                ]
            )


            red_team = (
                row[
                    "red_team"
                ]
            )


            team_wins.setdefault(
                blue_team,
                0
            )


            team_wins.setdefault(
                red_team,
                0
            )


            games.at[
                index,
                "blue_series_wins_before"
            ] = team_wins[
                blue_team
            ]


            games.at[
                index,
                "red_series_wins_before"
            ] = team_wins[
                red_team
            ]


            games.at[
                index,
                "series_games_before"
            ] = games_played


            winner = (
                row[
                    "winner_team"
                ]
            )


            team_wins[
                winner
            ] += 1


            games_played += 1


    return games


# ============================================================
# 12. Fearless
#
# 이전 Game에서 PICK된 챔피언만 사용 불가로 누적
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


    games[
        "fearless_repeated_champions"
    ] = "[]"


    for _, group in (
        games.groupby(
            "series_id"
        )
    ):

        group = group.sort_values(
            [
                "game_number",
                "date"
            ]
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
            ] = len(
                unavailable
            )


            current_picks = []


            for i in range(
                1,
                6
            ):

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


            games.at[
                index,
                "fearless_repeated_champions"
            ] = json.dumps(

                repeats,

                ensure_ascii=False
            )


            if (
                USE_FEARLESS
                and repeats
            ):

                games.at[
                    index,
                    "fearless_repeat_detected"
                ] = True


            if USE_FEARLESS:

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
# 13. 경기 시작 전 팀 승률
#
# 현재 경기 결과는 모든 Feature를 만든 후 반영
#
# → 데이터 누수 방지
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

    ).reset_index(
        drop=True
    )


    overall = {}

    recent_results = {}

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

            return str(
                team_id
            )


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


        patch = (
            game[
                "patch"
            ]
        )


        overall.setdefault(
            blue,
            [0, 0]
        )


        overall.setdefault(
            red,
            [0, 0]
        )


        recent_results.setdefault(
            blue,
            []
        )


        recent_results.setdefault(
            red,
            []
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


        h2h_stats[
            pair
        ].setdefault(
            blue,
            [0, 0]
        )


        h2h_stats[
            pair
        ].setdefault(
            red,
            [0, 0]
        )


        # ====================================================
        # BLUE 이전 기록
        # ====================================================

        games.at[
            index,
            "blue_games_before"
        ] = overall[
            blue
        ][0]


        games.at[
            index,
            "blue_wins_before"
        ] = overall[
            blue
        ][1]


        games.at[
            index,
            "blue_win_rate_before"
        ] = safe_win_rate(

            overall[
                blue
            ][1],

            overall[
                blue
            ][0]
        )


        games.at[
            index,
            "blue_last5_win_rate_before"
        ] = recent_win_rate(

            recent_results[
                blue
            ],

            5
        )


        games.at[
            index,
            "blue_last10_win_rate_before"
        ] = recent_win_rate(

            recent_results[
                blue
            ],

            10
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
        ] = safe_win_rate(

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
        ] = safe_win_rate(

            patch_stats[
                (blue, patch)
            ][1],

            patch_stats[
                (blue, patch)
            ][0]
        )


        # ====================================================
        # RED 이전 기록
        # ====================================================

        games.at[
            index,
            "red_games_before"
        ] = overall[
            red
        ][0]


        games.at[
            index,
            "red_wins_before"
        ] = overall[
            red
        ][1]


        games.at[
            index,
            "red_win_rate_before"
        ] = safe_win_rate(

            overall[
                red
            ][1],

            overall[
                red
            ][0]
        )


        games.at[
            index,
            "red_last5_win_rate_before"
        ] = recent_win_rate(

            recent_results[
                red
            ],

            5
        )


        games.at[
            index,
            "red_last10_win_rate_before"
        ] = recent_win_rate(

            recent_results[
                red
            ],

            10
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
        ] = safe_win_rate(

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
        ] = safe_win_rate(

            patch_stats[
                (red, patch)
            ][1],

            patch_stats[
                (red, patch)
            ][0]
        )


        # ====================================================
        # H2H
        # ====================================================

        blue_h2h = (
            h2h_stats[
                pair
            ][blue]
        )


        red_h2h = (
            h2h_stats[
                pair
            ][red]
        )


        games.at[
            index,
            "blue_h2h_games_before"
        ] = blue_h2h[0]


        games.at[
            index,
            "blue_h2h_win_rate_before"
        ] = safe_win_rate(

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
        ] = safe_win_rate(

            red_h2h[1],
            red_h2h[0]
        )


        # ====================================================
        # 여기서부터 현재 경기 결과 반영
        # ====================================================

        blue_win = int(

            game[
                "blue_result"
            ]

            == 1
        )


        red_win = int(

            game[
                "red_result"
            ]

            == 1
        )


        overall[
            blue
        ][0] += 1


        overall[
            blue
        ][1] += blue_win


        overall[
            red
        ][0] += 1


        overall[
            red
        ][1] += red_win


        recent_results[
            blue
        ].append(
            blue_win
        )


        recent_results[
            red
        ].append(
            red_win
        )


        side_stats[
            (blue, "BLUE")
        ][0] += 1


        side_stats[
            (blue, "BLUE")
        ][1] += blue_win


        side_stats[
            (red, "RED")
        ][0] += 1


        side_stats[
            (red, "RED")
        ][1] += red_win


        patch_stats[
            (blue, patch)
        ][0] += 1


        patch_stats[
            (blue, patch)
        ][1] += blue_win


        patch_stats[
            (red, patch)
        ][0] += 1


        patch_stats[
            (red, patch)
        ][1] += red_win


        h2h_stats[
            pair
        ][blue][0] += 1


        h2h_stats[
            pair
        ][blue][1] += blue_win


        h2h_stats[
            pair
        ][red][0] += 1


        h2h_stats[
            pair
        ][red][1] += red_win


    return games


# ============================================================
# 14. 챔피언 메타 History
# ============================================================

def build_champion_meta_history(
    games
):

    games = games.sort_values(

        [
            "date",
            "series_id",
            "game_number"
        ]

    )


    stats = {}

    patch_stats = {}

    team_champion_stats = {}

    total_games = 0

    patch_games = {}

    records = []


    for _, game in (
        games.iterrows()
    ):

        patch = (
            game[
                "patch"
            ]
        )


        patch_games.setdefault(
            patch,
            0
        )


        current_updates = []


        # ====================================================
        # BANS
        # ====================================================

        for side in (
            "BLUE",
            "RED"
        ):

            prefix = (
                side.lower()
            )


            for ban_index in range(
                1,
                6
            ):

                champion = (

                    game[
                        f"{prefix}_ban"
                        f"{ban_index}"
                    ]
                )


                stats.setdefault(

                    champion,

                    {
                        "picks": 0,
                        "bans": 0,
                        "pick_wins": 0
                    }
                )


                patch_key = (
                    champion,
                    patch
                )


                patch_stats.setdefault(

                    patch_key,

                    {
                        "picks": 0,
                        "bans": 0,
                        "pick_wins": 0
                    }
                )


                overall = (
                    stats[
                        champion
                    ]
                )


                patch_data = (
                    patch_stats[
                        patch_key
                    ]
                )


                records.append({

                    "game_id":
                        game[
                            "game_id"
                        ],

                    "series_id":
                        game[
                            "series_id"
                        ],

                    "game_number":
                        game[
                            "game_number"
                        ],

                    "date":
                        game[
                            "date"
                        ],

                    "patch":
                        patch,

                    "champion":
                        champion,

                    "current_action":
                        "BAN",

                    "current_side":
                        side,

                    "team":
                        None,

                    "picks_before":
                        overall[
                            "picks"
                        ],

                    "bans_before":
                        overall[
                            "bans"
                        ],

                    "presence_before":

                        (
                            overall[
                                "picks"
                            ]

                            + overall[
                                "bans"
                            ]
                        ),

                    "pick_rate_before":

                        (
                            overall[
                                "picks"
                            ]
                            / total_games

                            if total_games > 0

                            else None
                        ),

                    "ban_rate_before":

                        (
                            overall[
                                "bans"
                            ]
                            / total_games

                            if total_games > 0

                            else None
                        ),

                    "presence_rate_before":

                        (
                            (
                                overall[
                                    "picks"
                                ]

                                + overall[
                                    "bans"
                                ]
                            )
                            / total_games

                            if total_games > 0

                            else None
                        ),

                    "pick_win_rate_before":

                        safe_win_rate(

                            overall[
                                "pick_wins"
                            ],

                            overall[
                                "picks"
                            ]
                        ),

                    "patch_picks_before":
                        patch_data[
                            "picks"
                        ],

                    "patch_bans_before":
                        patch_data[
                            "bans"
                        ],

                    "patch_pick_win_rate_before":

                        safe_win_rate(

                            patch_data[
                                "pick_wins"
                            ],

                            patch_data[
                                "picks"
                            ]
                        ),

                    "patch_presence_rate_before":

                        (
                            (
                                patch_data[
                                    "picks"
                                ]

                                + patch_data[
                                    "bans"
                                ]
                            )
                            / patch_games[
                                patch
                            ]

                            if patch_games[
                                patch
                            ] > 0

                            else None
                        ),

                    "team_champion_games_before":
                        None,

                    "team_champion_win_rate_before":
                        None,

                    "picked_side_won":
                        None
                })


                current_updates.append({

                    "type":
                        "BAN",

                    "champion":
                        champion,

                    "patch_key":
                        patch_key
                })


        # ====================================================
        # PICKS
        # ====================================================

        for side in (
            "BLUE",
            "RED"
        ):

            prefix = (
                side.lower()
            )


            team_id = (

                game[
                    f"{prefix}_team_id"
                ]
            )


            team = (

                game[
                    f"{prefix}_team"
                ]
            )


            team_key = (

                str(team_id)

                if team_id

                else str(team)
            )


            won = int(

                game[
                    "winner_side"
                ]

                == side
            )


            for pick_index in range(
                1,
                6
            ):

                champion = (

                    game[
                        f"{prefix}_pick"
                        f"{pick_index}"
                    ]
                )


                stats.setdefault(

                    champion,

                    {
                        "picks": 0,
                        "bans": 0,
                        "pick_wins": 0
                    }
                )


                patch_key = (
                    champion,
                    patch
                )


                patch_stats.setdefault(

                    patch_key,

                    {
                        "picks": 0,
                        "bans": 0,
                        "pick_wins": 0
                    }
                )


                team_champion_key = (

                    team_key,
                    champion
                )


                team_champion_stats.setdefault(

                    team_champion_key,

                    [0, 0]
                )


                overall = (
                    stats[
                        champion
                    ]
                )


                patch_data = (
                    patch_stats[
                        patch_key
                    ]
                )


                team_champion = (
                    team_champion_stats[
                        team_champion_key
                    ]
                )


                records.append({

                    "game_id":
                        game[
                            "game_id"
                        ],

                    "series_id":
                        game[
                            "series_id"
                        ],

                    "game_number":
                        game[
                            "game_number"
                        ],

                    "date":
                        game[
                            "date"
                        ],

                    "patch":
                        patch,

                    "champion":
                        champion,

                    "current_action":
                        "PICK",

                    "current_side":
                        side,

                    "team":
                        team,

                    "picks_before":
                        overall[
                            "picks"
                        ],

                    "bans_before":
                        overall[
                            "bans"
                        ],

                    "presence_before":

                        (
                            overall[
                                "picks"
                            ]

                            + overall[
                                "bans"
                            ]
                        ),

                    "pick_rate_before":

                        (
                            overall[
                                "picks"
                            ]
                            / total_games

                            if total_games > 0

                            else None
                        ),

                    "ban_rate_before":

                        (
                            overall[
                                "bans"
                            ]
                            / total_games

                            if total_games > 0

                            else None
                        ),

                    "presence_rate_before":

                        (
                            (
                                overall[
                                    "picks"
                                ]

                                + overall[
                                    "bans"
                                ]
                            )

                            / total_games

                            if total_games > 0

                            else None
                        ),

                    "pick_win_rate_before":

                        safe_win_rate(

                            overall[
                                "pick_wins"
                            ],

                            overall[
                                "picks"
                            ]
                        ),

                    "patch_picks_before":
                        patch_data[
                            "picks"
                        ],

                    "patch_bans_before":
                        patch_data[
                            "bans"
                        ],

                    "patch_pick_win_rate_before":

                        safe_win_rate(

                            patch_data[
                                "pick_wins"
                            ],

                            patch_data[
                                "picks"
                            ]
                        ),

                    "patch_presence_rate_before":

                        (
                            (
                                patch_data[
                                    "picks"
                                ]

                                + patch_data[
                                    "bans"
                                ]
                            )

                            / patch_games[
                                patch
                            ]

                            if patch_games[
                                patch
                            ] > 0

                            else None
                        ),

                    "team_champion_games_before":
                        team_champion[0],

                    "team_champion_win_rate_before":

                        safe_win_rate(

                            team_champion[1],
                            team_champion[0]
                        ),

                    "picked_side_won":
                        won
                })


                current_updates.append({

                    "type":
                        "PICK",

                    "champion":
                        champion,

                    "patch_key":
                        patch_key,

                    "team_champion_key":
                        team_champion_key,

                    "won":
                        won
                })


        # ====================================================
        # 현재 경기 결과 반영
        # ====================================================

        for update in (
            current_updates
        ):

            champion = (
                update[
                    "champion"
                ]
            )


            patch_key = (
                update[
                    "patch_key"
                ]
            )


            if (
                update[
                    "type"
                ]
                == "BAN"
            ):

                stats[
                    champion
                ][
                    "bans"
                ] += 1


                patch_stats[
                    patch_key
                ][
                    "bans"
                ] += 1


            else:

                won = (
                    update[
                        "won"
                    ]
                )


                team_champion_key = (

                    update[
                        "team_champion_key"
                    ]
                )


                stats[
                    champion
                ][
                    "picks"
                ] += 1


                stats[
                    champion
                ][
                    "pick_wins"
                ] += won


                patch_stats[
                    patch_key
                ][
                    "picks"
                ] += 1


                patch_stats[
                    patch_key
                ][
                    "pick_wins"
                ] += won


                team_champion_stats[
                    team_champion_key
                ][0] += 1


                team_champion_stats[
                    team_champion_key
                ][1] += won


        total_games += 1


        patch_games[
            patch
        ] += 1


    return pd.DataFrame(
        records
    )


# ============================================================
# 15. 실제 Draft Actions Dataset
# ============================================================

def build_actions(
    games
):

    output = []


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


        if len(actions) != 20:

            print(

                f"[경고] game_id="
                f"{game['game_id']} "

                f"Draft Action이 "
                f"{len(actions)}개입니다."
            )


        for action in actions:

            acting_side = (
                action[
                    "side"
                ]
            )


            action.update({

                # --------------------------------------------
                # 경기 정보
                # --------------------------------------------

                "game_id":
                    game[
                        "game_id"
                    ],

                "series_id":
                    game[
                        "series_id"
                    ],

                "game_number":
                    game[
                        "game_number"
                    ],

                "date":
                    game[
                        "date"
                    ],

                "patch":
                    game[
                        "patch"
                    ],

                "blue_team":
                    game[
                        "blue_team"
                    ],

                "red_team":
                    game[
                        "red_team"
                    ],

                "first_pick_side":
                    game[
                        "first_pick_side"
                    ],


                # --------------------------------------------
                # 시리즈 상태
                # --------------------------------------------

                "blue_series_wins_before":

                    game[
                        "blue_series_wins_before"
                    ],

                "red_series_wins_before":

                    game[
                        "red_series_wins_before"
                    ],

                "series_games_before":

                    game[
                        "series_games_before"
                    ],


                # --------------------------------------------
                # Fearless
                # --------------------------------------------

                "fearless_unavailable":

                    game[
                        "fearless_unavailable_before_game"
                    ],

                "fearless_unavailable_count":

                    game[
                        "fearless_unavailable_count"
                    ],


                # --------------------------------------------
                # 과거 승률
                # --------------------------------------------

                "blue_win_rate_before":

                    game[
                        "blue_win_rate_before"
                    ],

                "red_win_rate_before":

                    game[
                        "red_win_rate_before"
                    ],

                "blue_last5_win_rate_before":

                    game[
                        "blue_last5_win_rate_before"
                    ],

                "red_last5_win_rate_before":

                    game[
                        "red_last5_win_rate_before"
                    ],

                "blue_last10_win_rate_before":

                    game[
                        "blue_last10_win_rate_before"
                    ],

                "red_last10_win_rate_before":

                    game[
                        "red_last10_win_rate_before"
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
                # 결과 Label
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


            output.append(
                action
            )


    return pd.DataFrame(
        output
    )


# ============================================================
# 16. 모델 학습용 Sample
#
# 현재 draft_state
#       ↓
# 다음 BAN/PICK 예측
#
# 한 경기당 20개 Sample
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


        current_state = []


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
                # 시리즈
                # --------------------------------------------

                "blue_series_wins_before":

                    action[
                        "blue_series_wins_before"
                    ],

                "red_series_wins_before":

                    action[
                        "red_series_wins_before"
                    ],

                "series_games_before":

                    action[
                        "series_games_before"
                    ],


                # --------------------------------------------
                # 현재 Draft
                # --------------------------------------------

                "step":
                    action[
                        "order"
                    ],

                "current_phase":
                    action[
                        "phase"
                    ],

                "draft_state":

                    json.dumps(

                        current_state,

                        ensure_ascii=False
                    ),


                # --------------------------------------------
                # Fearless
                # --------------------------------------------

                "fearless_unavailable":

                    action[
                        "fearless_unavailable"
                    ],

                "fearless_unavailable_count":

                    action[
                        "fearless_unavailable_count"
                    ],


                # --------------------------------------------
                # 경기 전 승률 Feature
                # --------------------------------------------

                "blue_win_rate_before":

                    action[
                        "blue_win_rate_before"
                    ],

                "red_win_rate_before":

                    action[
                        "red_win_rate_before"
                    ],

                "blue_last5_win_rate_before":

                    action[
                        "blue_last5_win_rate_before"
                    ],

                "red_last5_win_rate_before":

                    action[
                        "red_last5_win_rate_before"
                    ],

                "blue_last10_win_rate_before":

                    action[
                        "blue_last10_win_rate_before"
                    ],

                "red_last10_win_rate_before":

                    action[
                        "red_last10_win_rate_before"
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
                # 다음 행동 예측 Label
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
                # 승률 모델 Label
                #
                # Feature로 사용하면 안 됨
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


            # =================================================
            # 현재 행동을 다음 상태에 추가
            # =================================================

            current_state.append({

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
# 17. 데이터 검증
# ============================================================

def validate_outputs(
    games,
    actions
):

    print()
    print(
        "========================================"
    )

    print(
        "데이터 검증"
    )

    print(
        "========================================"
    )


    print(
        "경기 수:",
        len(
            games
        )
    )


    print(
        "Draft Action 수:",
        len(
            actions
        )
    )


    expected_actions = (

        len(
            games
        )

        * 20
    )


    print(
        "예상 Draft Action 수:",
        expected_actions
    )


    if (
        len(actions)
        != expected_actions
    ):

        print(
            "[경고] 일부 경기의 "
            "20단계 밴픽 복원에 "
            "문제가 있을 수 있습니다."
        )


    if not actions.empty:

        action_counts = (

            actions.groupby(
                "game_id"
            )
            .size()
        )


        bad_games = action_counts[
            action_counts
            != 20
        ]


        print(
            "20 Actions가 아닌 경기 수:",
            len(
                bad_games
            )
        )


    fearless_repeats = games[

        games[
            "fearless_repeat_detected"
        ]

        == True

    ]


    print(
        "Fearless 중복 감지 경기:",
        len(
            fearless_repeats
        )
    )


# ============================================================
# 18. MAIN
# ============================================================

def main():

    print()
    print(
        "========================================"
    )

    print(
        "Oracle's Elixir → LCK Dataset Builder"
    )

    print(
        "========================================"
    )


    source_updated = False


    # ========================================================
    # Oracle 최신 데이터 자동 다운로드
    # ========================================================

    if AUTO_DOWNLOAD:

        try:

            source_updated = (
                download_latest_oracle_data()
            )


        except Exception as e:

            print()
            print(
                "자동 다운로드 실패:"
            )

            print(
                e
            )


            if RAW_FILE.exists():

                print()
                print(
                    "기존 로컬 Oracle 파일로 "
                    "계속 진행합니다."
                )


            else:

                raise


    # ========================================================
    # Oracle Raw 존재 확인
    # ========================================================

    if not RAW_FILE.exists():

        raise FileNotFoundError(
            f"Oracle 파일 없음: "
            f"{RAW_FILE}"
        )


    # ========================================================
    # Hash
    # ========================================================

    current_hash = (
        calculate_sha256(
            RAW_FILE
        )
    )


    print()
    print(
        "현재 Oracle SHA256:",
        current_hash[:16]
    )


    source_changed_since_last_run = (

        not source_is_unchanged(
            current_hash
        )
    )


    # ========================================================
    # 완성 후 자동 운영 모드
    # ========================================================

    if (

        SKIP_IF_SOURCE_UNCHANGED

        and not source_changed_since_last_run

    ):

        print(
            "Oracle 원본이 이전 실행과 동일합니다."
        )

        print(
            "데이터셋 생성을 건너뜁니다."
        )

        return


    # ========================================================
    # Oracle 읽기
    # ========================================================

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
        len(
            df
        )
    )


    # ========================================================
    # LCK 경기 데이터
    # ========================================================

    games, failed, raw_lck = (
        build_games(
            df
        )
    )


    print(
        "LCK 완성 경기:",
        len(
            games
        )
    )


    if games.empty:

        raise ValueError(
            "가공 가능한 LCK 경기가 없습니다."
        )


    # ========================================================
    # Series
    # ========================================================

    games = (
        assign_series_ids(
            games
        )
    )


    # ========================================================
    # 시리즈 스코어
    # ========================================================

    games = (
        add_series_context(
            games
        )
    )


    # ========================================================
    # Fearless
    # ========================================================

    games = (
        add_fearless_info(
            games
        )
    )


    # ========================================================
    # 팀 승률
    # ========================================================

    games = (
        add_team_history(
            games
        )
    )


    # ========================================================
    # 챔피언 메타
    # ========================================================

    champion_meta = (
        build_champion_meta_history(
            games
        )
    )


    # ========================================================
    # Draft Actions
    # ========================================================

    actions = (
        build_actions(
            games
        )
    )


    # ========================================================
    # Training Samples
    # ========================================================

    training = (
        build_training_samples(
            actions
        )
    )


    # ========================================================
    # 검증
    # ========================================================

    validate_outputs(
        games,
        actions
    )


    # ========================================================
    # 최신 파일
    #
    # 코드 수정 후 실행해도 항상 다시 생성
    # ========================================================

    output_paths = []


    output_paths.append(

        safe_write_csv(

            raw_lck,

            PROCESSED_DIR
            / "lck_raw_latest.csv"
        )
    )


    output_paths.append(

        safe_write_csv(

            games,

            PROCESSED_DIR
            / "lck_games_latest.csv"
        )
    )


    output_paths.append(

        safe_write_csv(

            actions,

            PROCESSED_DIR
            / "lck_draft_actions_latest.csv"
        )
    )


    output_paths.append(

        safe_write_csv(

            training,

            PROCESSED_DIR
            / "lck_training_samples_latest.csv"
        )
    )


    output_paths.append(

        safe_write_csv(

            champion_meta,

            PROCESSED_DIR
            / "lck_champion_meta_history_latest.csv"
        )
    )


    # ========================================================
    # 실패 경기
    # ========================================================

    if not failed.empty:

        output_paths.append(

            safe_write_csv(

                failed,

                PROCESSED_DIR
                / "failed_games.csv"
            )
        )


    # ========================================================
    # Snapshot
    #
    # Oracle 원본 데이터가 실제로 변경됐을 때만 저장
    #
    # 날짜 + 시간 사용
    #
    # 같은 날 여러 번 데이터가 갱신되어도 충돌 X
    # ========================================================

    should_snapshot = (

        source_updated

        or source_changed_since_last_run
    )


    if should_snapshot:

        timestamp = (

            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )


        output_paths.append(

            safe_write_csv(

                games,

                PROCESSED_DIR
                / (
                    f"lck_games_"
                    f"{timestamp}.csv"
                )
            )
        )


        output_paths.append(

            safe_write_csv(

                actions,

                PROCESSED_DIR
                / (
                    f"lck_draft_actions_"
                    f"{timestamp}.csv"
                )
            )
        )


        print()
        print(
            "새 Oracle 원본 기준 "
            "Snapshot 저장 완료"
        )


    # ========================================================
    # Metadata
    # ========================================================

    metadata = {

        "processed_at":
            datetime.now()
            .isoformat(),

        "source":
            "Oracle's Elixir",

        "oracle_google_drive_file_id":
            ORACLE_FILE_ID,

        "source_file":
            str(
                RAW_FILE
            ),

        "source_sha256":
            current_hash,

        "source_updated_this_run":
            source_updated,

        "year":
            TARGET_YEAR,

        "league":
            TARGET_LEAGUE,

        "fearless_enabled":
            USE_FEARLESS,

        "raw_lck_rows":
            len(
                raw_lck
            ),

        "games":
            len(
                games
            ),

        "draft_actions":
            len(
                actions
            ),

        "training_samples":
            len(
                training
            ),

        "champion_meta_rows":
            len(
                champion_meta
            ),

        "failed_games":
            len(
                failed
            )
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
        "========================================"
    )

    print(
        "데이터셋 생성 완료"
    )

    print(
        "========================================"
    )


    print(
        "LCK 경기:",
        len(
            games
        )
    )


    print(
        "Draft Action:",
        len(
            actions
        )
    )


    print(
        "Training Sample:",
        len(
            training
        )
    )


    print(
        "Champion Meta:",
        len(
            champion_meta
        )
    )


    print(
        "실패 경기:",
        len(
            failed
        )
    )


    print()
    print(
        "저장된 파일:"
    )


    for path in (
        output_paths
    ):

        print(
            path
        )


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    main()