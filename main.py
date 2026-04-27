import requests
from bs4 import BeautifulSoup

# URL
url = "https://nar.netkeiba.com/odds/index.html?race_id=202546042901&rf=race_submenu"
urlx = "https://nar.netkeiba.com/race/shutuba_past.html?race_id=202546042901&rf=shutuba_submenu"

# ヘッダー設定
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

# オッズページ取得
res = requests.get(url, headers=headers)
res.encoding = res.apparent_encoding
soup = BeautifulSoup(res.text, "html.parser")

# 馬ごとの行を取得
rows = soup.select("table.RaceOdds_HorseList_Table tr")[1:]  # ヘッダー行は除く

# 馬名と複勝オッズのリスト作成
horse_list = []
for row in rows:
    horse_name_tag = row.select_one("td.Horse_Name a")
    odds_tags = row.select("td.Odds span.Odds")

    if horse_name_tag and len(odds_tags) == 2:
        horse_name = horse_name_tag.text.strip()
        fukusho_odds = odds_tags[1].text.strip()  # 2番目が複勝オッズ

        horse_list.append({
            "name": horse_name,
            "fukusho_odds": fukusho_odds
        })

# -------------------------
# ここから過去レース順位を取りに行く
# -------------------------

# 過去レースページ取得
res_x = requests.get(urlx, headers=headers)
res_x.encoding = res_x.apparent_encoding
soup_x = BeautifulSoup(res_x.text, "html.parser")

# 過去レース情報を取得
past_horse_blocks = soup_x.select('tr.HorseList')

for idx, horse_block in enumerate(past_horse_blocks):
    ranks = []
    past_td_list = horse_block.select('td.Past')
    for past_td in past_td_list:
        if len(ranks) >= 5:
            break  # 5レースまで
        data_item = past_td.select_one('div.Data_Item')
        if data_item:
            num_span = data_item.select_one('div.Data01 span.Num')
            if num_span:
                rank = num_span.text.strip()
                ranks.append(rank)
    if idx < len(horse_list):
        horse_list[idx]["past_ranks"] = ranks
# -------------------------
# 結果表示
# -------------------------

print("\n馬名と複勝オッズ＋過去レース順位：")
for horse in horse_list:
    name = horse["name"]
    fukusho = horse["fukusho_odds"]
    past = horse.get("past_ranks", [])
    print(f"{name}: 複勝オッズ={fukusho}, 過去レース順位={past}")
