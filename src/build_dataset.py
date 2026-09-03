from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime
import hashlib
import json
import re
import shutil

import gdown
import numpy as np
import pandas as pd


# ============================================================
# 0. 기본 설정
# ============================================================

TARGET_LEAGUE = "LCK"
TARGET_YEARS = [2025, 2026]

# 2025, 2026 Fearless 적용
FEARLESS_YEARS = {2025, 2026}

# 같은 두 팀의 경기가 이 시간보다 멀리 떨어져 있으면
# 다른 시리즈로 판단
MAX_SERIES_GAP_HOURS = 12

# 밴 카드를 사용하지 않은 경우 저장할 값
NO_BAN_TOKEN = "NO_BAN"


# ============================================================
# 1. 2026 Oracle 자동 다운로드 설정
# ============================================================

AUTO_DOWNLOAD_2026 = True

ORACLE_2026_FILE_ID = (
    "1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm"
)


# ============================================================
# 2. 폴더 경로
# ============================================================

RAW_DIR = Path("data/raw")
ARCHIVE_DIR = Path("data/raw_archive")
PROCESSED_DIR = Path("data/processed")

RAW_DIR.mkdir(
    parents=True,
    exist_ok=True
)

ARCHIVE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

PROCESSED_DIR.mkdir(
    parents=True,
    exist_ok=True
)


RAW_FILES = {

    2025:
        RAW_DIR
        / "2025_LoL_esports_match_data_from_OraclesElixir.csv",

    2026:
        RAW_DIR
        / "2026_LoL_esports_match_data_from_OraclesElixir.csv",
}


# ============================================================
# 3. 기본 함수
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
        str(column).lower(): column
        for column in df.columns
    }

    for name in names:

        if name in df.columns:
            return name

        lower_name = name.lower()

        if lower_name in lower_map:
            return lower_map[lower_name]

    return None


def safe_name(value):

    if value is None:
        return "unknown"

    value = str(value)

    value = re.sub(
        r"[^A-Za-z0-9가-힣]+",
        "_",
        value
    )

    return value.strip("_")


def calculate_rate(wins, games):

    if games == 0:
        return np.nan

    return wins / games


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

            sha.update(chunk)

    return sha.hexdigest()


# ============================================================
# 5. 원본 파일 백업
# ============================================================

def archive_file(year, path):

    if not path.exists():
        return

    file_hash = calculate_sha256(path)

    existing = list(
        ARCHIVE_DIR.glob(
            f"{year}_OE_*_{file_hash[:10]}.csv"
        )
    )

    # 동일한 파일은 다시 백업하지 않음
    if existing:
        return

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    archive_path = (
        ARCHIVE_DIR
        / (
            f"{year}_OE_"
            f"{timestamp}_"
            f"{file_hash[:10]}.csv"
        )
    )

    shutil.copy2(
        path,
        archive_path
    )

    print(
        f"[{year}] 원본 백업:",
        archive_path
    )


# ============================================================
# 6. 2026 Oracle 최신 파일 자동 다운로드
# ============================================================

def download_latest_2026():

    if not AUTO_DOWNLOAD_2026:

        print(
            "[2026] 자동 다운로드 비활성화"
        )

        return


    output_path = RAW_FILES[2026]

    temp_path = (
        RAW_DIR
        / "2026_oracle_download_temp.csv"
    )


    if temp_path.exists():
        temp_path.unlink()


    print()
    print(
        "======================================"
    )

    print(
        "[2026] Oracle 최신 데이터 다운로드"
    )

    print(
        "======================================"
    )

    print(
        "Google Drive에서 다운로드 중..."
    )


    try:

        result = gdown.download(
            id=ORACLE_2026_FILE_ID,
            output=str(temp_path),
            quiet=False
        )

    except Exception as error:

        print()
        print(
            "[2026] 다운로드 실패:"
        )

        print(error)

        if output_path.exists():

            print(
                "기존 2026 파일을 사용합니다."
            )

            return

        raise


    if (
        result is None
        or not temp_path.exists()
    ):

        if output_path.exists():

            print(
                "[2026] 다운로드 실패"
            )

            print(
                "기존 2026 파일을 사용합니다."
            )

            return

        raise RuntimeError(
            "2026 Oracle 데이터를 "
            "다운로드하지 못했습니다."
        )


    # --------------------------------------------------------
    # 실제 CSV인지 확인
    # --------------------------------------------------------

    try:

        test_df = pd.read_csv(
            temp_path,
            nrows=5,
            low_memory=False
        )

        if len(test_df.columns) < 5:

            raise ValueError(
                "다운로드한 파일의 컬럼 수가 비정상적입니다."
            )

    except Exception as error:

        temp_path.unlink(
            missing_ok=True
        )

        if output_path.exists():

            print()
            print(
                "[2026] 다운로드 파일이 정상 CSV가 아닙니다."
            )

            print(error)

            print(
                "기존 2026 파일을 사용합니다."
            )

            return

        raise


    new_hash = calculate_sha256(
        temp_path
    )


    # ========================================================
    # 기존 파일과 비교
    # ========================================================

    if output_path.exists():

        old_hash = calculate_sha256(
            output_path
        )


        if new_hash == old_hash:

            print()
            print(
                "[2026] Oracle 데이터 변경 없음"
            )

            print(
                "기존 2026 파일을 그대로 사용합니다."
            )

            temp_path.unlink()

            return


        print()
        print(
            "[2026] 새로운 데이터 확인"
        )

        print(
            "기존 2026 파일을 백업합니다."
        )

        archive_file(
            2026,
            output_path
        )


    # ========================================================
    # 최신 파일로 교체
    # ========================================================

    shutil.move(
        str(temp_path),
        str(output_path)
    )


    print()
    print(
        "[2026] 최신 Oracle 데이터 저장 완료:"
    )

    print(output_path)

    print(
        "SHA256:",
        new_hash[:16]
    )


