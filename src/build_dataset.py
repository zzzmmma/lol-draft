from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata

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

# Role 후보는 경기 이전 전체 챔피언 이력만 사용한다.
# 표본 부족은 [] (미확인)이며 최종 포지션으로 보충하지 않는다.
POSITIONS = ("top", "jng", "mid", "bot", "sup")
MIN_ROLE_GAMES = 3
MIN_ROLE_RATE = 0.10


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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data/raw"
ARCHIVE_DIR = PROJECT_ROOT / "data/raw_archive"
PROCESSED_DIR = PROJECT_ROOT / "data/processed"

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

def use_local_2026_or_raise(output_path, temp_path, error):

    # 실패한 다운로드 파일은 원본 교체에 사용하지 않는다.
    try:
        temp_path.unlink(missing_ok=True)
    except OSError as cleanup_error:
        print(
            f"[2026] 경고: 다운로드 임시 파일 정리 실패: {cleanup_error}"
        )

    if output_path.is_file():
        print(
            f"[2026] 경고: 최신 Oracle 데이터 다운로드/검증 실패: {error}"
        )
        print(
            f"[2026] 기존 로컬 CSV를 fallback으로 사용합니다: {output_path}"
        )
        return

    raise RuntimeError(
        "[2026] Oracle 데이터 다운로드/검증에 실패했고 "
        "기존 로컬 CSV도 없습니다.\n"
        f"로컬 CSV 확인 경로: {output_path}\n"
        f"실패 원인: {error}"
    ) from error


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

        use_local_2026_or_raise(output_path, temp_path, error)
        return


    if (
        result is None
        or not temp_path.exists()
    ):

        error = RuntimeError(
            "gdown이 다운로드 결과를 반환하지 않았거나 "
            "다운로드한 임시 파일이 없습니다."
        )
        use_local_2026_or_raise(output_path, temp_path, error)
        return


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

        use_local_2026_or_raise(output_path, temp_path, error)
        return


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


            # 분석/정답 전용 내부 값. process_dataset에서 기존 games와 분리한다.
            positions, role_error = extract_final_positions(game_rows, schema, record)
            record["_final_positions"] = positions
            record["_role_mapping_error"] = role_error

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
# 22. 입력 경기 기준 전체 파생 Dataset 생성
#
# 이 함수의 모든 누적 통계는 호출할 때마다 새로 시작한다.
# 따라서 2026 경기만 전달하면 2025 기록이 섞이지 않는다.
# ============================================================

ROLE_SOURCE_COLUMNS = ["_final_positions", "_role_mapping_error"]
ROLE_HISTORY_SCOPES = {
    "champion": "champion_total_position_games_before",
    "champion_patch": "champion_patch_position_games_before",
    "team_champion": "team_champion_position_games_before",
}
POSITION_HISTORY_COLUMNS = [
    "series_id", "game_id", "game_number", "year", "date", "patch",
    "side", "team", "champion", "pick_index", "final_position",
] + [
    column
    for prefix, total_column in ROLE_HISTORY_SCOPES.items()
    for column in (
        [f"{prefix}_{role}_games_before" for role in POSITIONS]
        + [total_column]
        + [f"{prefix}_{role}_rate_before" for role in POSITIONS]
    )
] + ["possible_roles_before", "possible_role_count_before", "is_flex_before"]
ROLE_FAILURE_COLUMNS = [
    "year", "date", "game_id", "blue_team", "red_team", "category", "reason",
]


