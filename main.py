from datetime import datetime
# 今日の日付を取得
site_id = 44  # サイトID（固定）


today = datetime.now()
year = today.year
month = today.month
day = today.day
base_id = int(f"{year:04d}{site_id:02d}{month:02d}{day:02d}")
print(base_id)
