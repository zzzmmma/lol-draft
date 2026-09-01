import requests
from bs4 import BeautifulSoup
import pandas as pd


# ==================================================
# 팀 이름 / 승패 가져오기
# ==================================================

def get_team_info(soup, selector):
    header = soup.select_one(selector)

    if header is None:
        return None, None

    # 팀 이름
    team_tag = header.select_one("a")

    if team_tag:
        team_name = team_tag.get_text(strip=True)
    else:
        team_name = None

    # WIN / LOSS
    header_text = header.get_text(" ", strip=True)

    if "WIN" in header_text:
        result = "WIN"

    elif "LOSS" in header_text:
        result = "LOSS"

    else:
        result = None

    return team_name, result


# ==================================================
# Bans / Picks 가져오기
# ==================================================

def get_draft_rows(soup, label_name):
    results = []

    # 모든 row 확인
    for row in soup.select("div.row"):

        # 중요:
        # 현재 row의 '바로 아래 자식'만 확인
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

        # Bans/Picks row가 아니면 넘어감
        if label is None or content is None:
            continue

        label_text = label.get_text(
            " ",
            strip=True
        )

        # 원하는 행인지 확인
        if not label_text.startswith(label_name):
            continue

        # ------------------------------------------
        # 챔피언 이름
        # ------------------------------------------

        champions = []

        for img in content.select("img"):

            champion_name = img.get("alt")

            if champion_name:
                champions.append(champion_name)

        # ------------------------------------------
        # First Pick 확인
        # ------------------------------------------

        first_pick_img = label.find(
            "img",
            alt="First Pick"
        )

        if first_pick_img is not None:
            is_first_pick = True
        else:
            is_first_pick = False

        results.append({
            "champions": champions,
            "first_pick": is_first_pick
        })

    return results


# ==================================================
# 리스트에서 챔피언 안전하게 꺼내기
# ==================================================

def get_champion(champions, index):

    if len(champions) > index:
        return champions[index]

    return None


# ==================================================
# Gol.gg 경기 크롤링
# ==================================================

def crawl_gol_game(url):

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=10
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # ==================================================
    # 팀 정보
    # ==================================================

    blue_team, blue_result = get_team_info(
        soup,
        ".blue-line-header"
    )

    red_team, red_result = get_team_info(
        soup,
        ".red-line-header"
    )

    # ==================================================
    # 밴
    # ==================================================

    ban_rows = get_draft_rows(
        soup,
        "Bans"
    )

    if len(ban_rows) >= 1:
        blue_bans = ban_rows[0]["champions"]
    else:
        blue_bans = []

    if len(ban_rows) >= 2:
        red_bans = ban_rows[1]["champions"]
    else:
        red_bans = []

    # ==================================================
    # 픽
    # ==================================================

    pick_rows = get_draft_rows(
        soup,
        "Picks"
    )

    if len(pick_rows) >= 1:

        blue_picks = pick_rows[0]["champions"]

        blue_first_pick = (
            pick_rows[0]["first_pick"]
        )

    else:

        blue_picks = []
        blue_first_pick = False


    if len(pick_rows) >= 2:

        red_picks = pick_rows[1]["champions"]

        red_first_pick = (
            pick_rows[1]["first_pick"]
        )

    else:

        red_picks = []
        red_first_pick = False


    # ==================================================
    # First Pick 진영
    # ==================================================

    if blue_first_pick:

        first_pick_side = "BLUE"

    elif red_first_pick:

        first_pick_side = "RED"

    else:

        first_pick_side = None


    # ==================================================
    # 데이터 저장
    # ==================================================

    data = {

        "url": url,

        # 팀
        "blue_team": blue_team,
        "blue_result": blue_result,

        "red_team": red_team,
        "red_result": red_result,

        # First Pick
        "first_pick_side": first_pick_side,

        # ------------------
        # BLUE BANS
        # ------------------

        "blue_ban1": get_champion(
            blue_bans, 0
        ),

        "blue_ban2": get_champion(
            blue_bans, 1
        ),

        "blue_ban3": get_champion(
            blue_bans, 2
        ),

        "blue_ban4": get_champion(
            blue_bans, 3
        ),

        "blue_ban5": get_champion(
            blue_bans, 4
        ),

        # ------------------
        # RED BANS
        # ------------------

        "red_ban1": get_champion(
            red_bans, 0
        ),

        "red_ban2": get_champion(
            red_bans, 1
        ),

        "red_ban3": get_champion(
            red_bans, 2
        ),

        "red_ban4": get_champion(
            red_bans, 3
        ),

        "red_ban5": get_champion(
            red_bans, 4
        ),

        # ------------------
        # BLUE PICKS
        # ------------------

        "blue_pick1": get_champion(
            blue_picks, 0
        ),

        "blue_pick2": get_champion(
            blue_picks, 1
        ),

        "blue_pick3": get_champion(
            blue_picks, 2
        ),

        "blue_pick4": get_champion(
            blue_picks, 3
        ),

        "blue_pick5": get_champion(
            blue_picks, 4
        ),

        # ------------------
        # RED PICKS
        # ------------------

        "red_pick1": get_champion(
            red_picks, 0
        ),

        "red_pick2": get_champion(
            red_picks, 1
        ),

        "red_pick3": get_champion(
            red_picks, 2
        ),

        "red_pick4": get_champion(
            red_picks, 3
        ),

        "red_pick5": get_champion(
            red_picks, 4
        ),
    }

    return data


# ==================================================
# 프로그램 실행
# ==================================================

if __name__ == "__main__":

    url = (
        "https://gol.gg/game/stats/"
        "82383/page-game/"
    )

    game_data = crawl_gol_game(url)


    # ==================================================
    # 결과 출력
    # ==================================================

    print()
    print("==============================")
    print("GAME INFO")
    print("==============================")

    print(
        "Blue Team   :",
        game_data["blue_team"]
    )

    print(
        "Blue Result :",
        game_data["blue_result"]
    )

    print(
        "Red Team    :",
        game_data["red_team"]
    )

    print(
        "Red Result  :",
        game_data["red_result"]
    )


    print()
    print("==============================")
    print("FIRST PICK")
    print("==============================")

    print(
        "First Pick Side:",
        game_data["first_pick_side"]
    )


    print()
    print("==============================")
    print("BANS")
    print("==============================")

    print(
        "Blue Bans:",
        [
            game_data["blue_ban1"],
            game_data["blue_ban2"],
            game_data["blue_ban3"],
            game_data["blue_ban4"],
            game_data["blue_ban5"],
        ]
    )

    print(
        "Red Bans :",
        [
            game_data["red_ban1"],
            game_data["red_ban2"],
            game_data["red_ban3"],
            game_data["red_ban4"],
            game_data["red_ban5"],
        ]
    )


    print()
    print("==============================")
    print("PICKS")
    print("==============================")

    print(
        "Blue Picks:",
        [
            game_data["blue_pick1"],
            game_data["blue_pick2"],
            game_data["blue_pick3"],
            game_data["blue_pick4"],
            game_data["blue_pick5"],
        ]
    )

    print(
        "Red Picks :",
        [
            game_data["red_pick1"],
            game_data["red_pick2"],
            game_data["red_pick3"],
            game_data["red_pick4"],
            game_data["red_pick5"],
        ]
    )


    # ==================================================
    # CSV 저장
    # ==================================================

    df = pd.DataFrame(
        [game_data]
    )

    df.to_csv(
        "gol_game_82383.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("==============================")
    print("CSV 저장 완료")
    print("==============================")

    print("gol_game_82383.csv")