def extract_final_positions(game_rows, schema, game):
    """Oracle 선수 행과 양 팀 Pick의 일대일 대응을 검증한다.

    실패한 경기 전체의 Role label/누적을 보류하지만 기존 Draft 데이터는 유지한다.
    """
    champion_column = find_column(game_rows, "champion")
    if champion_column is None:
        return {}, "필수 데이터 누락: Oracle champion 열 없음"

    players = game_rows[
        game_rows[schema["position"]].astype(str).str.strip().str.lower() != "team"
    ]
    if len(players) != 10:
        return {}, f"형식 불일치: 선수 행 {len(players)}개 (정상: 10개)"

    mapping = {"BLUE": {}, "RED": {}}
    role_counts = {side: defaultdict(int) for side in mapping}
    for _, player in players.iterrows():
        side = (clean_value(player[schema["side"]]) or "").upper()
        role = (clean_value(player[schema["position"]]) or "").lower()
        champion = clean_value(player[champion_column])
        team = clean_value(player[schema["teamname"]])
        if side not in mapping or role not in POSITIONS or not champion or not team:
            return {}, f"필수 데이터/형식 오류: side={side}, position={role}, champion={champion}, team={team}"
        if team != game[f"{side.lower()}_team"]:
            return {}, f"팀 불일치: {side} 선수 팀={team}"
        if champion in mapping[side]:
            return {}, f"챔피언 중복: {side} {champion}"
        mapping[side][champion] = role
        role_counts[side][role] += 1

    for side in mapping:
        if any(role_counts[side][role] != 1 for role in POSITIONS):
            return {}, f"포지션 구성 오류: {side} {dict(role_counts[side])}"
        picks = [game[f"{side.lower()}_pick{i}"] for i in range(1, 6)]
        if len(set(picks)) != 5 or set(picks) != set(mapping[side]):
            return {}, f"Pick/선수 챔피언 불일치: {side} picks={picks}, players={list(mapping[side])}"
    if len(set(mapping["BLUE"]) | set(mapping["RED"])) != 10:
        return {}, "챔피언 중복: 양 팀의 Pick 챔피언이 10종이 아님"
    return mapping, None


def position_snapshot(counts, prefix, total_column):
    total = sum(counts.values())
    snapshot = {total_column: total}
    for role in POSITIONS:
        snapshot[f"{prefix}_{role}_games_before"] = counts.get(role, 0)
        # 새 Role 비율은 표본이 없으면 0. 기존 calculate_rate 정책은 변경하지 않는다.
        snapshot[f"{prefix}_{role}_rate_before"] = counts.get(role, 0) / total if total else 0.0
    return snapshot


def build_champion_position_history(games, role_sources):
    if MIN_ROLE_GAMES < 1 or not 0 < MIN_ROLE_RATE <= 1:
        raise ValueError("MIN_ROLE_GAMES >= 1, 0 < MIN_ROLE_RATE <= 1 이어야 합니다.")
    histories = {scope: defaultdict(lambda: defaultdict(int)) for scope in ROLE_HISTORY_SCOPES}
    records, failures = [], []
    ordered = games.sort_values(["date", "series_id", "game_number", "game_id"])
    # 같은 시각의 경기끼리도 결과가 섞이지 않도록 모든 snapshot 후 누적한다.
    for date, batch in ordered.groupby("date", sort=False, dropna=False):
        updates = []
        for _, game in batch.iterrows():
            source = role_sources.get(game["game_id"], {})
            mapping = source.get("_final_positions", {})
            error = source.get("_role_mapping_error")
            if not mapping and not error:
                error = "필수 데이터 누락: Oracle 포지션 매칭 정보 없음"
            if pd.isna(date):
                error = error or "필수 데이터 누락: 경기 날짜 없음 (Role 이력 누적 불가)"
            if error:
                mapping = {}
                failures.append({
                    **{key: game[key] for key in ROLE_FAILURE_COLUMNS[:5]},
                    "category": "role_mapping_failure", "reason": error,
                })
            for side in ("BLUE", "RED"):
                prefix = side.lower()
                for pick_index in range(1, 6):
                    champion = game[f"{prefix}_pick{pick_index}"]
                    keys = {
                        "champion": champion,
                        "champion_patch": (champion, clean_value(game["patch"])),
                        "team_champion": (team_identity(game, prefix), champion),
                    }
                    final_position = mapping.get(side, {}).get(champion)
                    row = {
                        **{key: game[key] for key in POSITION_HISTORY_COLUMNS[:6]},
                        "side": side, "team": game[f"{prefix}_team"],
                        "champion": champion, "pick_index": pick_index,
                        "final_position": final_position,
                    }
                    for scope, total_column in ROLE_HISTORY_SCOPES.items():
                        counts = histories[scope][keys[scope]] if pd.notna(date) else {}
                        row.update(position_snapshot(counts, scope, total_column))
                    possible_roles = [
                        role for role in POSITIONS
                        if row[f"champion_{role}_games_before"] >= MIN_ROLE_GAMES
                        and row[f"champion_{role}_rate_before"] >= MIN_ROLE_RATE
                    ]
                    row.update({
                        "possible_roles_before": json.dumps(possible_roles),
                        "possible_role_count_before": len(possible_roles),
                        "is_flex_before": len(possible_roles) >= 2,
                    })
                    records.append(row)
                    if final_position is not None:
                        updates.append((keys, final_position))
        for keys, role in updates:
            for scope in ROLE_HISTORY_SCOPES:
                histories[scope][keys[scope]][role] += 1
    return (
        pd.DataFrame(records, columns=POSITION_HISTORY_COLUMNS),
        pd.DataFrame(failures, columns=ROLE_FAILURE_COLUMNS),
    )


