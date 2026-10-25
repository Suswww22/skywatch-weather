"""
觀天氣象台：天氣資料爬蟲與資料處理

流程：
  1. 讀入地點清單（國家 → 縣市 → 行政區，含經緯度）
  2. 分批呼叫 Open-Meteo Forecast API（目前天氣、逐時、7 天）
  3. 分批呼叫 Open-Meteo Air Quality API（AQI、PM2.5、PM10、臭氧）
  4. 清理與整理：四捨五入、補缺值、計算 AQI 等級、壓縮成陣列格式
  5. 輸出 site/data/weather.json（給網頁用）與 site/data/weather_current.csv（給試算表用）
  6. 下載世界地圖輪廓 site/data/world-110m.json

只用 Python 標準函式庫，不需要 pip install。
執行：python weather_crawler.py
"""

import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).parent / "site" / "data"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
AIR_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
WORLD_MAP_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json"
BATCH_SIZE = 50  # Open-Meteo 一次請求可帶多組經緯度，分批避免網址過長

# ---------------------------------------------------------------------------
# 1. 地點清單：(中文名, 英文名, 緯度, 經度, 上層行政區)
# ---------------------------------------------------------------------------
COUNTRIES = [
    ("TW", "臺灣", "Taiwan", "Asia", [
        ("臺北市", "Taipei", 25.0375, 121.5637, ""),
        ("新北市", "New Taipei", 25.0117, 121.4627, ""),
        ("基隆市", "Keelung", 25.1283, 121.7419, ""),
        ("桃園市", "Taoyuan", 24.9936, 121.3010, ""),
        ("新竹市", "Hsinchu City", 24.8138, 120.9675, ""),
        ("新竹縣", "Hsinchu County", 24.8387, 121.0177, ""),
        ("苗栗縣", "Miaoli", 24.5602, 120.8214, ""),
        ("臺中市", "Taichung", 24.1477, 120.6736, ""),
        ("彰化縣", "Changhua", 24.0809, 120.5385, ""),
        ("南投縣", "Nantou", 23.9157, 120.6639, ""),
        ("雲林縣", "Yunlin", 23.7092, 120.5434, ""),
        ("嘉義市", "Chiayi City", 23.4801, 120.4491, ""),
        ("嘉義縣", "Chiayi County", 23.4590, 120.3330, ""),
        ("臺南市", "Tainan", 22.9999, 120.2270, ""),
        ("高雄市", "Kaohsiung", 22.6273, 120.3014, ""),
        ("屏東縣", "Pingtung", 22.6727, 120.4880, ""),
        ("宜蘭縣", "Yilan", 24.7570, 121.7533, ""),
        ("花蓮縣", "Hualien", 23.9871, 121.6015, ""),
        ("臺東縣", "Taitung", 22.7583, 121.1444, ""),
        ("澎湖縣", "Penghu", 23.5655, 119.5793, ""),
        ("金門縣", "Kinmen", 24.4321, 118.3171, ""),
        ("連江縣", "Lienchiang (Matsu)", 26.1597, 119.9497, ""),
        ("中正區", "Zhongzheng", 25.0324, 121.5199, "臺北市"),
        ("大同區", "Datong", 25.0634, 121.5130, "臺北市"),
        ("中山區", "Zhongshan", 25.0685, 121.5266, "臺北市"),
        ("松山區", "Songshan", 25.0500, 121.5770, "臺北市"),
        ("大安區", "Da'an", 25.0264, 121.5436, "臺北市"),
        ("萬華區", "Wanhua", 25.0287, 121.4977, "臺北市"),
        ("信義區", "Xinyi", 25.0330, 121.5654, "臺北市"),
        ("士林區", "Shilin", 25.0928, 121.5246, "臺北市"),
        ("北投區", "Beitou", 25.1322, 121.5017, "臺北市"),
        ("內湖區", "Neihu", 25.0693, 121.5884, "臺北市"),
        ("南港區", "Nangang", 25.0549, 121.6069, "臺北市"),
        ("文山區", "Wenshan", 24.9887, 121.5701, "臺北市"),
        ("淡水區", "Tamsui", 25.1695, 121.4407, "新北市"),
        ("三重區", "Sanchong", 25.0615, 121.4874, "新北市"),
        ("新店區", "Xindian", 24.9677, 121.5418, "新北市"),
        ("瑞芳區（九份）", "Ruifang (Jiufen)", 25.1090, 121.8440, "新北市"),
        ("西屯區", "Xitun", 24.1660, 120.6280, "臺中市"),
        ("左營區", "Zuoying", 22.6870, 120.2950, "高雄市"),
        ("鳳山區", "Fengshan", 22.6270, 120.3570, "高雄市"),
        ("阿里山", "Alishan", 23.5100, 120.8020, "嘉義縣"),
        ("合歡山", "Hehuanshan", 24.1390, 121.2710, "南投縣"),
        ("日月潭", "Sun Moon Lake", 23.8570, 120.9160, "南投縣"),
        ("墾丁", "Kenting", 21.9450, 120.7980, "屏東縣"),
    ]),
    ("JP", "日本", "Japan", "Asia", [
        ("東京", "Tokyo", 35.6762, 139.6503, "東京都"),
        ("大阪", "Osaka", 34.6937, 135.5023, "大阪府"),
        ("京都", "Kyoto", 35.0116, 135.7681, "京都府"),
        ("札幌", "Sapporo", 43.0618, 141.3545, "北海道"),
        ("福岡", "Fukuoka", 33.5904, 130.4017, "福岡縣"),
        ("名古屋", "Nagoya", 35.1815, 136.9066, "愛知縣"),
        ("那霸", "Naha", 26.2124, 127.6809, "沖繩縣"),
        ("仙台", "Sendai", 38.2682, 140.8694, "宮城縣"),
        ("廣島", "Hiroshima", 34.3853, 132.4553, "廣島縣"),
    ]),
    ("KR", "韓國", "South Korea", "Asia", [
        ("首爾", "Seoul", 37.5665, 126.9780, ""),
        ("釜山", "Busan", 35.1796, 129.0756, ""),
        ("仁川", "Incheon", 37.4563, 126.7052, ""),
        ("濟州", "Jeju", 33.4996, 126.5312, "濟州道"),
    ]),
    ("CN", "中國", "China", "Asia", [
        ("北京", "Beijing", 39.9042, 116.4074, ""),
        ("上海", "Shanghai", 31.2304, 121.4737, ""),
        ("廣州", "Guangzhou", 23.1291, 113.2644, "廣東省"),
        ("深圳", "Shenzhen", 22.5431, 114.0579, "廣東省"),
        ("成都", "Chengdu", 30.5728, 104.0668, "四川省"),
        ("重慶", "Chongqing", 29.5630, 106.5516, ""),
        ("西安", "Xi'an", 34.3416, 108.9398, "陝西省"),
        ("杭州", "Hangzhou", 30.2741, 120.1551, "浙江省"),
        ("廈門", "Xiamen", 24.4798, 118.0894, "福建省"),
        ("哈爾濱", "Harbin", 45.8038, 126.5349, "黑龍江省"),
        ("拉薩", "Lhasa", 29.6520, 91.1721, "西藏"),
        ("烏魯木齊", "Urumqi", 43.8256, 87.6168, "新疆"),
    ]),
    ("HK", "香港", "Hong Kong", "Asia", [
        ("香港", "Hong Kong", 22.3193, 114.1694, ""),
    ]),
    ("MO", "澳門", "Macau", "Asia", [
        ("澳門", "Macau", 22.1987, 113.5439, ""),
    ]),
    ("TH", "泰國", "Thailand", "Asia", [
        ("曼谷", "Bangkok", 13.7563, 100.5018, ""),
        ("清邁", "Chiang Mai", 18.7883, 98.9853, ""),
        ("普吉", "Phuket", 7.8804, 98.3923, ""),
    ]),
    ("SG", "新加坡", "Singapore", "Asia", [
        ("新加坡", "Singapore", 1.3521, 103.8198, ""),
    ]),
    ("MY", "馬來西亞", "Malaysia", "Asia", [
        ("吉隆坡", "Kuala Lumpur", 3.1390, 101.6869, ""),
        ("檳城", "Penang", 5.4141, 100.3288, ""),
    ]),
    ("VN", "越南", "Vietnam", "Asia", [
        ("河內", "Hanoi", 21.0278, 105.8342, ""),
        ("胡志明市", "Ho Chi Minh City", 10.8231, 106.6297, ""),
        ("峴港", "Da Nang", 16.0544, 108.2022, ""),
    ]),
    ("PH", "菲律賓", "Philippines", "Asia", [
        ("馬尼拉", "Manila", 14.5995, 120.9842, ""),
        ("宿霧", "Cebu", 10.3157, 123.8854, ""),
    ]),
    ("ID", "印尼", "Indonesia", "Asia", [
        ("雅加達", "Jakarta", -6.2088, 106.8456, ""),
        ("峇里島", "Bali (Denpasar)", -8.6705, 115.2126, ""),
    ]),
    ("IN", "印度", "India", "Asia", [
        ("新德里", "New Delhi", 28.6139, 77.2090, ""),
        ("孟買", "Mumbai", 19.0760, 72.8777, ""),
        ("班加羅爾", "Bengaluru", 12.9716, 77.5946, ""),
    ]),
    ("NP", "尼泊爾", "Nepal", "Asia", [
        ("加德滿都", "Kathmandu", 27.7172, 85.3240, ""),
    ]),
    ("AE", "阿聯", "United Arab Emirates", "Asia", [
        ("杜拜", "Dubai", 25.2048, 55.2708, ""),
    ]),
    ("SA", "沙烏地阿拉伯", "Saudi Arabia", "Asia", [
        ("利雅德", "Riyadh", 24.7136, 46.6753, ""),
    ]),
    ("TR", "土耳其", "Türkiye", "Europe", [
        ("伊斯坦堡", "Istanbul", 41.0082, 28.9784, ""),
    ]),
    ("GB", "英國", "United Kingdom", "Europe", [
        ("倫敦", "London", 51.5074, -0.1278, "英格蘭"),
        ("曼徹斯特", "Manchester", 53.4808, -2.2426, "英格蘭"),
        ("愛丁堡", "Edinburgh", 55.9533, -3.1883, "蘇格蘭"),
    ]),
    ("IE", "愛爾蘭", "Ireland", "Europe", [
        ("都柏林", "Dublin", 53.3498, -6.2603, ""),
    ]),
    ("FR", "法國", "France", "Europe", [
        ("巴黎", "Paris", 48.8566, 2.3522, ""),
        ("里昂", "Lyon", 45.7640, 4.8357, ""),
        ("尼斯", "Nice", 43.7102, 7.2620, ""),
    ]),
    ("DE", "德國", "Germany", "Europe", [
        ("柏林", "Berlin", 52.5200, 13.4050, ""),
        ("慕尼黑", "Munich", 48.1351, 11.5820, "巴伐利亞"),
        ("法蘭克福", "Frankfurt", 50.1109, 8.6821, "黑森"),
    ]),
    ("IT", "義大利", "Italy", "Europe", [
        ("羅馬", "Rome", 41.9028, 12.4964, ""),
        ("米蘭", "Milan", 45.4642, 9.1900, ""),
        ("威尼斯", "Venice", 45.4408, 12.3155, ""),
    ]),
    ("ES", "西班牙", "Spain", "Europe", [
        ("馬德里", "Madrid", 40.4168, -3.7038, ""),
        ("巴塞隆納", "Barcelona", 41.3874, 2.1686, "加泰隆尼亞"),
    ]),
    ("PT", "葡萄牙", "Portugal", "Europe", [
        ("里斯本", "Lisbon", 38.7223, -9.1393, ""),
    ]),
    ("NL", "荷蘭", "Netherlands", "Europe", [
        ("阿姆斯特丹", "Amsterdam", 52.3676, 4.9041, ""),
    ]),
    ("BE", "比利時", "Belgium", "Europe", [
        ("布魯塞爾", "Brussels", 50.8503, 4.3517, ""),
    ]),
    ("CH", "瑞士", "Switzerland", "Europe", [
        ("蘇黎世", "Zurich", 47.3769, 8.5417, ""),
    ]),
    ("AT", "奧地利", "Austria", "Europe", [
        ("維也納", "Vienna", 48.2082, 16.3738, ""),
    ]),
    ("CZ", "捷克", "Czechia", "Europe", [
        ("布拉格", "Prague", 50.0755, 14.4378, ""),
    ]),
    ("HU", "匈牙利", "Hungary", "Europe", [
        ("布達佩斯", "Budapest", 47.4979, 19.0402, ""),
    ]),
    ("PL", "波蘭", "Poland", "Europe", [
        ("華沙", "Warsaw", 52.2297, 21.0122, ""),
    ]),
    ("GR", "希臘", "Greece", "Europe", [
        ("雅典", "Athens", 37.9838, 23.7275, ""),
    ]),
    ("SE", "瑞典", "Sweden", "Europe", [
        ("斯德哥爾摩", "Stockholm", 59.3293, 18.0686, ""),
    ]),
    ("NO", "挪威", "Norway", "Europe", [
        ("奧斯陸", "Oslo", 59.9139, 10.7522, ""),
    ]),
    ("DK", "丹麥", "Denmark", "Europe", [
        ("哥本哈根", "Copenhagen", 55.6761, 12.5683, ""),
    ]),
    ("FI", "芬蘭", "Finland", "Europe", [
        ("赫爾辛基", "Helsinki", 60.1699, 24.9384, ""),
    ]),
    ("IS", "冰島", "Iceland", "Europe", [
        ("雷克雅維克", "Reykjavik", 64.1466, -21.9426, ""),
    ]),
    ("RU", "俄羅斯", "Russia", "Europe", [
        ("莫斯科", "Moscow", 55.7558, 37.6173, ""),
    ]),
    ("US", "美國", "United States", "North America", [
        ("紐約", "New York", 40.7128, -74.0060, "紐約州"),
        ("華盛頓", "Washington, D.C.", 38.9072, -77.0369, ""),
        ("波士頓", "Boston", 42.3601, -71.0589, "麻薩諸塞州"),
        ("芝加哥", "Chicago", 41.8781, -87.6298, "伊利諾州"),
        ("邁阿密", "Miami", 25.7617, -80.1918, "佛羅里達州"),
        ("休士頓", "Houston", 29.7604, -95.3698, "德州"),
        ("丹佛", "Denver", 39.7392, -104.9903, "科羅拉多州"),
        ("拉斯維加斯", "Las Vegas", 36.1699, -115.1398, "內華達州"),
        ("洛杉磯", "Los Angeles", 34.0522, -118.2437, "加州"),
        ("舊金山", "San Francisco", 37.7749, -122.4194, "加州"),
        ("西雅圖", "Seattle", 47.6062, -122.3321, "華盛頓州"),
        ("安克拉治", "Anchorage", 61.2181, -149.9003, "阿拉斯加州"),
        ("檀香山", "Honolulu", 21.3069, -157.8583, "夏威夷州"),
    ]),
    ("CA", "加拿大", "Canada", "North America", [
        ("多倫多", "Toronto", 43.6532, -79.3832, "安大略省"),
        ("蒙特婁", "Montreal", 45.5017, -73.5673, "魁北克省"),
        ("溫哥華", "Vancouver", 49.2827, -123.1207, "卑詩省"),
        ("卡加利", "Calgary", 51.0447, -114.0719, "亞伯達省"),
    ]),
    ("MX", "墨西哥", "Mexico", "North America", [
        ("墨西哥市", "Mexico City", 19.4326, -99.1332, ""),
        ("坎昆", "Cancún", 21.1619, -86.8515, ""),
    ]),
    ("BR", "巴西", "Brazil", "South America", [
        ("聖保羅", "São Paulo", -23.5505, -46.6333, ""),
        ("里約熱內盧", "Rio de Janeiro", -22.9068, -43.1729, ""),
    ]),
    ("AR", "阿根廷", "Argentina", "South America", [
        ("布宜諾斯艾利斯", "Buenos Aires", -34.6037, -58.3816, ""),
    ]),
    ("PE", "秘魯", "Peru", "South America", [
        ("利馬", "Lima", -12.0464, -77.0428, ""),
    ]),
    ("CL", "智利", "Chile", "South America", [
        ("聖地牙哥", "Santiago", -33.4489, -70.6693, ""),
    ]),
    ("CO", "哥倫比亞", "Colombia", "South America", [
        ("波哥大", "Bogotá", 4.7110, -74.0721, ""),
    ]),
    ("EG", "埃及", "Egypt", "Africa", [
        ("開羅", "Cairo", 30.0444, 31.2357, ""),
    ]),
    ("MA", "摩洛哥", "Morocco", "Africa", [
        ("馬拉喀什", "Marrakesh", 31.6295, -7.9811, ""),
    ]),
    ("KE", "肯亞", "Kenya", "Africa", [
        ("奈洛比", "Nairobi", -1.2921, 36.8219, ""),
    ]),
    ("NG", "奈及利亞", "Nigeria", "Africa", [
        ("拉哥斯", "Lagos", 6.5244, 3.3792, ""),
    ]),
    ("ZA", "南非", "South Africa", "Africa", [
        ("約翰尼斯堡", "Johannesburg", -26.2041, 28.0473, ""),
        ("開普敦", "Cape Town", -33.9249, 18.4241, ""),
    ]),
    ("AU", "澳洲", "Australia", "Oceania", [
        ("雪梨", "Sydney", -33.8688, 151.2093, "新南威爾斯州"),
        ("墨爾本", "Melbourne", -37.8136, 144.9631, "維多利亞州"),
        ("布里斯本", "Brisbane", -27.4698, 153.0251, "昆士蘭州"),
        ("伯斯", "Perth", -31.9505, 115.8605, "西澳"),
    ]),
    ("NZ", "紐西蘭", "New Zealand", "Oceania", [
        ("奧克蘭", "Auckland", -36.8485, 174.7633, ""),
        ("皇后鎮", "Queenstown", -45.0312, 168.6626, ""),
    ]),
]

