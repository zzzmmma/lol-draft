import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import re
import time
from urllib.parse import urljoin


# ============================================================
# 기본 설정
# ============================================================

BASE_URL = "https://gol.gg"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# 크롤링할 대회
TOURNAMENT_URLS = [
    "https://gol.gg/tournament/tournament-matchlist/LCK%202026%20Season%20Playoffs/"
]

# 사이트에 너무 빠르게 요청하지 않도록 대기
REQUEST_DELAY = 1


# ============================================================
# 1. HTML 요청
# ============================================================

def get_soup(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


# ============================================================
# 2. Game ID 추출
# ============================================================

def extract_game_id(url):

    match = re.search(
        r"/game/stats/(\d+)/",
        url
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# 3. 대회 페이지에서 시리즈 링크 수집
# ============================================================

def get_series_urls(tournament_url):

    print()
    print("대회 페이지 확인:")
    print(tournament_url)

    soup = get_soup(tournament_url)

    series_urls = []

    for a in soup.find_all("a", href=True):

        href = a["href"]

        # Gol.gg Match List에서
        # page-summary 링크를 찾음
        if (
            "/game/stats/" in href
            and "page-summary" in href
        ):

            full_url = urljoin(
                tournament_url,
                href
            )

            series_urls.append(
                full_url
            )

    # 중복 제거
    series_urls = list(
        dict.fromkeys(series_urls)
    )

    print(
        "찾은 시리즈 수:",
        len(series_urls)
    )

    return series_urls


# ============================================================
# 4. 시리즈 Summary에서 개별 경기 URL 찾기
# ============================================================

def get_game_urls(series_url):

    print()
    print("시리즈 확인:")
    print(series_url)

    soup = get_soup(series_url)

    game_ids = []

    # 페이지 안에 등장하는 모든
    # /game/stats/숫자/ 링크 확인
    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a["href"]

        game_id = extract_game_id(
            href
        )

        if game_id:
            game_ids.append(
                game_id
            )

    # 현재 summary URL의 ID도 추가
    current_id = extract_game_id(
        series_url
    )

    if current_id:
        game_ids.append(
            current_id
        )

    # 중복 제거
    game_ids = list(
        dict.fromkeys(game_ids)
    )

    game_urls = []

    for game_id in game_ids:

        game_url = (
            f"{BASE_URL}/game/stats/"
            f"{game_id}/page-game/"
        )

        game_urls.append(
            game_url
        )

    print(
        "후보 경기 수:",
        len(game_urls)
    )

    return game_urls


# ============================================================
# 5. 팀 이름 / 승패
# ============================================================

def get_team_info(
    soup,
    selector
):

    header = soup.select_one(
        selector
    )

    if header is None:
        return None, None

    team_tag = header.select_one(
        "a"
    )

    if team_tag:

        team_name = (
            team_tag.get_text(
                strip=True
            )
        )

    else:

        team_name = None

    header_text = (
        header.get_text(
            " ",
            strip=True
        )
    )

    if "WIN" in header_text:

        result = "WIN"

    elif "LOSS" in header_text:

        result = "LOSS"

    else:

        result = None

    return (
        team_name,
        result
    )


# ============================================================
# 6. Gol.gg의 | 묶음 저장
# ============================================================

def parse_champion_groups(
    content
):

    html = (
        content.decode_contents()
    )

    parts = html.split("|")

    groups = []

    for part in parts:

        part_soup = BeautifulSoup(
            part,
            "html.parser"
        )

        champions = []

        for img in (
            part_soup.select("img")
        ):

            champion_name = (
                img.get("alt")
            )

            if champion_name:

                champions.append(
                    champion_name
                )

        if champions:

            groups.append(
                champions
            )

    return groups


# ============================================================
# 7. Bans / Picks 추출
# ============================================================

def get_draft_rows(
    soup,
    label_name
):

    results = []

    for row in soup.select(
        "div.row"
    ):

        # 현재 row 바로 아래만 탐색
        label = row.find(
            "div",
            class_="col-2",
            recursive=False
        )

        content = row.find(
            "div",
            class_="col-10",
            recursive=False
        )

        if (
            label is None
            or content is None
        ):
            continue

        label_text = (
            label.get_text(
                " ",
                strip=True
            )
        )

        if not label_text.startswith(
            label_name
        ):
            continue

        champions = []

        for img in (
            content.select("img")
        ):

            champion_name = (
                img.get("alt")
            )

            if champion_name:

                champions.append(
                    champion_name
                )

        groups = (
            parse_champion_groups(
                content
            )
        )

        # First Pick 이미지 확인
        first_pick_img = (
            label.find(
                "img",
                alt="First Pick"
            )
        )

        is_first_pick = (
            first_pick_img
            is not None
        )

        results.append({

            "champions":
                champions,

            "groups":
                groups,

            "first_pick":
                is_first_pick
        })

    return results


# ============================================================
# 8. 안전하게 리스트 값 가져오기
# ============================================================

def get_champion(
    champions,
    index
):

    if index < len(
        champions
    ):

        return champions[index]

    return None


# ============================================================
# 9. 실제 전체 밴픽 순서 복원
# ============================================================

def reconstruct_draft_actions(
    blue_bans,
    red_bans,
    blue_picks,
    red_picks,
    first_pick_side
):

    actions = []

    # --------------------------------------------------------
    # First Pick 팀 설정
    # --------------------------------------------------------

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


    # ========================================================
    # 1차 밴
    #
    # First → Second
    # First → Second
    # First → Second
    # ========================================================

    for i in range(3):

        if i < len(first_bans):

            actions.append({
                "phase":
                    "BAN_PHASE_1",

                "side":
                    first_side,

                "action":
                    "BAN",

                "champion":
                    first_bans[i]
            })

        if i < len(second_bans):

            actions.append({
                "phase":
                    "BAN_PHASE_1",

                "side":
                    second_side,

                "action":
                    "BAN",

                "champion":
                    second_bans[i]
            })


    # ========================================================
    # 1차 픽
    #
    # First
    # Second Second
    # First First
    # Second
    # ========================================================

    if len(first_picks) > 0:

        actions.append({
            "phase":
                "PICK_PHASE_1",

            "side":
                first_side,

            "action":
                "PICK",

            "champion":
                first_picks[0]
        })


    for i in [0, 1]:

        if i < len(
            second_picks
        ):

            actions.append({
                "phase":
                    "PICK_PHASE_1",

                "side":
                    second_side,

                "action":
                    "PICK",

                "champion":
                    second_picks[i]
            })


    for i in [1, 2]:

        if i < len(
            first_picks
        ):

            actions.append({
                "phase":
                    "PICK_PHASE_1",

                "side":
                    first_side,

                "action":
                    "PICK",

                "champion":
                    first_picks[i]
            })


    if len(second_picks) > 2:

        actions.append({
            "phase":
                "PICK_PHASE_1",

            "side":
                second_side,

            "action":
                "PICK",

            "champion":
                second_picks[2]
        })


    # ========================================================
    # 2차 밴
    #
    # Second → First
    # Second → First
    # ========================================================

    for i in [3, 4]:

        if i < len(
            second_bans
        ):

            actions.append({
                "phase":
                    "BAN_PHASE_2",

                "side":
                    second_side,

                "action":
                    "BAN",

                "champion":
                    second_bans[i]
            })

        if i < len(
            first_bans
        ):

            actions.append({
                "phase":
                    "BAN_PHASE_2",

                "side":
                    first_side,

                "action":
                    "BAN",

                "champion":
                    first_bans[i]
            })


    # ========================================================
    # 2차 픽
    #
    # Second
    # First First
    # Second
    # ========================================================

    if len(second_picks) > 3:

        actions.append({
            "phase":
                "PICK_PHASE_2",

            "side":
                second_side,

            "action":
                "PICK",

            "champion":
                second_picks[3]
        })


    for i in [3, 4]:

        if i < len(
            first_picks
        ):

            actions.append({
                "phase":
                    "PICK_PHASE_2",

                "side":
                    first_side,

                "action":
                    "PICK",

                "champion":
                    first_picks[i]
            })


    if len(second_picks) > 4:

        actions.append({
            "phase":
                "PICK_PHASE_2",

            "side":
                second_side,

            "action":
                "PICK",

            "champion":
                second_picks[4]
        })


    # 순서 번호
    for i, action in enumerate(
        actions,
        start=1
    ):

        action["order"] = i

    return actions


# ============================================================
# 10. 개별 경기 크롤링
# ============================================================

def crawl_gol_game(
    url,
    tournament_url=None,
    series_id=None,
    game_number=None
):

    soup = get_soup(url)

    game_id = extract_game_id(
        url
    )

    # --------------------------------------------------------
    # 팀
    # --------------------------------------------------------

    blue_team, blue_result = (
        get_team_info(
            soup,
            ".blue-line-header"
        )
    )

    red_team, red_result = (
        get_team_info(
            soup,
            ".red-line-header"
        )
    )

    # 실제 경기 페이지가 아니면 제외
    if (
        blue_team is None
        or red_team is None
    ):

        raise ValueError(
            "경기 데이터를 찾을 수 없음"
        )


    # --------------------------------------------------------
    # 밴
    # --------------------------------------------------------

    ban_rows = get_draft_rows(
        soup,
        "Bans"
    )

    if len(ban_rows) >= 1:

        blue_bans = (
            ban_rows[0]["champions"]
        )

        blue_ban_groups = (
            ban_rows[0]["groups"]
        )

    else:

        blue_bans = []
        blue_ban_groups = []


    if len(ban_rows) >= 2:

        red_bans = (
            ban_rows[1]["champions"]
        )

        red_ban_groups = (
            ban_rows[1]["groups"]
        )

    else:

        red_bans = []
        red_ban_groups = []


    # --------------------------------------------------------
    # 픽
    # --------------------------------------------------------

    pick_rows = get_draft_rows(
        soup,
        "Picks"
    )

    if len(pick_rows) >= 1:

        blue_picks = (
            pick_rows[0]["champions"]
        )

        blue_pick_groups = (
            pick_rows[0]["groups"]
        )

        blue_first_pick = (
            pick_rows[0]["first_pick"]
        )

    else:

        blue_picks = []
        blue_pick_groups = []
        blue_first_pick = False


    if len(pick_rows) >= 2:

        red_picks = (
            pick_rows[1]["champions"]
        )

        red_pick_groups = (
            pick_rows[1]["groups"]
        )

        red_first_pick = (
            pick_rows[1]["first_pick"]
        )

    else:

        red_picks = []
        red_pick_groups = []
        red_first_pick = False


    # --------------------------------------------------------
    # First Pick
    # --------------------------------------------------------

    if blue_first_pick:

        first_pick_side = "BLUE"

    elif red_first_pick:

        first_pick_side = "RED"

    else:

        first_pick_side = None


    # --------------------------------------------------------
    # 데이터 검증
    # --------------------------------------------------------

    if len(blue_bans) != 5:
        print(
            f"경고: {game_id} "
            f"Blue Ban {len(blue_bans)}개"
        )

    if len(red_bans) != 5:
        print(
            f"경고: {game_id} "
            f"Red Ban {len(red_bans)}개"
        )

    if len(blue_picks) != 5:
        print(
            f"경고: {game_id} "
            f"Blue Pick {len(blue_picks)}개"
        )

    if len(red_picks) != 5:
        print(
            f"경고: {game_id} "
            f"Red Pick {len(red_picks)}개"
        )


    # --------------------------------------------------------
    # 경기 데이터
    # --------------------------------------------------------

    game_data = {

        "game_id":
            game_id,

        "series_id":
            series_id,

        "game_number":
            game_number,

        "url":
            url,

        "tournament_url":
            tournament_url,

        "blue_team":
            blue_team,

        "blue_result":
            blue_result,

        "red_team":
            red_team,

        "red_result":
            red_result,

        "first_pick_side":
            first_pick_side,


        # BLUE BANS
        "blue_ban1":
            get_champion(
                blue_bans, 0
            ),

        "blue_ban2":
            get_champion(
                blue_bans, 1
            ),

        "blue_ban3":
            get_champion(
                blue_bans, 2
            ),

        "blue_ban4":
            get_champion(
                blue_bans, 3
            ),

        "blue_ban5":
            get_champion(
                blue_bans, 4
            ),


        # RED BANS
        "red_ban1":
            get_champion(
                red_bans, 0
            ),

        "red_ban2":
            get_champion(
                red_bans, 1
            ),

        "red_ban3":
            get_champion(
                red_bans, 2
            ),

        "red_ban4":
            get_champion(
                red_bans, 3
            ),

        "red_ban5":
            get_champion(
                red_bans, 4
            ),


        # BLUE PICKS
        "blue_pick1":
            get_champion(
                blue_picks, 0
            ),

        "blue_pick2":
            get_champion(
                blue_picks, 1
            ),

        "blue_pick3":
            get_champion(
                blue_picks, 2
            ),

        "blue_pick4":
            get_champion(
                blue_picks, 3
            ),

        "blue_pick5":
            get_champion(
                blue_picks, 4
            ),


        # RED PICKS
        "red_pick1":
            get_champion(
                red_picks, 0
            ),

        "red_pick2":
            get_champion(
                red_picks, 1
            ),

        "red_pick3":
            get_champion(
                red_picks, 2
            ),

        "red_pick4":
            get_champion(
                red_picks, 3
            ),

        "red_pick5":
            get_champion(
                red_picks, 4
            ),


        # Gol.gg 원본 | 묶음
        "blue_ban_groups":
            json.dumps(
                blue_ban_groups,
                ensure_ascii=False
            ),

        "red_ban_groups":
            json.dumps(
                red_ban_groups,
                ensure_ascii=False
            ),

        "blue_pick_groups":
            json.dumps(
                blue_pick_groups,
                ensure_ascii=False
            ),

        "red_pick_groups":
            json.dumps(
                red_pick_groups,
                ensure_ascii=False
            )
    }


    # --------------------------------------------------------
    # 실제 밴픽 순서
    # --------------------------------------------------------

    draft_actions = (
        reconstruct_draft_actions(
            blue_bans,
            red_bans,
            blue_picks,
            red_picks,
            first_pick_side
        )
    )


    # Action마다 게임 정보 추가
    for action in draft_actions:

        action["game_id"] = (
            game_id
        )

        action["series_id"] = (
            series_id
        )

        action["game_number"] = (
            game_number
        )


    return (
        game_data,
        draft_actions
    )


# ============================================================
# 11. 전체 대회 크롤링
# ============================================================

def crawl_tournaments(
    tournament_urls
):

    all_games = []
    all_actions = []

    failed_urls = []

    visited_game_ids = set()


    for tournament_url in (
        tournament_urls
    ):

        print()
        print(
            "======================================"
        )

        print(
            "대회 시작"
        )

        print(
            tournament_url
        )

        print(
            "======================================"
        )


        # ----------------------------------------------------
        # 시리즈 URL
        # ----------------------------------------------------

        series_urls = (
            get_series_urls(
                tournament_url
            )
        )


        for series_index, series_url in enumerate(
            series_urls,
            start=1
        ):

            series_id = (
                extract_game_id(
                    series_url
                )
            )

            try:

                game_urls = (
                    get_game_urls(
                        series_url
                    )
                )

            except Exception as e:

                print(
                    "시리즈 실패:",
                    series_url,
                    e
                )

                continue


            # ------------------------------------------------
            # 개별 게임
            # ------------------------------------------------

            game_number = 1

            for game_url in game_urls:

                game_id = (
                    extract_game_id(
                        game_url
                    )
                )

                # 이미 수집한 경기면 제외
                if game_id in (
                    visited_game_ids
                ):
                    continue


                print()
                print(
                    f"크롤링 중: "
                    f"{game_url}"
                )


                try:

                    game_data, actions = (
                        crawl_gol_game(
                            game_url,
                            tournament_url,
                            series_id,
                            game_number
                        )
                    )


                    # 정상적인 밴픽인지 확인
                    if len(actions) != 20:

                        print(
                            f"경고: "
                            f"{game_id} "
                            f"밴픽 액션 "
                            f"{len(actions)}개"
                        )


                    all_games.append(
                        game_data
                    )

                    all_actions.extend(
                        actions
                    )

                    visited_game_ids.add(
                        game_id
                    )


                    print(
                        f"완료: "
                        f"{game_id}"
                    )

                    print(
                        game_data[
                            "blue_team"
                        ],
                        "vs",
                        game_data[
                            "red_team"
                        ]
                    )


                    game_number += 1


                except Exception as e:

                    print(
                        "실패:",
                        game_url
                    )

                    print(
                        "이유:",
                        e
                    )

                    failed_urls.append(
                        game_url
                    )


                # 요청 간격
                time.sleep(
                    REQUEST_DELAY
                )


    return (
        all_games,
        all_actions,
        failed_urls
    )


# ============================================================
# 12. 프로그램 실행
# ============================================================

if __name__ == "__main__":


    print(
        "LCK 크롤링 시작"
    )


    games, actions, failed = (
        crawl_tournaments(
            TOURNAMENT_URLS
        )
    )


    # ========================================================
    # games.csv
    # ========================================================

    if games:

        games_df = pd.DataFrame(
            games
        )

        games_df.to_csv(
            "lck_games.csv",
            index=False,
            encoding="utf-8-sig"
        )


    # ========================================================
    # draft_actions.csv
    # ========================================================

    if actions:

        actions_df = pd.DataFrame(
            actions
        )

        actions_df = actions_df[
            [
                "game_id",
                "series_id",
                "game_number",
                "order",
                "phase",
                "side",
                "action",
                "champion"
            ]
        ]

        actions_df.to_csv(
            "lck_draft_actions.csv",
            index=False,
            encoding="utf-8-sig"
        )


    # ========================================================
    # 실패 URL
    # ========================================================

    if failed:

        failed_df = pd.DataFrame({
            "url": failed
        })

        failed_df.to_csv(
            "failed_urls.csv",
            index=False,
            encoding="utf-8-sig"
        )


    # ========================================================
    # 결과
    # ========================================================

    print()
    print(
        "======================================"
    )

    print(
        "크롤링 종료"
    )

    print(
        "======================================"
    )

    print(
        "수집 경기:",
        len(games)
    )

    print(
        "밴픽 Action:",
        len(actions)
    )

    print(
        "실패 URL:",
        len(failed)
    )

    print()

    print(
        "생성 파일:"
    )

    print(
        "lck_games.csv"
    )

    print(
        "lck_draft_actions.csv"
    )

    if failed:
        print(
            "failed_urls.csv"
        )