# ============================================================
# 7. 2025 + 2026 Oracle 읽기
# ============================================================

def load_oracle_files():

    frames = []
    hashes = {}


    # 2026만 자동 다운로드
    download_latest_2026()


    for year in TARGET_YEARS:

        path = RAW_FILES[year]


        if not path.exists():

            raise FileNotFoundError(

                f"\n{year} Oracle CSV가 없습니다.\n\n"

                f"파일 위치:\n"
                f"{path}\n"
            )


        archive_file(
            year,
            path
        )


        print()
        print(
            f"[{year}] Oracle CSV 읽는 중..."
        )


        df = pd.read_csv(
            path,
            low_memory=False
        )


        # 원본에 year가 없을 경우 대비
        df["_source_year"] = year


        hashes[year] = (
            calculate_sha256(
                path
            )
        )


        print(
            f"[{year}] 전체 행:",
            len(df)
        )


        frames.append(df)


    combined = pd.concat(
        frames,
        ignore_index=True
    )


    print()
    print(
        "2025 + 2026 전체 행:",
        len(combined)
    )


    return (
        combined,
        hashes
    )


# ============================================================
# 8. Oracle Schema 확인
# ============================================================

def get_schema(df):

    schema = {

        "league":
            find_column(
                df,
                "league"
            ),

        "year":
            find_column(
                df,
                "year"
            ),

        "date":
            find_column(
                df,
                "date"
            ),

        "gameid":
            find_column(
                df,
                "gameid"
            ),

        "game":
            find_column(
                df,
                "game"
            ),

        "position":
            find_column(
                df,
                "position"
            ),

        "side":
            find_column(
                df,
                "side"
            ),

        "teamname":
            find_column(
                df,
                "teamname",
                "team"
            ),

        "teamid":
            find_column(
                df,
                "teamid"
            ),

        "result":
            find_column(
                df,
                "result"
            ),

        "firstpick":
            find_column(
                df,
                "firstPick",
                "firstpick"
            ),

        "patch":
            find_column(
                df,
                "patch"
            ),

        "split":
            find_column(
                df,
                "split"
            ),

        "playoffs":
            find_column(
                df,
                "playoffs"
            ),

        "datacompleteness":
            find_column(
                df,
                "datacompleteness"
            ),

        "url":
            find_column(
                df,
                "url"
            ),

        "series":
            find_column(
                df,
                "seriesid",
                "series_id",
                "matchid",
                "match_id"
            )
    }


    required = [

        "league",
        "date",
        "gameid",
        "game",
        "position",
        "side",
        "teamname",
        "result",
        "firstpick"
    ]


    missing = [

        column

        for column
        in required

        if schema[column] is None
    ]


    if missing:

        print()
        print(
            "Oracle CSV 실제 컬럼:"
        )

        print(
            df.columns.tolist()
        )

        raise ValueError(
            f"필수 컬럼 없음: {missing}"
        )


    # ========================================================
    # Ban / Pick 컬럼 확인
    # ========================================================

    for prefix in [
        "ban",
        "pick"
    ]:

        for i in range(
            1,
            6
        ):

            column = (
                f"{prefix}{i}"
            )

            if column not in df.columns:

                raise ValueError(
                    f"필수 컬럼 없음: {column}"
                )


    return schema


# ============================================================
# 9. Ban / Pick 챔피언 추출
#
# 중요:
# Ban이 비어 있으면 NO_BAN으로 처리
# Pick이 비어 있으면 None 유지
# ============================================================

def get_champions(
    row,
    prefix
):

    champions = []


    for i in range(
        1,
        6
    ):

        value = clean_value(
            row[
                f"{prefix}{i}"
            ]
        )


        # ====================================================
        # 밴 카드 포기
        # ====================================================

        if (
            prefix == "ban"
            and value is None
        ):

            value = NO_BAN_TOKEN


        champions.append(
            value
        )


    return champions


# ============================================================
# 10. First Pick 판별
# ============================================================

def is_first_pick(
    row,
    column
):

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
# 11. 실패 경기 정보 추출
# ============================================================

def get_failed_game_context(
    game_rows,
    schema
):

    failed_year = None
    failed_date = None
    failed_blue_team = None
    failed_red_team = None


    # ========================================================
    # Year
    # ========================================================

    try:

        if schema["year"] is not None:

            values = (
                game_rows[
                    schema["year"]
                ]
                .dropna()
            )

            if not values.empty:

                failed_year = int(
                    float(
                        values.iloc[0]
                    )
                )


        if failed_year is None:

            values = (
                game_rows[
                    "_source_year"
                ]
                .dropna()
            )

            if not values.empty:

                failed_year = int(
                    values.iloc[0]
                )

    except Exception:
        pass


    # ========================================================
    # Date
    # ========================================================

    try:

        values = (
            game_rows[
                schema["date"]
            ]
            .dropna()
        )

        if not values.empty:

            failed_date = (
                values.iloc[0]
            )

    except Exception:
        pass


    # ========================================================
    # Teams
    # ========================================================

    try:

        team_rows = game_rows[

            game_rows[
                schema["position"]
            ]
            .astype(str)
            .str.lower()
            == "team"

        ]


        blue_rows = team_rows[

            team_rows[
                schema["side"]
            ]
            .astype(str)
            .str.lower()
            == "blue"

        ]


        red_rows = team_rows[

            team_rows[
                schema["side"]
            ]
            .astype(str)
            .str.lower()
            == "red"

        ]


        if not blue_rows.empty:

            failed_blue_team = clean_value(
                blue_rows.iloc[0][
                    schema["teamname"]
                ]
            )


        if not red_rows.empty:

            failed_red_team = clean_value(
                red_rows.iloc[0][
                    schema["teamname"]
                ]
            )

    except Exception:
        pass


    return {

        "year":
            failed_year,

        "date":
            failed_date,

        "blue_team":
            failed_blue_team,

        "red_team":
            failed_red_team
    }