CURRENT_VARS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]
HOURLY_VARS = ["temperature_2m", "precipitation_probability", "weather_code", "is_day", "uv_index"]
DAILY_VARS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "precipitation_probability_max", "precipitation_sum",
    "sunrise", "sunset", "uv_index_max", "wind_speed_10m_max",
]
AIR_VARS = ["us_aqi", "pm2_5", "pm10", "ozone", "nitrogen_dioxide"]


# ---------------------------------------------------------------------------
# 2. 網路請求（含重試）
# ---------------------------------------------------------------------------
def get_json(url, params=None, retries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params, safe=",")
    req = urllib.request.Request(url, headers={"User-Agent": "skywatch-student-project/1.0"})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as err:  # 網路不穩或被限流時，等一下再試
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  請求失敗（{err}），{wait} 秒後重試…")
            time.sleep(wait)


def batched(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_batch(api, places, extra):
    params = {
        "latitude": ",".join(str(p["lat"]) for p in places),
        "longitude": ",".join(str(p["lon"]) for p in places),
        "timezone": "auto",
        **extra,
    }
    data = get_json(api, params)
    return data if isinstance(data, list) else [data]  # 只有一個地點時回傳的是物件


# ---------------------------------------------------------------------------
# 3. 資料清理工具
# ---------------------------------------------------------------------------
def r1(v):
    return None if v is None else round(v, 1)


def ri(v):
    return None if v is None else int(round(v))


def aqi_level(aqi):
    """依美國 EPA 標準把 AQI 數值轉成等級。"""
    if aqi is None:
        return None
    for limit, label in [(50, "良好"), (100, "普通"), (150, "對敏感族群不健康"),
                         (200, "對所有族群不健康"), (300, "非常不健康")]:
        if aqi <= limit:
            return label
    return "危害"


def build_place_list():
    places = []
    for code, zh, en, region, cities in COUNTRIES:
        for name, name_en, lat, lon, admin in cities:
            places.append({
                "id": f"{code}-{name_en.lower().replace(' ', '-').replace('(', '').replace(')', '')}",
                "name": name, "nameEn": name_en, "admin": admin,
                "cc": code, "country": zh, "countryEn": en, "region": region,
                "lat": lat, "lon": lon,
            })
    return places


def process_forecast(raw):
    cur, hr, dy = raw["current"], raw["hourly"], raw["daily"]
    return {
        "tz": raw["timezone"],
        "tzAbbr": raw["timezone_abbreviation"],
        "utcOffset": raw["utc_offset_seconds"],
        "elevation": raw.get("elevation"),
        "current": {
            "time": cur["time"],
            "temp": r1(cur["temperature_2m"]),
            "feels": r1(cur["apparent_temperature"]),
            "rh": ri(cur["relative_humidity_2m"]),
            "isDay": cur["is_day"],
            "precip": r1(cur["precipitation"]),
            "code": cur["weather_code"],
            "cloud": ri(cur["cloud_cover"]),
            "pressure": ri(cur["pressure_msl"]),
            "wind": r1(cur["wind_speed_10m"]),
            "windDir": ri(cur["wind_direction_10m"]),
            "gust": r1(cur["wind_gusts_10m"]),
        },
        # 逐時資料只存起始時間與數值陣列，網頁再依「現在時間」切出未來 48 小時
        "hourly": {
            "start": hr["time"][0],
            "temp": [r1(v) for v in hr["temperature_2m"]],
            "pop": [ri(v) for v in hr["precipitation_probability"]],
            "code": hr["weather_code"],
            "isDay": hr["is_day"],
            "uv": [r1(v) for v in hr["uv_index"]],
        },
        "daily": {
            "date": dy["time"],
            "code": dy["weather_code"],
            "max": [r1(v) for v in dy["temperature_2m_max"]],
            "min": [r1(v) for v in dy["temperature_2m_min"]],
            "pop": [ri(v) for v in dy["precipitation_probability_max"]],
            "rain": [r1(v) for v in dy["precipitation_sum"]],
            "sunrise": [s[-5:] for s in dy["sunrise"]],
            "sunset": [s[-5:] for s in dy["sunset"]],
            "uvMax": [r1(v) for v in dy["uv_index_max"]],
            "windMax": [r1(v) for v in dy["wind_speed_10m_max"]],
        },
    }


def process_air(raw):
    cur = raw.get("current") or {}
    aqi = ri(cur.get("us_aqi"))
    return {
        "aqi": aqi,
        "level": aqi_level(aqi),
        "pm25": r1(cur.get("pm2_5")),
        "pm10": r1(cur.get("pm10")),
        "o3": r1(cur.get("ozone")),
        "no2": r1(cur.get("nitrogen_dioxide")),
    }


# ---------------------------------------------------------------------------
# 4. 主流程
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    places = build_place_list()
    print(f"共 {len(places)} 個地點，{len(COUNTRIES)} 個國家／地區")

    results = []
    for n, batch in enumerate(batched(places, BATCH_SIZE), 1):
        print(f"[第 {n} 批] 抓取 {len(batch)} 個地點的天氣預報…")
        forecasts = fetch_batch(FORECAST_API, batch, {
            "current": ",".join(CURRENT_VARS),
            "hourly": ",".join(HOURLY_VARS),
            "daily": ",".join(DAILY_VARS),
            "forecast_days": 7,
            "wind_speed_unit": "kmh",
        })
        print(f"[第 {n} 批] 抓取空氣品質…")
        try:
            airs = fetch_batch(AIR_API, batch, {"current": ",".join(AIR_VARS)})
        except Exception as err:
            print(f"  空氣品質抓取失敗，這批先略過：{err}")
            airs = [{}] * len(batch)

        for place, fc, air in zip(batch, forecasts, airs):
            try:
                results.append({**place, **process_forecast(fc), "air": process_air(air)})
            except (KeyError, TypeError, IndexError) as err:
                print(f"  {place['name']} 資料格式異常，略過：{err}")
        time.sleep(1)  # 對免費 API 客氣一點

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generatedAt": generated,
        "source": "Open-Meteo.com (CC BY 4.0)",
        "count": len(results),
        "cities": results,
    }
    (OUT_DIR / "weather.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 給試算表看的扁平 CSV：一列一個地點的目前天氣
    with open(OUT_DIR / "weather_current.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["國家", "上層行政區", "地點", "緯度", "經度", "時區", "觀測時間",
                    "氣溫°C", "體感°C", "濕度%", "風速km/h", "天氣代碼", "AQI", "AQI等級", "PM2.5"])
        for c in results:
            cur, air = c["current"], c["air"]
            w.writerow([c["country"], c["admin"], c["name"], c["lat"], c["lon"], c["tz"], cur["time"],
                        cur["temp"], cur["feels"], cur["rh"], cur["wind"], cur["code"],
                        air["aqi"], air["level"], air["pm25"]])

    world = OUT_DIR / "world-110m.json"
    if not world.exists():
        print("下載世界地圖輪廓…")
        req = urllib.request.Request(WORLD_MAP_URL, headers={"User-Agent": "skywatch-student-project/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            world.write_bytes(resp.read())

    size_kb = (OUT_DIR / "weather.json").stat().st_size / 1024
    print(f"完成：{len(results)} 個地點，weather.json {size_kb:.0f} KB，資料時間 {generated}")


if __name__ == "__main__":
    main()