def role_state_entry(row):
    """입력 Feature 허용 목록. final_position 및 다른 경기 결과는 포함하지 않는다."""
    return {
        "side": row["side"], "champion": row["champion"],
        "possible_roles": json.loads(row["possible_roles_before"]),
        "role_rates": {role: row[f"champion_{role}_rate_before"] for role in POSITIONS},
    }


def add_role_columns(actions, training, position_history):
    lookup = {
        (row["game_id"], row["side"], row["champion"]): row
        for row in position_history.to_dict("records")
    }
    # 새 label을 기존 draft_state 생성 로직에 전달하지 않는다.
    actions = actions.copy()
    training = training.copy()
    actions["picked_final_position"] = [
        lookup[(row.game_id, row.side, row.champion)]["final_position"]
        if row.action == "PICK" else None
        for row in actions.itertuples()
    ]
    training["target_position"] = [
        lookup[(row.game_id, row.next_side, row.target_champion)]["final_position"]
        if row.next_action == "PICK" else None
        for row in training.itertuples()
    ]
    states = {"BLUE": [], "RED": []}
    for row in training.itertuples():
        # draft_state는 현재 target을 제외한 실제 이전 Action만 포함한다.
        picked = {"BLUE": [], "RED": []}
        for action in json.loads(row.draft_state):
            if action["action"] == "PICK":
                key = (row.game_id, action["side"], action["champion"])
                picked[action["side"]].append(role_state_entry(lookup[key]))
        for side in states:
            states[side].append(json.dumps(picked[side], ensure_ascii=False, allow_nan=False))
    for side in states:
        training[f"{side.lower()}_role_state"] = states[side]
    return actions, training


