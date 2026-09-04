# lol-draft
lck_Law.csv
    원본 파일 보존

lck_games
    경기당 1행
    game_id, series_id, game_number, year, date, patch
    blue_team, red_team
    first_pick_side
    blue_result, red_result, winner_side, winner_team
    blue_ban1~5, red_ban1~5
    blue_pick1~5, red_pick1~5
    fearless_unavailable_before_game, fearless_unavailable_count
    팀 전체 승률, 이번 시즌 승률, 최근 5/10 경기 승률, 진영 승률, 해당 패치 승률, 맞대결 승률

lck_draft_action
    series_id, game_id, game_number(몇 경기), year, date, patch
    blue_team, red_team
    order
    phase
    side
    action
    champion
    fearless_unavailable_before_game
    winner_side, winner_team
    acting_side_won
    승률

lck_training_samples
    밴픽 상태, 다음 행동

lck_champion_history
    픽한 챔피언과 관련된 과거 데이터들 정리

failed_games
    처리가 불가능한 데이터들 정리

