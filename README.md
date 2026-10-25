# 觀天氣象台

全球 53 個國家／地區、159 個地點的天氣現況與預報網頁，台灣細到行政區。
資料由 Python 爬蟲透過 Open-Meteo API 取得，經整理後由 GitHub Actions 每小時自動更新並部署到 GitHub Pages。

## 功能

- **選擇地點**：搜尋框（中英文）、國家 → 城市／行政區下拉選單、地圖點選（自動找最近的觀測點）
- **框選範圍**：在地圖上拖曳出矩形，統計範圍內的平均、最高、最低氣溫與降雨機率
- **即時時鐘**：同時顯示所選地點的當地時間與使用者的時間，並計算時差
- **目前天氣**：氣溫、體感、濕度、風向風速、陣風、氣壓、雲量
- **空氣品質**：AQI（美國 EPA 標準）、PM2.5、PM10、臭氧、紫外線、日出日落
- **預報**：未來 48 小時逐時溫度與降雨機率圖、7 天預報

## 架構

```
Open-Meteo API ──► weather_crawler.py ──► site/data/weather.json ──► site/index.html
 (天氣、空品)        (抓取、清理、整理)         (整理後的資料)              (d3.js 繪圖)
                          ▲
              GitHub Actions 每小時執行
```

| 檔案 | 說明 |
| --- | --- |
| `weather_crawler.py` | 爬蟲與資料處理，只用 Python 標準函式庫 |
| `site/index.html` | 網頁本體（HTML、CSS、JavaScript 都在同一個檔案） |
| `site/data/world-110m.json` | 世界地圖輪廓（TopoJSON） |
| `.github/workflows/update-weather.yml` | 每小時執行爬蟲並部署網頁 |

## 資料處理流程

1. **API 串接**：Open-Meteo 支援一次查詢多個經緯度，159 個地點每 50 個一批，共 4 批。
2. **容錯**：請求失敗時以 2、4 秒間隔重試；單一地點格式異常就略過，不中斷整批。
3. **清理**：數值四捨五入、AQI 換算等級、日出日落只保留「時:分」、逐時資料壓縮成陣列。
4. **輸出**：`weather.json` 給網頁使用，`weather_current.csv` 方便用試算表檢視。
5. **前端時間對齊**：網頁依各地時區的「現在」切出未來 48 小時，資料放了一段時間，時間軸仍正確。

## 在自己電腦上執行

```bash
python weather_crawler.py
python -m http.server 8000 --directory site
```

然後用瀏覽器開啟 http://localhost:8000 。直接雙擊 `index.html` 會因為瀏覽器限制讀不到 JSON。

## 新增地點

在 `weather_crawler.py` 的 `COUNTRIES` 清單加入 `(中文名, 英文名, 緯度, 經度, 上層行政區)`，重新執行即可。

## 已知限制

- 相鄰行政區可能落在氣象模式的同一個網格內，數值會相同或非常接近。
- 公開儲存庫若 60 天沒有任何提交，GitHub 會自動停用排程，需到 Actions 頁面重新啟用。

## 資料來源

天氣與空氣品質資料：[Open-Meteo.com](https://open-meteo.com/)（[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)）
地圖輪廓：[world-atlas](https://github.com/topojson/world-atlas)（Natural Earth，公有領域）