def validate_role_dataset(dataset, role_sources):
    """Label 연결, 입력 상태 및 독립적인 날짜별 누적 계산으로 Role QA를 수행한다."""
    games = dataset["games"]
    history = dataset["champion_position_history"]
    failures = dataset["role_mapping_failures"]
    checks = {}
    failed_ids = set(failures["game_id"])
    valid = history[~history["game_id"].isin(failed_ids)]
    checks["ten_position_rows_per_game"] = (
        len(history) == 10 * len(games)
        and history.groupby("game_id").size().eq(10).all()
        and valid["final_position"].isin(POSITIONS).all()
    )
    checks["one_of_each_position_per_team"] = all(
        sorted(group["final_position"]) == sorted(POSITIONS)
        for _, group in valid.groupby(["game_id", "side"])
    )
    checks["mapping_failures_have_no_labels"] = history.loc[
        history["game_id"].isin(failed_ids), "final_position"
    ].isna().all()
    game_lookup = games.set_index("game_id").to_dict("index")
    checks["picks_match_position_rows"] = all(
        row.champion == game_lookup[row.game_id][f"{row.side.lower()}_pick{row.pick_index}"]
        for row in history.itertuples()
    )
    checks["oracle_player_mapping"] = all(
        row.final_position == role_sources[row.game_id]["_final_positions"][row.side][row.champion]
        for row in valid.itertuples()
    )

    # 빌더의 순차 카운터와 독립적으로 날짜별 관측값에서 다시 계산한다.
    audit = history.copy()
    audit["_team_key"] = [
        team_identity(game_lookup[row.game_id], row.side.lower()) for row in history.itertuples()
    ]
    audit["_patch_key"] = history["patch"].map(clean_value)
    group_keys = {
        "champion": ["champion"],
        "champion_patch": ["champion", "_patch_key"],
        "team_champion": ["_team_key", "champion"],
    }
    for scope, keys in group_keys.items():
        counts_ok, rates_ok = True, True
        expected_total = np.zeros(len(history), dtype=np.int64)
        for role in POSITIONS:
            observations = audit.assign(_played=audit["final_position"].eq(role).astype(int))
            dated = observations[observations["date"].notna()]
            daily = dated.groupby(keys + ["date"], dropna=False)["_played"].sum().reset_index()
            daily = daily.sort_values("date")
            daily["_before"] = daily.groupby(keys, dropna=False)["_played"].cumsum() - daily["_played"]
            expected = audit[keys + ["date"]].merge(
                daily[keys + ["date", "_before"]], on=keys + ["date"], how="left", validate="many_to_one",
            )["_before"].fillna(0).to_numpy(dtype=np.int64)
            expected_total += expected
            counts_ok = counts_ok and np.array_equal(history[f"{scope}_{role}_games_before"], expected)
        counts_ok = counts_ok and np.array_equal(history[ROLE_HISTORY_SCOPES[scope]], expected_total)
        for role in POSITIONS:
            expected_rates = np.divide(
                history[f"{scope}_{role}_games_before"].to_numpy(dtype=float), expected_total,
                out=np.zeros(len(history)), where=expected_total != 0,
            )
            rates_ok = rates_ok and np.allclose(history[f"{scope}_{role}_rate_before"], expected_rates)
        checks[f"{scope}_strictly_prior_counts"] = counts_ok
        checks[f"{scope}_rates"] = rates_ok

    checks["possible_roles_and_flex_thresholds"] = all(
        json.loads(row["possible_roles_before"]) == [
            role for role in POSITIONS
            if row[f"champion_{role}_games_before"] >= MIN_ROLE_GAMES
            and row[f"champion_{role}_rate_before"] >= MIN_ROLE_RATE
        ]
        and row["possible_role_count_before"] == len(json.loads(row["possible_roles_before"]))
        and row["is_flex_before"] == (row["possible_role_count_before"] >= 2)
        for row in history.to_dict("records")
    )
    first = history[history["date"] == history["date"].min()]
    count_columns = [column for column in history if column.endswith("_games_before")]
    checks["first_game_position_history_zero"] = first[count_columns].eq(0).all().all()

    # 중복 Pick 자체가 매칭 실패 원인인 경기도 기존 행을 보존하고 QA에 보고한다.
    lookup_keys = ["game_id", "side", "champion"]
    lookup = history.drop_duplicates(lookup_keys).set_index(lookup_keys).to_dict("index")
    labels_ok = True
    for row in dataset["actions"].itertuples():
        expected = lookup[(row.game_id, row.side, row.champion)]["final_position"] if row.action == "PICK" else None
        labels_ok = labels_ok and (
            pd.isna(row.picked_final_position) if pd.isna(expected) else row.picked_final_position == expected
        )
    checks["action_position_labels_pick_only"] = labels_ok
    labels_ok, states_ok = True, True
    for row in dataset["training"].itertuples():
        expected = lookup[(row.game_id, row.next_side, row.target_champion)]["final_position"] if row.next_action == "PICK" else None
        labels_ok = labels_ok and (pd.isna(row.target_position) if pd.isna(expected) else row.target_position == expected)
        prior = json.loads(row.draft_state)
        for side in ("BLUE", "RED"):
            actual = json.loads(getattr(row, f"{side.lower()}_role_state"))
            picks = [action for action in prior if action["action"] == "PICK" and action["side"] == side]
            expected_state = [
                role_state_entry({"side": side, "champion": action["champion"], **lookup[(row.game_id, side, action["champion"])]})
                for action in picks
            ]
            states_ok = states_ok and actual == expected_state and all(action["order"] < row.step for action in picks)
    checks["target_position_labels_pick_only"] = labels_ok
    checks["role_states_use_prior_history_and_prior_picks_only"] = states_ok
    checks = {key: bool(value) for key, value in checks.items()}
    return {
        "passed": all(checks.values()), "checks": checks,
        "games_checked": len(games), "mapped_games": len(games) - len(failures),
        "role_mapping_failures": len(failures),
        "role_mapping_failure_details": json.loads(failures.to_json(orient="records", date_format="iso")),
    }