# ============================================================
# 12. Oracle → 경기 단위 Dataset
# ============================================================

def build_base_games(
    full_df,
    schema
):

    df = full_df.copy()


    # ========================================================
    # 날짜 변환
    # ========================================================

    df[
        schema["date"]
    ] = pd.to_datetime(

        df[
            schema["date"]
        ],

        errors="coerce",

        utc=True
    )


    # ========================================================
    # LCK 필터
    # ========================================================

    lck = df[

        df[
            schema["league"]
        ]
        .astype(str)
        .str.upper()
        == TARGET_LEAGUE

    ].copy()


    # ========================================================
    # 2025 / 2026
    # ========================================================

    if schema["year"] is not None:

        numeric_year = pd.to_numeric(

            lck[
                schema["year"]
            ],

            errors="coerce"
        )


        lck = lck[

            numeric_year.isin(
                TARGET_YEARS
            )

        ].copy()


    else:

        lck = lck[

            lck[
                "_source_year"
            ].isin(
                TARGET_YEARS
            )

        ].copy()


    # ========================================================
    # Oracle LCK 원본 그대로 보존
    # ========================================================

    lck.to_csv(

        PROCESSED_DIR
        / "lck_raw_2025_2026.csv",

        index=False,

        encoding="utf-8-sig"
    )


    games = []
    failed = []


    # ========================================================
    # gameid 단위 처리
    # ========================================================

    for (
        game_id,
        game_rows
    ) in lck.groupby(
        schema["gameid"],
        sort=False
    ):

        try:

            # =================================================
            # Team 행
            # =================================================

            team_rows = game_rows[

                game_rows[
                    schema["position"]
                ]
                .astype(str)
                .str.lower()
                == "team"

            ]


            blue_rows = team_rows[

                team_rows[
                    schema["side"]
                ]
                .astype(str)
                .str.lower()
                == "blue"

            ]


            red_rows = team_rows[

                team_rows[
                    schema["side"]
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
                    "Blue/Red Team 행 오류"
                )


            blue = blue_rows.iloc[0]
            red = red_rows.iloc[0]


            # =================================================
            # Year
            # =================================================

            if schema["year"] is not None:

                year = int(
                    float(
                        blue[
                            schema["year"]
                        ]
                    )
                )

            else:

                year = int(
                    blue[
                        "_source_year"
                    ]
                )


            # =================================================
            # Teams
            # =================================================

            blue_team = clean_value(
                blue[
                    schema["teamname"]
                ]
            )

            red_team = clean_value(
                red[
                    schema["teamname"]
                ]
            )


            # =================================================
            # Ban / Pick
            # =================================================

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


            # =================================================
            # 중요:
            #
            # BAN은 NO_BAN 허용
            # PICK만 누락 검사
            # =================================================

            all_picks = (
                blue_picks
                + red_picks
            )


            if any(
                champion is None
                for champion
                in all_picks
            ):

                raise ValueError(
                    "픽 정보 누락"
                )


            # =================================================
            # First Pick
            # =================================================

            blue_first = is_first_pick(
                blue,
                schema[
                    "firstpick"
                ]
            )

            red_first = is_first_pick(
                red,
                schema[
                    "firstpick"
                ]
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
                    "First Pick 판별 실패"
                )


            # =================================================
            # 승패
            # =================================================

            blue_result = int(
                float(
                    blue[
                        schema["result"]
                    ]
                )
            )


            red_result = int(
                float(
                    red[
                        schema["result"]
                    ]
                )
            )


            if (
                blue_result
                + red_result
                != 1
            ):

                raise ValueError(
                    "승패 데이터 이상"
                )


            winner_side = (

                "BLUE"

                if blue_result == 1

                else "RED"
            )


            winner_team = (

                blue_team

                if blue_result == 1

                else red_team
            )


            # =================================================
            # 경기 기본 정보
            # =================================================

            record = {

                "game_id":
                    str(game_id),

                "year":
                    year,

                "date":
                    blue[
                        schema["date"]
                    ],

                "league":
                    TARGET_LEAGUE,

                "game_number":
                    int(
                        float(
                            blue[
                                schema["game"]
                            ]
                        )
                    ),

                "split":
                    (
                        clean_value(
                            blue[
                                schema["split"]
                            ]
                        )

                        if schema["split"]

                        else None
                    ),

                "playoffs":
                    (
                        clean_value(
                            blue[
                                schema["playoffs"]
                            ]
                        )

                        if schema["playoffs"]

                        else None
                    ),

                "patch":
                    (
                        clean_value(
                            blue[
                                schema["patch"]
                            ]
                        )

                        if schema["patch"]

                        else None
                    ),

                "datacompleteness":
                    (
                        clean_value(
                            blue[
                                schema[
                                    "datacompleteness"
                                ]
                            ]
                        )

                        if schema[
                            "datacompleteness"
                        ]

                        else None
                    ),

                "source_url":
                    (
                        clean_value(
                            blue[
                                schema["url"]
                            ]
                        )

                        if schema["url"]

                        else None
                    ),

                "source_series_id":
                    (
                        clean_value(
                            blue[
                                schema["series"]
                            ]
                        )

                        if schema["series"]

                        else None
                    ),

                "blue_team":
                    blue_team,

                "blue_team_id":
                    (
                        clean_value(
                            blue[
                                schema["teamid"]
                            ]
                        )

                        if schema["teamid"]

                        else None
                    ),

                "red_team":
                    red_team,

                "red_team_id":
                    (
                        clean_value(
                            red[
                                schema["teamid"]
                            ]
                        )

                        if schema["teamid"]

                        else None
                    ),

                "first_pick_side":
                    first_pick_side,

                "blue_result":
                    blue_result,

                "red_result":
                    red_result,

                "winner_side":
                    winner_side,

                "winner_team":
                    winner_team
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


            games.append(
                record
            )


        # ====================================================
        # Failed Game
        # ====================================================

        except Exception as error:

            context = (
                get_failed_game_context(
                    game_rows,
                    schema
                )
            )


            failed.append({

                "year":
                    context[
                        "year"
                    ],

                "date":
                    context[
                        "date"
                    ],

                "game_id":
                    str(game_id),

                "blue_team":
                    context[
                        "blue_team"
                    ],

                "red_team":
                    context[
                        "red_team"
                    ],

                "reason":
                    str(error)
            })


    games_df = pd.DataFrame(
        games
    )

    failed_df = pd.DataFrame(
        failed
    )


    if not games_df.empty:

        games_df = (

            games_df
            .sort_values(
                [
                    "date",
                    "game_id"
                ]
            )
            .reset_index(
                drop=True
            )
        )


    if not failed_df.empty:

        failed_df = (

            failed_df
            .sort_values(
                [
                    "year",
                    "date",
                    "game_id"
                ],

                na_position="last"
            )
            .reset_index(
                drop=True
            )
        )


    return (
        games_df,
        failed_df,
        lck
    )


# ============================================================
# 13. 팀 식별자
# ============================================================

def team_identity(
    row,
    side
):

    team_id = row[
        f"{side}_team_id"
    ]


    if (
        team_id is not None
        and not pd.isna(
            team_id
        )
    ):

        return str(
            team_id
        )


    return str(
        row[
            f"{side}_team"
        ]
    )


# ============================================================
# 14. BO3 / BO5 Series ID
# ============================================================

def assign_series_ids(
    games
):

    games = games.copy()


    games[
        "team_pair"
    ] = games.apply(

        lambda row:

        "|".join(
            sorted([
                team_identity(
                    row,
                    "blue"
                ),

                team_identity(
                    row,
                    "red"
                )
            ])
        ),

        axis=1
    )


    games[
        "series_id"
    ] = None


    # ========================================================
    # Oracle에 시리즈 ID가 있으면 우선 사용
    # ========================================================

    if (
        "source_series_id"
        in games.columns
    ):

        mask = (
            games[
                "source_series_id"
            ].notna()
        )


        games.loc[
            mask,
            "series_id"
        ] = (

            "OE_"

            + games.loc[
                mask,
                "source_series_id"
            ].astype(str)
        )


    # ========================================================
    # 없는 경우 직접 묶기
    # ========================================================

    for pair, group in (
        games.groupby(
            "team_pair",
            sort=False
        )
    ):

        group = (
            group.sort_values(
                [
                    "date",
                    "game_number"
                ]
            )
        )


        current_series_id = None
        previous_date = None
        previous_game_number = None

        series_count = 0


        for index, row in (
            group.iterrows()
        ):

            # Oracle Series ID 존재
            if pd.notna(
                games.at[
                    index,
                    "series_id"
                ]
            ):

                current_series_id = (
                    games.at[
                        index,
                        "series_id"
                    ]
                )

                previous_date = (
                    row["date"]
                )

                previous_game_number = (
                    row[
                        "game_number"
                    ]
                )

                continue


            new_series = False


            if (
                previous_game_number
                is None
            ):

                new_series = True


            elif (
                row[
                    "game_number"
                ]
                == 1
            ):

                new_series = True


            elif (
                row[
                    "game_number"
                ]
                <= previous_game_number
            ):

                new_series = True


            elif (
                previous_date
                is not None
                and pd.notna(
                    row["date"]
                )
            ):

                gap_hours = (

                    row["date"]
                    - previous_date

                ).total_seconds() / 3600


                if (
                    gap_hours
                    > MAX_SERIES_GAP_HOURS
                ):

                    new_series = True


            if new_series:

                series_count += 1


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


                date_text = (

                    row["date"]
                    .strftime(
                        "%Y%m%d"
                    )

                    if pd.notna(
                        row["date"]
                    )

                    else "unknown"
                )


                current_series_id = (

                    f"{row['year']}_"
                    f"{date_text}_"
                    f"{teams[0]}_vs_"
                    f"{teams[1]}_"
                    f"S{series_count}"
                )


            games.at[
                index,
                "series_id"
            ] = current_series_id


            previous_date = (
                row["date"]
            )

            previous_game_number = (
                row[
                    "game_number"
                ]
            )


    return games


# ============================================================
# 15. Fearless Draft
# ============================================================

def add_fearless_information(
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
            "series_id",
            sort=False
        )
    ):

        group = (
            group.sort_values(
                [
                    "game_number",
                    "date"
                ]
            )
        )


        previously_picked = []


        for index, game in (
            group.iterrows()
        ):

            fearless_active = (

                int(
                    game["year"]
                )

                in FEARLESS_YEARS
            )


            unavailable = (

                list(
                    previously_picked
                )

                if fearless_active

                else []
            )


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


            # =================================================
            # 현재 경기 Pick 10개
            #
            # NO_BAN은 여기와 아무 관계 없음
            # =================================================

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


            if (
                fearless_active
                and repeats
            ):

                games.at[
                    index,
                    "fearless_repeat_detected"
                ] = True


            # 다음 경기용 누적
            if fearless_active:

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
# 16. 팀 과거 승률 Feature
# ============================================================

def add_team_history(
    games
):

    games = (

        games.copy()
        .sort_values(
            [
                "date",
                "series_id",
                "game_number",
                "game_id"
            ]
        )
        .reset_index(
            drop=True
        )
    )


    # 전체
    overall = defaultdict(
        lambda: [0, 0]
    )

    # 시즌
    season = defaultdict(
        lambda: [0, 0]
    )

    # 진영
    side_stats = defaultdict(
        lambda: [0, 0]
    )

    # 패치
    patch_stats = defaultdict(
        lambda: [0, 0]
    )

    # 상대 전적
    h2h = defaultdict(
        lambda: [0, 0]
    )

    # 최근 10 경기
    recent_results = defaultdict(
        lambda: deque(
            maxlen=10
        )
    )


    for index, game in (
        games.iterrows()
    ):

        blue = team_identity(
            game,
            "blue"
        )

        red = team_identity(
            game,
            "red"
        )

        year = int(
            game["year"]
        )

        patch = (
            game["patch"]
        )


        # ====================================================
        # 현재 경기 이전 통계 계산
        # ====================================================

        for (
            prefix,
            team,
            opponent,
            side
        ) in [

            (
                "blue",
                blue,
                red,
                "BLUE"
            ),

            (
                "red",
                red,
                blue,
                "RED"
            )
        ]:

            # ------------------------------------------------
            # 전체
            # ------------------------------------------------

            total_games = (
                overall[
                    team
                ][0]
            )

            total_wins = (
                overall[
                    team
                ][1]
            )


            games.at[
                index,
                f"{prefix}_games_before"
            ] = total_games


            games.at[
                index,
                f"{prefix}_wins_before"
            ] = total_wins


            games.at[
                index,
                f"{prefix}_win_rate_before"
            ] = calculate_rate(
                total_wins,
                total_games
            )


            # ------------------------------------------------
            # 시즌
            # ------------------------------------------------

            (
                season_games,
                season_wins
            ) = season[
                (
                    team,
                    year
                )
            ]


            games.at[
                index,
                f"{prefix}_season_games_before"
            ] = season_games


            games.at[
                index,
                f"{prefix}_season_wins_before"
            ] = season_wins


            games.at[
                index,
                f"{prefix}_season_win_rate_before"
            ] = calculate_rate(
                season_wins,
                season_games
            )


            # ------------------------------------------------
            # 최근 5 / 10
            # ------------------------------------------------

            recent = list(
                recent_results[
                    team
                ]
            )


            last5 = recent[-5:]
            last10 = recent[-10:]


            games.at[
                index,
                f"{prefix}_last5_games"
            ] = len(
                last5
            )


            games.at[
                index,
                f"{prefix}_last5_win_rate"
            ] = (

                float(
                    np.mean(
                        last5
                    )
                )

                if last5

                else np.nan
            )


            games.at[
                index,
                f"{prefix}_last10_games"
            ] = len(
                last10
            )


            games.at[
                index,
                f"{prefix}_last10_win_rate"
            ] = (

                float(
                    np.mean(
                        last10
                    )
                )

                if last10

                else np.nan
            )


            # ------------------------------------------------
            # Side
            # ------------------------------------------------

            (
                side_games,
                side_wins
            ) = side_stats[
                (
                    team,
                    side
                )
            ]


            games.at[
                index,
                f"{prefix}_side_games_before"
            ] = side_games


            games.at[
                index,
                f"{prefix}_side_win_rate_before"
            ] = calculate_rate(
                side_wins,
                side_games
            )


            # ------------------------------------------------
            # Patch
            # ------------------------------------------------

            (
                patch_games,
                patch_wins
            ) = patch_stats[
                (
                    team,
                    patch
                )
            ]


            games.at[
                index,
                f"{prefix}_patch_games_before"
            ] = patch_games


            games.at[
                index,
                f"{prefix}_patch_win_rate_before"
            ] = calculate_rate(
                patch_wins,
                patch_games
            )


            # ------------------------------------------------
            # H2H
            # ------------------------------------------------

            (
                h2h_games,
                h2h_wins
            ) = h2h[
                (
                    team,
                    opponent
                )
            ]


            games.at[
                index,
                f"{prefix}_h2h_games_before"
            ] = h2h_games


            games.at[
                index,
                f"{prefix}_h2h_win_rate_before"
            ] = calculate_rate(
                h2h_wins,
                h2h_games
            )


        # ====================================================
        # 현재 경기 결과
        #
        # Feature를 만든 후 반영
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


        # 전체
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


        # 시즌
        season[
            (
                blue,
                year
            )
        ][0] += 1

        season[
            (
                blue,
                year
            )
        ][1] += blue_win


        season[
            (
                red,
                year
            )
        ][0] += 1

        season[
            (
                red,
                year
            )
        ][1] += red_win


        # 최근 경기
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


        # Side
        side_stats[
            (
                blue,
                "BLUE"
            )
        ][0] += 1

        side_stats[
            (
                blue,
                "BLUE"
            )
        ][1] += blue_win


        side_stats[
            (
                red,
                "RED"
            )
        ][0] += 1

        side_stats[
            (
                red,
                "RED"
            )
        ][1] += red_win


        # Patch
        patch_stats[
            (
                blue,
                patch
            )
        ][0] += 1

        patch_stats[
            (
                blue,
                patch
            )
        ][1] += blue_win


        patch_stats[
            (
                red,
                patch
            )
        ][0] += 1

        patch_stats[
            (
                red,
                patch
            )
        ][1] += red_win


        # H2H
        h2h[
            (
                blue,
                red
            )
        ][0] += 1

        h2h[
            (
                blue,
                red
            )
        ][1] += blue_win


        h2h[
            (
                red,
                blue
            )
        ][0] += 1

        h2h[
            (
                red,
                blue
            )
        ][1] += red_win


    return games


# ============================================================
# 17. 실제 20단계 밴픽 순서
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

        raise ValueError(
            "First Pick 오류"
        )


    actions = []


    def add(
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
    # 1차 BAN
    #
    # F S F S F S
    # ========================================================

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


    # ========================================================
    # 1차 PICK
    #
    # F1 S1 S2 F2 F3 S3
    # ========================================================

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


    # ========================================================
    # 2차 BAN
    #
    # S4 F4 S5 F5
    # ========================================================

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


    # ========================================================
    # 2차 PICK
    #
    # S4 F4 F5 S5
    # ========================================================

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


    # ========================================================
    # Order
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
# 18. 승률 Feature 목록
# ============================================================

HISTORY_COLUMNS = [

    "blue_games_before",
    "blue_wins_before",
    "blue_win_rate_before",

    "red_games_before",
    "red_wins_before",
    "red_win_rate_before",

    "blue_season_games_before",
    "blue_season_wins_before",
    "blue_season_win_rate_before",

    "red_season_games_before",
    "red_season_wins_before",
    "red_season_win_rate_before",

    "blue_last5_games",
    "blue_last5_win_rate",

    "red_last5_games",
    "red_last5_win_rate",

    "blue_last10_games",
    "blue_last10_win_rate",

    "red_last10_games",
    "red_last10_win_rate",

    "blue_side_games_before",
    "blue_side_win_rate_before",

    "red_side_games_before",
    "red_side_win_rate_before",

    "blue_patch_games_before",
    "blue_patch_win_rate_before",

    "red_patch_games_before",
    "red_patch_win_rate_before",

    "blue_h2h_games_before",
    "blue_h2h_win_rate_before",

    "red_h2h_games_before",
    "red_h2h_win_rate_before"
]


# ============================================================
# 19. Draft Action Dataset
# ============================================================

def build_actions(
    games
):

    rows = []


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

            row = {

                "series_id":
                    game[
                        "series_id"
                    ],

                "game_id":
                    game[
                        "game_id"
                    ],

                "game_number":
                    game[
                        "game_number"
                    ],

                "year":
                    game[
                        "year"
                    ],

                "date":
                    game[
                        "date"
                    ],

                "split":
                    game[
                        "split"
                    ],

                "playoffs":
                    game[
                        "playoffs"
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

                "order":
                    action[
                        "order"
                    ],

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
                    ],

                "fearless_unavailable_before_game":
                    game[
                        "fearless_unavailable_before_game"
                    ],

                "fearless_unavailable_count":
                    game[
                        "fearless_unavailable_count"
                    ],

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
                        action[
                            "side"
                        ]
                        == game[
                            "winner_side"
                        ]
                    )
            }


            for column in (
                HISTORY_COLUMNS
            ):

                row[column] = (
                    game[column]
                )


            rows.append(
                row
            )


    return pd.DataFrame(
        rows
    )


# ============================================================
# 20. Training Sample Dataset
#
# 실제 모델 학습은 하지 않고
# 학습하기 편한 형태의 CSV만 생성
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

        group = (
            group.sort_values(
                "order"
            )
        )


        draft_state = []


        for _, action in (
            group.iterrows()
        ):

            sample = {

                "series_id":
                    action[
                        "series_id"
                    ],

                "game_id":
                    game_id,

                "game_number":
                    action[
                        "game_number"
                    ],

                "year":
                    action[
                        "year"
                    ],

                "date":
                    action[
                        "date"
                    ],

                "split":
                    action[
                        "split"
                    ],

                "playoffs":
                    action[
                        "playoffs"
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

                "step":
                    action[
                        "order"
                    ],

                "draft_state":
                    json.dumps(
                        draft_state,
                        ensure_ascii=False
                    ),

                "fearless_unavailable":
                    action[
                        "fearless_unavailable_before_game"
                    ],

                "fearless_unavailable_count":
                    action[
                        "fearless_unavailable_count"
                    ],

                "next_phase":
                    action[
                        "phase"
                    ],

                "next_side":
                    action[
                        "side"
                    ],

                "next_action":
                    action[
                        "action"
                    ],

                # NO_BAN도 정상적인 target이 될 수 있음
                "target_champion":
                    action[
                        "champion"
                    ],

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
            }


            for column in (
                HISTORY_COLUMNS
            ):

                sample[column] = (
                    action[column]
                )


            samples.append(
                sample
            )


            draft_state.append({

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
# 21. Champion History
# ============================================================

def build_champion_history(
    games
):

    overall = defaultdict(
        lambda: [0, 0]
    )

    season = defaultdict(
        lambda: [0, 0]
    )

    patch_stats = defaultdict(
        lambda: [0, 0]
    )

    team_champion = defaultdict(
        lambda: [0, 0]
    )


    records = []


    games = (
        games.sort_values(
            [
                "date",
                "series_id",
                "game_number",
                "game_id"
            ]
        )
    )


    for _, game in (
        games.iterrows()
    ):

        updates = []


        for side in [
            "BLUE",
            "RED"
        ]:

            prefix = (
                side.lower()
            )


            team_key = (
                team_identity(
                    game,
                    prefix
                )
            )


            team_name = (
                game[
                    f"{prefix}_team"
                ]
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


                season_key = (
                    champion,
                    int(
                        game["year"]
                    )
                )

                patch_key = (
                    champion,
                    game["patch"]
                )

                team_champion_key = (
                    team_key,
                    champion
                )


                (
                    overall_games,
                    overall_wins
                ) = overall[
                    champion
                ]


                (
                    season_games,
                    season_wins
                ) = season[
                    season_key
                ]


                (
                    patch_games,
                    patch_wins
                ) = patch_stats[
                    patch_key
                ]


                (
                    team_games,
                    team_wins
                ) = team_champion[
                    team_champion_key
                ]


                records.append({

                    "series_id":
                        game[
                            "series_id"
                        ],

                    "game_id":
                        game[
                            "game_id"
                        ],

                    "game_number":
                        game[
                            "game_number"
                        ],

                    "year":
                        game[
                            "year"
                        ],

                    "date":
                        game[
                            "date"
                        ],

                    "patch":
                        game[
                            "patch"
                        ],

                    "side":
                        side,

                    "team":
                        team_name,

                    "champion":
                        champion,

                    "pick_index":
                        pick_index,

                    # 전체 챔피언 성적
                    "champion_games_before":
                        overall_games,

                    "champion_wins_before":
                        overall_wins,

                    "champion_win_rate_before":
                        calculate_rate(
                            overall_wins,
                            overall_games
                        ),

                    # 시즌 챔피언 성적
                    "champion_season_games_before":
                        season_games,

                    "champion_season_wins_before":
                        season_wins,

                    "champion_season_win_rate_before":
                        calculate_rate(
                            season_wins,
                            season_games
                        ),

                    # 패치 챔피언 성적
                    "champion_patch_games_before":
                        patch_games,

                    "champion_patch_wins_before":
                        patch_wins,

                    "champion_patch_win_rate_before":
                        calculate_rate(
                            patch_wins,
                            patch_games
                        ),

                    # 팀 + 챔피언
                    "team_champion_games_before":
                        team_games,

                    "team_champion_wins_before":
                        team_wins,

                    "team_champion_win_rate_before":
                        calculate_rate(
                            team_wins,
                            team_games
                        ),

                    # 결과 Label
                    "picked_side_won":
                        won
                })


                updates.append((

                    champion,
                    season_key,
                    patch_key,
                    team_champion_key,
                    won
                ))


        # ====================================================
        # 현재 경기 결과는 기록 후 반영
        # ====================================================

        for (
            champion,
            season_key,
            patch_key,
            team_champion_key,
            won
        ) in updates:

            overall[
                champion
            ][0] += 1

            overall[
                champion
            ][1] += won


            season[
                season_key
            ][0] += 1

            season[
                season_key
            ][1] += won


            patch_stats[
                patch_key
            ][0] += 1

            patch_stats[
                patch_key
            ][1] += won


            team_champion[
                team_champion_key
            ][0] += 1

            team_champion[
                team_champion_key
            ][1] += won


    return pd.DataFrame(
        records
    )


# ============================================================
# 22. Dataset 저장
# ============================================================

def save_datasets(
    games,
    actions,
    training,
    champion_history
):

    # ========================================================
    # 2025 + 2026 전체
    # ========================================================

    games.to_csv(

        PROCESSED_DIR
        / "lck_games_2025_2026.csv",

        index=False,

        encoding="utf-8-sig"
    )


    actions.to_csv(

        PROCESSED_DIR
        / "lck_draft_actions_2025_2026.csv",

        index=False,

        encoding="utf-8-sig"
    )


    training.to_csv(

        PROCESSED_DIR
        / "lck_training_samples_2025_2026.csv",

        index=False,

        encoding="utf-8-sig"
    )


    champion_history.to_csv(

        PROCESSED_DIR
        / "lck_champion_history_2025_2026.csv",

        index=False,

        encoding="utf-8-sig"
    )


    # ========================================================
    # 연도별 파일
    # ========================================================

    for year in TARGET_YEARS:

        games[
            games[
                "year"
            ]
            == year
        ].to_csv(

            PROCESSED_DIR
            / f"lck_games_{year}.csv",

            index=False,

            encoding="utf-8-sig"
        )


        actions[
            actions[
                "year"
            ]
            == year
        ].to_csv(

            PROCESSED_DIR
            / f"lck_draft_actions_{year}.csv",

            index=False,

            encoding="utf-8-sig"
        )


        training[
            training[
                "year"
            ]
            == year
        ].to_csv(

            PROCESSED_DIR
            / f"lck_training_samples_{year}.csv",

            index=False,

            encoding="utf-8-sig"
        )


# ============================================================
# 23. MAIN
# ============================================================

def main():

    print()
    print(
        "======================================"
    )

    print(
        "Oracle's Elixir LCK Dataset Builder"
    )

    print(
        "2025 Local + 2026 Auto Download"
    )

    print(
        "======================================"
    )


    # ========================================================
    # Oracle 파일 읽기
    # ========================================================

    (
        full_df,
        source_hashes
    ) = load_oracle_files()


    schema = (
        get_schema(
            full_df
        )
    )


    # ========================================================
    # 경기 Dataset
    # ========================================================

    (
        games,
        failed,
        raw_lck
    ) = build_base_games(
        full_df,
        schema
    )


    print()
    print(
        "LCK 경기 추출 완료"
    )


    print(
        "2025:",
        int(
            (
                games[
                    "year"
                ]
                == 2025
            ).sum()
        )
    )


    print(
        "2026:",
        int(
            (
                games[
                    "year"
                ]
                == 2026
            ).sum()
        )
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
    # Fearless
    # ========================================================

    games = (
        add_fearless_information(
            games
        )
    )


    # ========================================================
    # 과거 승률
    # ========================================================

    games = (
        add_team_history(
            games
        )
    )


    # ========================================================
    # Draft Action
    # ========================================================

    actions = (
        build_actions(
            games
        )
    )


    # ========================================================
    # Training Sample
    # ========================================================

    training = (
        build_training_samples(
            actions
        )
    )


    # ========================================================
    # Champion History
    # ========================================================

    champion_history = (
        build_champion_history(
            games
        )
    )


    # ========================================================
    # CSV 저장
    # ========================================================

    save_datasets(
        games,
        actions,
        training,
        champion_history
    )


    # ========================================================
    # Failed Games
    # ========================================================

    failed_path = (
        PROCESSED_DIR
        / "failed_games.csv"
    )


    if not failed.empty:

        failed.to_csv(

            failed_path,

            index=False,

            encoding="utf-8-sig"
        )


        print()
        print(
            "실패 경기 연도별:"
        )


        print(
            failed[
                "year"
            ]
            .value_counts(
                dropna=False
            )
            .sort_index()
        )


    elif failed_path.exists():

        # 이전 실행 실패 파일 제거
        failed_path.unlink()


    # ========================================================
    # NO_BAN 통계
    # ========================================================

    no_ban_count = int(
        (
            actions[
                "champion"
            ]
            == NO_BAN_TOKEN
        ).sum()
    )


    no_ban_games = int(
        actions[
            actions[
                "champion"
            ]
            == NO_BAN_TOKEN
        ][
            "game_id"
        ].nunique()
    )


    # ========================================================
    # Metadata
    # ========================================================

    metadata = {

        "processed_at":
            datetime.now().isoformat(),

        "source":
            "Oracle's Elixir",

        "league":
            TARGET_LEAGUE,

        "years":
            TARGET_YEARS,

        "2025_source":
            "local",

        "2026_source_google_drive_id":
            ORACLE_2026_FILE_ID,

        "source_sha256":
            source_hashes,

        "no_ban_token":
            NO_BAN_TOKEN,

        "raw_lck_rows":
            len(raw_lck),

        "games_total":
            len(games),

        "games_2025":
            int(
                (
                    games[
                        "year"
                    ]
                    == 2025
                ).sum()
            ),

        "games_2026":
            int(
                (
                    games[
                        "year"
                    ]
                    == 2026
                ).sum()
            ),

        "draft_actions":
            len(actions),

        "training_samples":
            len(training),

        "champion_history_rows":
            len(
                champion_history
            ),

        "no_ban_actions":
            no_ban_count,

        "games_with_no_ban":
            no_ban_games,

        "failed_games":
            len(failed),

        "failed_games_2025":
            (
                int(
                    (
                        failed[
                            "year"
                        ]
                        == 2025
                    ).sum()
                )

                if (
                    not failed.empty
                    and "year"
                    in failed.columns
                )

                else 0
            ),

        "failed_games_2026":
            (
                int(
                    (
                        failed[
                            "year"
                        ]
                        == 2026
                    ).sum()
                )

                if (
                    not failed.empty
                    and "year"
                    in failed.columns
                )

                else 0
            )
    }


    with open(

        PROCESSED_DIR
        / "dataset_metadata.json",

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
    # 완료 출력
    # ========================================================

    print()
    print(
        "======================================"
    )

    print(
        "데이터셋 생성 완료"
    )

    print(
        "======================================"
    )


    print(
        "전체 경기:",
        len(games)
    )


    print(
        "2025 경기:",
        int(
            (
                games[
                    "year"
                ]
                == 2025
            ).sum()
        )
    )


    print(
        "2026 경기:",
        int(
            (
                games[
                    "year"
                ]
                == 2026
            ).sum()
        )
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


    print()
    print(
        "Failed Games:",
        len(failed)
    )


    if not failed.empty:

        failed_2025 = int(
            (
                failed[
                    "year"
                ]
                == 2025
            ).sum()
        )

        failed_2026 = int(
            (
                failed[
                    "year"
                ]
                == 2026
            ).sum()
        )


        print(
            "  - 2025 실패:",
            failed_2025
        )


        print(
            "  - 2026 실패:",
            failed_2026
        )


    print()
    print(
        "생성 파일:"
    )


    print(
        "data/processed/lck_raw_2025_2026.csv"
    )

    print(
        "data/processed/lck_games_2025_2026.csv"
    )

    print(
        "data/processed/lck_games_2025.csv"
    )

    print(
        "data/processed/lck_games_2026.csv"
    )

    print(
        "data/processed/lck_draft_actions_2025_2026.csv"
    )

    print(
        "data/processed/lck_draft_actions_2025.csv"
    )

    print(
        "data/processed/lck_draft_actions_2026.csv"
    )

    print(
        "data/processed/lck_training_samples_2025_2026.csv"
    )

    print(
        "data/processed/lck_training_samples_2025.csv"
    )

    print(
        "data/processed/lck_training_samples_2026.csv"
    )

    print(
        "data/processed/lck_champion_history_2025_2026.csv"
    )


    if not failed.empty:

        print(
            "data/processed/failed_games.csv"
        )


if __name__ == "__main__":

    main()