def process_dataset(base_games):

    role_sources = {
        row["game_id"]: {key: row[key] for key in ROLE_SOURCE_COLUMNS if key in row}
        for row in base_games.to_dict("records")
    }

    games = assign_series_ids(
        base_games.drop(columns=ROLE_SOURCE_COLUMNS, errors="ignore").copy()
    )

    games = add_fearless_information(
        games
    )

    games = add_team_history(
        games
    )

    actions = build_actions(
        games
    )

    training = build_training_samples(
        actions
    )

    champion_history = build_champion_history(
        games
    )

    position_history, role_failures = build_champion_position_history(games, role_sources)
    actions, training = add_role_columns(actions, training, position_history)

    dataset = {
        "games": games,
        "actions": actions,
        "training": training,
        "champion_history": champion_history,
        "champion_position_history": position_history,
        "role_mapping_failures": role_failures,
    }
    dataset["role_qa"] = validate_role_dataset(dataset, role_sources)
    return dataset


# ============================================================
# 23. Dataset 저장
# ============================================================

DROP_PROCESSED_COLUMNS = [
    "source_url",
    "source_series_id",
]


def validate_output_component(name):
    """Windows/macOS에서 같은 파일명으로 저장되도록 검사하며 임의로 고치지 않는다."""
    invalid = [
        f"U+{ord(char):04X}" for char in name
        if char in '<>:"/\\|?*' or unicodedata.category(char) in ("Cc", "Cf")
    ]
    reserved = re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]", name.split(".")[0], re.IGNORECASE)
    if not name or name.endswith((" ", ".")) or invalid or reserved:
        raise ValueError(f"잘못된 저장 경로 구성요소: {name!r}; 잘못된 문자={invalid}")


def processed_output_paths(filenames):
    directory = Path(PROCESSED_DIR)
    # resolve() 전에 검사해 Windows가 끝 공백/점 등을 정규화하기 전에 발견한다.
    for part in directory.parts:
        if part != directory.anchor:
            validate_output_component(part)
    directory = directory.resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"processed 저장 폴더가 없거나 디렉터리가 아닙니다: {str(directory)!r}")

    paths = {}
    for key, filename in filenames.items():
        validate_output_component(filename)
        path = directory / filename
        if path.exists() and not path.is_file():
            raise IsADirectoryError(f"CSV/JSON 파일 위치에 디렉터리 또는 일반 파일이 아닌 항목이 있습니다: {str(path)!r}")
        paths[key] = path
    # Windows는 대소문자를 구분하지 않으므로 중복 저장 대상도 미리 검사한다.
    if len({str(path).casefold() for path in paths.values()}) != len(paths):
        raise ValueError(f"중복 저장 경로: {[str(path) for path in paths.values()]!r}")
    return paths


def write_processed_csv(frame, path):
    """같은 폴더의 임시 파일을 닫은 뒤 교체하여 저장 실패 시 기존 CSV를 보존한다."""
    path = Path(path)
    temp_path = None
    stage = "임시 파일 열기"
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="",
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as file:
            temp_path = Path(file.name)
            stage = "CSV 쓰기/파일 닫기"
            frame.to_csv(file, index=False)
        # Windows에서는 열린 임시 파일을 교체할 수 없으므로 반드시 with 밖에서 실행한다.
        stage = "기존 CSV 교체"
        os.replace(temp_path, path)
    except OSError as error:
        raise OSError(
            error.errno,
            f"CSV 저장 실패: stage={stage}; filename={path.name!r}; "
            f"path={str(path)!r}; path_length={len(str(path))}; "
            f"temporary_path={str(temp_path)!r}; winerror={getattr(error, 'winerror', None)}; "
            f"원인={error}",
            str(path),
        ) from error
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                print(f"경고: CSV 임시 파일 정리 실패: {str(temp_path)!r}; {cleanup_error}")


def save_dataset(
    dataset,
    output_suffix
):

    if not isinstance(output_suffix, str) or not re.fullmatch(r"[A-Za-z0-9_]+", output_suffix):
        raise ValueError(f"잘못된 output_suffix: {output_suffix!r}; 영문/숫자/밑줄만 허용합니다.")

    output_files = {
        "games": f"lck_games_{output_suffix}.csv",
        "actions": f"lck_draft_actions_{output_suffix}.csv",
        "training": f"lck_training_samples_{output_suffix}.csv",
        "champion_history": (
            f"lck_champion_history_{output_suffix}.csv"
        ),
        "champion_position_history": f"lck_champion_position_history_{output_suffix}.csv",
    }

    # 어떤 파일도 쓰기 전에 전체 저장 대상의 이름과 디렉터리 충돌을 확인한다.
    paths = processed_output_paths({
        **output_files,
        "role_qa": f"role_qa_{output_suffix}.json",
        "role_mapping_failures": f"role_mapping_failures_{output_suffix}.csv",
    })
    qa_path = paths["role_qa"]
    qa_path.write_text(
        json.dumps(dataset["role_qa"], ensure_ascii=False, indent=2), encoding="utf-8",
    )
    write_processed_csv(dataset["role_mapping_failures"], paths["role_mapping_failures"])
    if not dataset["role_qa"]["passed"]:
        raise ValueError(f"Role QA 실패: 데이터셋 저장 중단. 상세 결과: {qa_path}")

    for dataset_name, filename in output_files.items():

        # Series ID 등 파생 계산이 끝난 뒤 저장할 사본에서만 제외한다.
        output_df = dataset[dataset_name].drop(
            columns=DROP_PROCESSED_COLUMNS,
            errors="ignore"
        )

        write_processed_csv(output_df, paths[dataset_name])


def get_no_ban_statistics(actions):

    no_ban_actions = actions[
        actions["champion"] == NO_BAN_TOKEN
    ]

    return {
        "actions": len(no_ban_actions),
        "games": no_ban_actions["game_id"].nunique()
    }


# ============================================================
# 24. MAIN
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
    # 2025 + 2026 통합 Dataset
    # ========================================================

    combined_dataset = process_dataset(
        games.copy()
    )


    # ========================================================
    # 2026 완전 독립 Dataset
    #
    # 통합 Dataset을 필터링하지 않고, base games 단계에서
    # 2026 경기만 분리한 뒤 모든 파생 정보를 다시 계산한다.
    # ========================================================

    only_2026_games = games[
        games["year"] == 2026
    ].copy()

    only_2026_dataset = process_dataset(
        only_2026_games
    )


    # ========================================================
    # CSV 저장
    # ========================================================

    save_dataset(
        combined_dataset,
        "2025_2026"
    )

    save_dataset(
        only_2026_dataset,
        "2026_only"
    )


    combined_games = combined_dataset["games"]
    combined_actions = combined_dataset["actions"]
    combined_training = combined_dataset["training"]
    combined_champion_history = (
        combined_dataset["champion_history"]
    )

    only_2026_processed_games = only_2026_dataset["games"]
    only_2026_actions = only_2026_dataset["actions"]
    only_2026_training = only_2026_dataset["training"]
    only_2026_champion_history = (
        only_2026_dataset["champion_history"]
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

    combined_no_ban = get_no_ban_statistics(
        combined_actions
    )

    only_2026_no_ban = get_no_ban_statistics(
        only_2026_actions
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
            len(combined_games),

        "games_2025":
            int(
                (
                    combined_games[
                        "year"
                    ]
                    == 2025
                ).sum()
            ),

        "games_2026":
            int(
                (
                    combined_games[
                        "year"
                    ]
                    == 2026
                ).sum()
            ),

        "draft_actions":
            len(combined_actions),

        "training_samples":
            len(combined_training),

        "champion_history_rows":
            len(
                combined_champion_history
            ),

        "no_ban_actions":
            combined_no_ban["actions"],

        "games_with_no_ban":
            combined_no_ban["games"],

        "games_2026_only":
            len(only_2026_processed_games),

        "draft_actions_2026_only":
            len(only_2026_actions),

        "training_samples_2026_only":
            len(only_2026_training),

        "champion_history_rows_2026_only":
            len(only_2026_champion_history),

        "no_ban_actions_2026_only":
            only_2026_no_ban["actions"],

        "games_with_no_ban_2026_only":
            only_2026_no_ban["games"],

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


    role_statistics = {
        "champion_position_history_rows": len(combined_dataset["champion_position_history"]),
        "champion_position_history_rows_2026_only": len(only_2026_dataset["champion_position_history"]),
        "flex_pick_rows": int(combined_dataset["champion_position_history"]["is_flex_before"].sum()),
        "flex_pick_rows_2026_only": int(only_2026_dataset["champion_position_history"]["is_flex_before"].sum()),
        "role_mapping_failures": len(combined_dataset["role_mapping_failures"]),
    }
    metadata.update(role_statistics)
    metadata["role_mapping_failures_2026_only"] = len(only_2026_dataset["role_mapping_failures"])
    metadata["role_qa"] = {
        "2025_2026": combined_dataset["role_qa"],
        "2026_only": only_2026_dataset["role_qa"],
    }
    metadata["role_feature_policy"] = {
        "positions": list(POSITIONS),
        "min_role_games": MIN_ROLE_GAMES,
        "min_role_rate": MIN_ROLE_RATE,
        "possible_roles_source": "champion overall history strictly before game date",
        "no_history_rates": 0.0,
        "insufficient_history_possible_roles": [],
        "role_state_rates": "all five roles; no smoothing or final_position fallback",
        "role_state_timing": "before target action; candidates are historical priors, not forced lane assignments",
        "label_only_columns": ["final_position", "picked_final_position", "target_position"],
        "pick_index": "1-based pick slot within side, same as existing champion_history",
        "mapping_failure_policy": "retain existing draft rows; all game role labels null; skip role history update",
        "same_timestamp_policy": "snapshot all games before accumulating any of their positions",
        "independent_2026_only": True,
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


    print()
    print("[2025 + 2026 통합]")
    print("경기:", len(combined_games))
    print("Draft Actions:", len(combined_actions))
    print("Training Samples:", len(combined_training))
    print(
        "Champion History:",
        len(combined_champion_history)
    )

    print()
    print("[2026 독립]")
    print("경기:", len(only_2026_processed_games))
    print("Draft Actions:", len(only_2026_actions))
    print("Training Samples:", len(only_2026_training))
    print(
        "Champion History:",
        len(only_2026_champion_history)
    )


    print()
    print(
        "Failed Games:",
        len(failed)
    )

    print()
    print("[Role / Flex]")
    for key, value in role_statistics.items():
        print(f"{key}: {value}")
    print("Role QA: 통합/2026-only 모두 통과")
    if role_statistics["role_mapping_failures"]:
        print("경고: Role 매칭 실패 경기의 정답은 비어 있습니다. role_mapping_failures 파일을 확인하세요.")


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
        "data/processed/lck_draft_actions_2025_2026.csv"
    )

    print(
        "data/processed/lck_training_samples_2025_2026.csv"
    )

    print(
        "data/processed/lck_champion_history_2025_2026.csv"
    )

    print(
        "data/processed/lck_games_2026_only.csv"
    )

    print(
        "data/processed/lck_draft_actions_2026_only.csv"
    )

    print(
        "data/processed/lck_training_samples_2026_only.csv"
    )

    print(
        "data/processed/lck_champion_history_2026_only.csv"
    )

    for suffix in ("2025_2026", "2026_only"):
        print(f"data/processed/lck_champion_position_history_{suffix}.csv")
        print(f"data/processed/role_qa_{suffix}.json")
        print(f"data/processed/role_mapping_failures_{suffix}.csv")


    if not failed.empty:

        print(
            "data/processed/failed_games.csv"
        )


if __name__ == "__main__":

    main()
