import streamlit as st
import pandas as pd
# numpy は現在未使用（K-Means廃止により）
import re
import math
import folium
import googlemaps
import polyline
import requests
import xml.etree.ElementTree as ET
import unicodedata
from streamlit_folium import st_folium
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from datetime import datetime, timedelta
# K-Meansクラスタリングは廃止（Global TSP & Time Slicing 方式に変更）

# ========================================
# ページ設定（最初に配置する必要あり）
# ========================================
st.set_page_config(
    page_title="環境整備スケジュール作成システム",
    page_icon="🏗️",
    layout="wide"
)

# ========================================
# カスタムCSS（モダンUI）
# ========================================
st.markdown("""
<style>
    /* 全体のフォントと背景 */
    .stApp {
        font-family: 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif;
        background-color: #f8f9fa;
    }

    /* ヘッダーの装飾 */
    h1 {
        color: #2c3e50;
        border-bottom: 3px solid #4CAF50;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }

    h2, h3 {
        color: #34495e;
    }

    /* カード風のコンテナスタイル */
    .stMetric {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    /* エキスパンダー（アコーディオン）のスタイル */
    .streamlit-expanderHeader {
        background-color: #ffffff;
        border-radius: 8px;
        font-weight: bold;
        font-size: 1.1em;
    }

    /* ボタンのスタイル */
    .stButton>button {
        border-radius: 25px;
        font-weight: bold;
        padding: 10px 25px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        transition: all 0.3s ease;
    }

    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }

    /* サイドバーの背景 */
    [data-testid="stSidebar"] {
        background-color: #e9ecef;
    }

    /* 成功メッセージ */
    .stSuccess {
        border-radius: 10px;
    }

    /* 警告メッセージ */
    .stWarning {
        border-radius: 10px;
    }

    /* データフレームのスタイル */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
    }

    /* マルチセレクトのドロップダウンを常に下方向に表示（スマホ対応） */
    [data-baseweb="popover"] {
        top: 100% !important;
        bottom: auto !important;
    }

    /* ドロップダウンリストの最大高さを制限してスクロール可能に */
    [data-baseweb="menu"] {
        max-height: 300px !important;
        overflow-y: auto !important;
    }
</style>
""", unsafe_allow_html=True)

# ========================================
# 定数定義
# ========================================

# API設定（Streamlit Secretsから取得）
DEFAULT_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "")
DEFAULT_MAP_ID = st.secrets.get("GOOGLE_MAP_ID", "")

# 稼働時間設定（固定）
WORK_HOURS_PER_DAY = 8.0

# 対象レイヤー（表記ゆれ対応）
TARGET_LAYERS_RAW = [
    "施工中工事",
    "O2グループ", "02グループ", "Ｏ２グループ", "０２グループ",
    "発注先"
]
# 正規化後のターゲットレイヤー
TARGET_LAYERS_NORMALIZED = ["施工中工事", "O2グループ", "発注先"]

# 固定地点マスタ
FIXED_LOCATIONS = {
    "O2本社": {"lat": 39.29462, "lon": 141.11325, "stay_min": 80},
    "旧本社": {"lat": 39.31273, "lon": 141.00406, "stay_min": 15},
    "きたえるーむ": {"lat": 39.29352, "lon": 141.09822, "stay_min": 15},
    "吉田工務店": {"lat": 39.14443, "lon": 141.57198, "stay_min": 10},
    "O2戸澤": {"lat": 40.05132, "lon": 141.00514, "stay_min": 10},
    "藤沢倉庫": {"lat": 39.31066, "lon": 141.11238, "stay_min": 15},
}

# O2本社（出発・帰着地点）
O2_HONSHA = {
    "name": "O2本社",
    "lat": 39.29462,
    "lon": 141.11325,
    "stay_min": 0
}

# O2本社業務タスク（80分）
O2_HONSHA_TASK = {
    "name": "O2本社（業務）",
    "lat": 39.29462,
    "lon": 141.11325,
    "stay_min": 80
}

# 藤沢倉庫（Gap Filling用）
FUJISAWA_SOUKO = {
    "name": "藤沢倉庫",
    "lat": 39.31066,
    "lon": 141.11238,
    "stay_min": 15
}

# Gap Filling用の推定移動時間（秒）
# O2本社 ↔ 藤沢倉庫 間は約10分（近距離）
O2_TO_FUJISAWA_SECONDS = 600  # 10分
FUJISAWA_TO_KITAEROOM_SECONDS = 900  # 15分（藤沢倉庫→きたえるーむ）

# 社長宅
SHACHO_HOME = {
    "name": "社長宅",
    "lat": 39.28791,
    "lon": 141.11858,
    "stay_min": 5
}

# 時間設定
FIRST_VISIT_ARRIVAL_TIME = "08:00"
MEETING_DURATION = 10
LUNCH_START_HOUR = 11
LUNCH_START_MINUTE = 30
LUNCH_DURATION = 60
KITAEROOM_RECOMMENDED_TIME = "17:00"
DEFAULT_STAY_DURATION = 20

# 訪問禁止時間帯（相手先の昼休み）
# この時間帯に訪問（滞在）が重ならないように調整
VISIT_FORBIDDEN_START_HOUR = 12
VISIT_FORBIDDEN_START_MINUTE = 0
VISIT_FORBIDDEN_END_HOUR = 13
VISIT_FORBIDDEN_END_MINUTE = 0

# ルートカラー
ROUTE_COLORS = ["blue", "red", "green", "orange", "purple"]

# VRP設定
MAX_DAILY_WORK_MINUTES = 600
MAX_DAILY_WORK_SECONDS = MAX_DAILY_WORK_MINUTES * 60


# ========================================
# ユーティリティ関数
# ========================================

def normalize_text(text):
    """テキストを正規化（全角→半角、空白削除）"""
    return unicodedata.normalize("NFKC", str(text)).strip()


def get_stay_duration(name, layer=None, description=None, row=None):
    """滞在時間を取得"""
    name_str = str(name)

    # 手動追加の場合はmanual_stay_minutesカラムから取得
    if row is not None and "manual_stay_minutes" in row.index and pd.notna(row.get("manual_stay_minutes")):
        return int(row["manual_stay_minutes"])

    # descriptionから手動追加の滞在時間を取得
    if description and "手動追加" in str(description):
        match = re.search(r'（(\d+)分）', str(description))
        if match:
            return int(match.group(1))

    # 固定マスタとの一致確認
    for key, data in FIXED_LOCATIONS.items():
        if key in name_str:
            return data["stay_min"]

    # レイヤー別の判定
    layer_normalized = normalize_text(layer) if layer else ""

    if "施工中工事" in layer_normalized:
        if "事務所" in name_str and "現場" in name_str:
            return 20
        elif "事務所" in name_str:
            return 10
        elif "現場" in name_str:
            return 10
        else:
            return 20
    elif "発注先" in layer_normalized:
        return 20
    elif "O2" in layer_normalized or "グループ" in layer_normalized:
        return 10

    return DEFAULT_STAY_DURATION


def format_time(dt):
    """datetimeを「HH:MM」形式にフォーマット"""
    return dt.strftime("%H:%M")


def format_duration(seconds):
    """秒を「X時間Y分」形式にフォーマット"""
    if seconds < 0:
        return "0分"
    hours = int(seconds) // 3600
    minutes = (int(seconds) % 3600) // 60
    if hours > 0:
        return f"{hours}時間{minutes}分"
    else:
        return f"{minutes}分"


def format_duration_minutes(seconds):
    """秒を分に変換"""
    return int(seconds) // 60


def is_kitaeroom(location_name):
    """きたえるーむかどうかを判定"""
    return "きたえるーむ" in str(location_name)


def is_fujisawa_souko(location_name):
    """藤沢倉庫かどうかを判定"""
    return "藤沢倉庫" in str(location_name)


def is_o2_honsha_task(location_name):
    """O2本社（業務タスク）かどうかを判定"""
    name = str(location_name)
    # 「O2本社」を含むが、「出発」「帰社」ではないもの
    return "O2本社" in name and "出発" not in name and "帰社" not in name


def get_base_location_name(location_name):
    """場所名から基本名を抽出（事務所/現場の接尾辞を除去）"""
    name = str(location_name)
    # （事務所）（現場）（事務所・現場）を除去
    import re
    return re.sub(r'[（\(](事務所|現場|事務所・現場)[）\)]$', '', name).strip()


def is_same_location(name1, name2):
    """2つの場所名が同じ場所（事務所と現場のペア）かどうかを判定"""
    base1 = get_base_location_name(name1)
    base2 = get_base_location_name(name2)
    return base1 == base2 and base1 != ""


def overlaps_forbidden_lunch_time(arrival_time, departure_time):
    """
    訪問時間帯が昼休み禁止時間帯（12:00-13:00）と重なるかを判定

    Args:
        arrival_time: 到着時刻（datetime）
        departure_time: 出発時刻（datetime）

    Returns:
        bool: 重なる場合True
    """
    # 禁止時間帯の開始・終了を設定
    forbidden_start = arrival_time.replace(
        hour=VISIT_FORBIDDEN_START_HOUR,
        minute=VISIT_FORBIDDEN_START_MINUTE,
        second=0,
        microsecond=0
    )
    forbidden_end = arrival_time.replace(
        hour=VISIT_FORBIDDEN_END_HOUR,
        minute=VISIT_FORBIDDEN_END_MINUTE,
        second=0,
        microsecond=0
    )

    # 時間帯が重なるかチェック
    # 重なる条件: arrival < forbidden_end AND departure > forbidden_start
    return arrival_time < forbidden_end and departure_time > forbidden_start


def adjust_for_lunch_break(arrival_time, stay_minutes, point_name):
    """
    昼休み禁止時間帯（12:00-13:00）を避けて到着時刻を調整

    Args:
        arrival_time: 元の到着時刻（datetime）
        stay_minutes: 滞在時間（分）
        point_name: 訪問先名（昼食休憩は除外）

    Returns:
        tuple: (調整後の到着時刻, 待機時間（分）, 調整されたかどうか)
    """
    # 昼食休憩自体は除外
    if "昼食" in str(point_name):
        return arrival_time, 0, False

    departure_time = arrival_time + timedelta(minutes=stay_minutes)

    # 禁止時間帯と重なるかチェック
    if overlaps_forbidden_lunch_time(arrival_time, departure_time):
        # 13:00に到着時刻を変更
        adjusted_arrival = arrival_time.replace(
            hour=VISIT_FORBIDDEN_END_HOUR,
            minute=VISIT_FORBIDDEN_END_MINUTE,
            second=0,
            microsecond=0
        )
        wait_minutes = int((adjusted_arrival - arrival_time).total_seconds() / 60)
        return adjusted_arrival, wait_minutes, True

    return arrival_time, 0, False


def override_coordinates(df, name_col):
    """マスターデータで座標を強制上書き"""
    if name_col is None:
        return df

    df = df.copy()
    for idx, row in df.iterrows():
        location_name = str(row[name_col]) if pd.notna(row[name_col]) else ""
        for master_name, master_data in FIXED_LOCATIONS.items():
            if master_name in location_name:
                df.at[idx, "lat"] = master_data["lat"]
                df.at[idx, "lon"] = master_data["lon"]
                break
    return df


def check_naming_rule(df, name_col):
    """施工中工事の命名規則をチェック"""
    if name_col is None:
        return []

    # 末尾が「(事務所)」「(現場)」「(事務所・現場)」で終わっているかチェック
    valid_pattern = r'[（\(](事務所|現場|事務所・現場)[）\)]$'
    invalid_rows = df[~df[name_col].astype(str).str.contains(valid_pattern, regex=True)]

    return invalid_rows[name_col].tolist() if not invalid_rows.empty else []


# ========================================
# Google Maps API関連
# ========================================

@st.cache_data(ttl=600)
def fetch_data_from_mymap(map_id):
    """GoogleマイマップからKMLデータを取得"""
    try:
        url = f"https://www.google.com/maps/d/kml?mid={map_id}&forcekml=1"
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}
        root = ET.fromstring(response.content)

        data = []
        folders = root.findall('.//kml:Folder', namespaces)
        if not folders:
            folders = root.findall('.//Folder')

        for folder in folders:
            folder_name_elem = folder.find('kml:name', namespaces)
            if folder_name_elem is None:
                folder_name_elem = folder.find('name')
            layer_name = folder_name_elem.text if folder_name_elem is not None else ""

            placemarks = folder.findall('kml:Placemark', namespaces)
            if not placemarks:
                placemarks = folder.findall('Placemark')

            for pm in placemarks:
                name_elem = pm.find('kml:name', namespaces)
                if name_elem is None:
                    name_elem = pm.find('name')
                name = name_elem.text if name_elem is not None else ""

                desc_elem = pm.find('kml:description', namespaces)
                if desc_elem is None:
                    desc_elem = pm.find('description')
                description = desc_elem.text if desc_elem is not None else ""

                coord_elem = pm.find('.//kml:coordinates', namespaces)
                if coord_elem is None:
                    coord_elem = pm.find('.//coordinates')

                if coord_elem is not None and coord_elem.text:
                    coord_text = coord_elem.text.strip()
                    parts = coord_text.split(',')
                    if len(parts) >= 2:
                        try:
                            lon = float(parts[0].strip())
                            lat = float(parts[1].strip())
                            data.append({
                                'name': name,
                                'description': description,
                                'layer': layer_name,
                                'lat': lat,
                                'lon': lon
                            })
                        except ValueError:
                            continue

        if not data:
            return None, "KMLからデータを抽出できませんでした"

        return pd.DataFrame(data), None

    except Exception as e:
        return None, f"エラー: {e}"


def create_distance_matrix_google_batched(locations_tuple, api_key, progress_callback=None):
    """Google Maps Distance Matrix APIで所要時間行列を作成"""
    try:
        import time as time_module
        gmaps = googlemaps.Client(key=api_key)
        locations = list(locations_tuple)
        n = len(locations)
        CHUNK_SIZE = 8

        time_matrix = [[0] * n for _ in range(n)]
        origin_chunks = [locations[i:i + CHUNK_SIZE] for i in range(0, n, CHUNK_SIZE)]
        dest_chunks = [locations[i:i + CHUNK_SIZE] for i in range(0, n, CHUNK_SIZE)]

        total_requests = len(origin_chunks) * len(dest_chunks)
        current_request = 0

        for orig_idx, origin_chunk in enumerate(origin_chunks):
            for dest_idx, dest_chunk in enumerate(dest_chunks):
                current_request += 1

                if progress_callback:
                    progress = current_request / total_requests
                    progress_callback(progress, f"距離行列取得中... ({current_request}/{total_requests})")

                result = gmaps.distance_matrix(
                    origins=origin_chunk,
                    destinations=dest_chunk,
                    mode="driving",
                    language="ja"
                )

                if result["status"] != "OK":
                    raise Exception(f"Distance Matrix API エラー: {result['status']}")

                for i, row in enumerate(result["rows"]):
                    for j, element in enumerate(row["elements"]):
                        global_i = orig_idx * CHUNK_SIZE + i
                        global_j = dest_idx * CHUNK_SIZE + j

                        if element["status"] == "OK":
                            time_matrix[global_i][global_j] = element["duration"]["value"]
                        else:
                            time_matrix[global_i][global_j] = 999999

                if current_request < total_requests:
                    time_module.sleep(0.1)

        return time_matrix, None

    except Exception as e:
        return None, f"エラー: {str(e)}"


@st.cache_data
def get_route_polyline(origin, destination, api_key):
    """Google Directions APIでルートのポリラインを取得"""
    try:
        gmaps = googlemaps.Client(key=api_key)
        result = gmaps.directions(origin=origin, destination=destination, mode="driving")

        if result and len(result) > 0:
            encoded_polyline = result[0]["overview_polyline"]["points"]
            decoded = polyline.decode(encoded_polyline)
            return decoded, None
        else:
            return None, "ルートが見つかりません"

    except Exception as e:
        return None, f"Directions API エラー: {str(e)}"


def geocode_address(address, api_key):
    """Google Geocoding APIで住所から緯度経度を取得"""
    try:
        gmaps = googlemaps.Client(key=api_key)
        result = gmaps.geocode(address, language="ja")

        if result and len(result) > 0:
            location = result[0]["geometry"]["location"]
            formatted_address = result[0].get("formatted_address", address)
            return {
                "lat": location["lat"],
                "lon": location["lng"],
                "formatted_address": formatted_address
            }, None
        else:
            return None, "住所が見つかりませんでした"
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600)
def find_nearby_restaurant(lat, lon, api_key):
    """Google Places APIで近くのレストランを検索"""
    try:
        gmaps = googlemaps.Client(key=api_key)
        result = gmaps.places_nearby(
            location=(lat, lon),
            radius=2000,
            type="restaurant",
            language="ja"
        )

        if result and "results" in result and len(result["results"]) > 0:
            restaurants = [r for r in result["results"]
                          if "convenience_store" not in r.get("types", [])]
            restaurants = sorted(restaurants, key=lambda x: x.get("rating", 0), reverse=True)

            top_restaurants = []
            for r in restaurants[:3]:
                top_restaurants.append({
                    "name": r.get("name", "不明"),
                    "address": r.get("vicinity", ""),
                    "rating": r.get("rating", 0),
                    "lat": r["geometry"]["location"]["lat"],
                    "lon": r["geometry"]["location"]["lng"]
                })
            return top_restaurants, None
        else:
            return [], "近くにレストランが見つかりませんでした"

    except Exception as e:
        return [], f"Places API エラー: {str(e)}"


# ========================================
# VRP最適化
# ========================================

def solve_vrp_multi_day(time_matrix, num_days, depot_idx=0, stay_times=None):
    """VRPで複数日に分割して最適化"""
    n = len(time_matrix)

    if n <= 1:
        return [[]], [0]

    if stay_times is None:
        stay_times = [DEFAULT_STAY_DURATION * 60] * n
        stay_times[depot_idx] = 0

    manager = pywrapcp.RoutingIndexManager(n, num_days, depot_idx)
    routing = pywrapcp.RoutingModel(manager)

    def time_plus_stay_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        travel_time = time_matrix[from_node][to_node]
        stay_time = stay_times[to_node] if to_node != depot_idx else 0
        return travel_time + stay_time

    transit_callback_index = routing.RegisterTransitCallback(time_plus_stay_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    vehicle_capacities = [MAX_DAILY_WORK_SECONDS] * num_days
    routing.AddDimensionWithVehicleCapacity(
        transit_callback_index,
        0,
        vehicle_capacities,
        True,
        "WorkTime"
    )

    time_dimension = routing.GetDimensionOrDie("WorkTime")
    time_dimension.SetGlobalSpanCostCoefficient(100)

    for i in range(num_days):
        routing.AddVariableMinimizedByFinalizer(
            time_dimension.CumulVar(routing.End(i))
        )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 20

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        routes = []
        route_times = []

        for vehicle_id in range(num_days):
            route = []
            index = routing.Start(vehicle_id)
            route_time = 0

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node != depot_idx:
                    route.append(node)
                prev_index = index
                index = solution.Value(routing.NextVar(index))
                route_time += routing.GetArcCostForVehicle(prev_index, index, vehicle_id)

            routes.append(route)
            route_times.append(route_time)

        return routes, route_times
    else:
        # フォールバック: 均等分割
        visit_indices = [i for i in range(n) if i != depot_idx]
        routes = [[] for _ in range(num_days)]
        for i, idx in enumerate(visit_indices):
            routes[i % num_days].append(idx)
        return routes, [0] * num_days


def solve_tsp_optimal_order(time_matrix, depot_idx=0):
    """TSPで最適な巡回順序を1本計算"""
    n = len(time_matrix)

    if n <= 1:
        return []

    if n == 2:
        return [i for i in range(n) if i != depot_idx]

    manager = pywrapcp.RoutingIndexManager(n, 1, depot_idx)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return time_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 15

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        route = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != depot_idx:
                route.append(node)
            index = solution.Value(routing.NextVar(index))
        return route
    else:
        # フォールバック: depot以外を順番に
        return [i for i in range(n) if i != depot_idx]


def global_tsp_time_slice_allocation(
    visit_df,
    time_matrix_all,
    o2_idx,
    shacho_idx,
    name_col,
    num_days,
    daily_end_limit_hour=17,
    daily_end_limit_minute=30
):
    """
    Global TSP & Time Slicing 方式（きたえるーむ最後尾配置対応）

    アルゴリズム:
    1. きたえるーむ（時間指定あり）を一時的に除外
    2. 残りの訪問先でTSP計算 → 地理的に近い場所は隣接
    3. TSP結果の最後尾にきたえるーむを追加
    4. TSP順序を維持したまま、Day1に可能な限り詰め込む
    5. 終了時刻が17:30を超えたら、残りをDay2以降に回す

    Args:
        visit_df: 訪問先データフレーム
        time_matrix_all: 全地点の移動時間行列（O2, 社長宅, 訪問先...）
        o2_idx: O2本社のインデックス（通常0）
        shacho_idx: 社長宅のインデックス（通常1）
        name_col: 名前カラム名
        num_days: 最大日数
        daily_end_limit_hour: 1日の終了時刻上限（時）
        daily_end_limit_minute: 1日の終了時刻上限（分）

    Returns:
        day_routes: 各日の訪問先インデックスリスト
    """
    n_visits = len(visit_df)

    if n_visits == 0:
        return [[] for _ in range(num_days)]

    if n_visits == 1:
        return [[0]] + [[] for _ in range(num_days - 1)]

    # ============================================
    # Step 0: きたえるーむを特定して分離
    # ============================================
    kitaeroom_indices = []
    normal_indices = []

    for idx in range(n_visits):
        if name_col:
            point_name = visit_df.iloc[idx][name_col]
        else:
            point_name = ""
        if is_kitaeroom(point_name):
            kitaeroom_indices.append(idx)
        else:
            normal_indices.append(idx)

    # きたえるーむしかない場合
    if not normal_indices:
        return [kitaeroom_indices] + [[] for _ in range(num_days - 1)]

    # ============================================
    # Step 1: きたえるーむ以外でGlobal TSP計算
    # ============================================
    # ローカル行列を作成（社長宅 + きたえるーむ以外の訪問先）
    local_size = 1 + len(normal_indices)
    local_matrix = [[0] * local_size for _ in range(local_size)]

    for i in range(local_size):
        for j in range(local_size):
            if i == 0:
                orig_full_idx = shacho_idx
            else:
                orig_full_idx = normal_indices[i - 1] + 2
            if j == 0:
                dest_full_idx = shacho_idx
            else:
                dest_full_idx = normal_indices[j - 1] + 2
            local_matrix[i][j] = time_matrix_all[orig_full_idx][dest_full_idx]

    # TSP計算（社長宅をデポとして）
    tsp_result = solve_tsp_optimal_order(local_matrix, depot_idx=0)

    # TSP結果を元のインデックスに変換
    tsp_order = [normal_indices[idx - 1] for idx in tsp_result]

    # ============================================
    # Step 2: きたえるーむを最後尾に追加
    # ============================================
    tsp_order.extend(kitaeroom_indices)

    if not tsp_order:
        return [[] for _ in range(num_days)]

    # ============================================
    # Step 3: Time Slicing（時間シミュレーションで日程分割）
    # ============================================
    day_routes = [[] for _ in range(num_days)]
    current_day = 0
    cursor = 0

    while cursor < len(tsp_order) and current_day < num_days:
        day_visits = []

        # その日の開始時刻（最初の訪問先に08:00着）
        first_visit_arrival = datetime.combine(
            datetime.today(),
            datetime.strptime(FIRST_VISIT_ARRIVAL_TIME, "%H:%M").time()
        )

        # 終了時刻の上限
        end_limit = datetime.combine(
            datetime.today(),
            datetime.strptime(f"{daily_end_limit_hour}:{daily_end_limit_minute:02d}", "%H:%M").time()
        )

        current_time = first_visit_arrival
        prev_matrix_idx = shacho_idx

        while cursor < len(tsp_order):
            visit_idx = tsp_order[cursor]
            visit_matrix_idx = visit_idx + 2

            # 訪問先情報を取得
            if name_col:
                point_name = visit_df.iloc[visit_idx][name_col]
            else:
                point_name = f"訪問先{visit_idx + 1}"

            layer = visit_df.iloc[visit_idx].get("layer", None) if "layer" in visit_df.columns else None
            stay_duration = get_stay_duration(point_name, layer, None)

            # 移動時間と到着時刻の計算
            if len(day_visits) == 0:
                arrival = first_visit_arrival
                travel_time = time_matrix_all[shacho_idx][visit_matrix_idx]
            else:
                travel_time = time_matrix_all[prev_matrix_idx][visit_matrix_idx]
                arrival = current_time + timedelta(seconds=travel_time)

            # きたえるーむの17:00固定ルール（地理的順序を維持）
            if is_kitaeroom(point_name):
                target_17 = arrival.replace(hour=17, minute=0, second=0, microsecond=0)
                if arrival < target_17:
                    arrival = target_17

            # 滞在時間の計算（初回は打ち合わせ時間も加算）
            if len(day_visits) == 0:
                departure = arrival + timedelta(minutes=MEETING_DURATION + stay_duration)
            else:
                departure = arrival + timedelta(minutes=stay_duration)

            # この訪問先を追加した場合の帰社時刻を予測
            visit_to_shacho = time_matrix_all[visit_matrix_idx][shacho_idx]
            shacho_to_o2 = time_matrix_all[shacho_idx][o2_idx]
            estimated_end = (
                departure
                + timedelta(seconds=visit_to_shacho)
                + timedelta(minutes=SHACHO_HOME["stay_min"])
                + timedelta(seconds=shacho_to_o2)
            )

            # 終了時刻が上限を超えるかチェック
            if estimated_end > end_limit and len(day_visits) > 0:
                # この訪問先から先は翌日に回す
                break
            else:
                # この日に追加
                day_visits.append(visit_idx)
                current_time = departure
                prev_matrix_idx = visit_matrix_idx
                cursor += 1

        day_routes[current_day] = day_visits
        current_day += 1

    # まだ残りがある場合は最終日に追加
    if cursor < len(tsp_order):
        remaining = tsp_order[cursor:]
        day_routes[num_days - 1].extend(remaining)

    return day_routes


def reoptimize_day_route(visit_indices, time_matrix_all, shacho_idx, visit_df=None, name_col=None):
    """
    指定された訪問先インデックスリストをTSPで再最適化
    （きたえるーむは常に最後尾に配置）

    Args:
        visit_indices: 訪問先インデックスのリスト
        time_matrix_all: 全地点の移動時間行列
        shacho_idx: 社長宅のインデックス
        visit_df: 訪問先データフレーム（きたえるーむ判定用）
        name_col: 名前カラム名

    Returns:
        optimized_indices: TSP最適化後の訪問先インデックスリスト
    """
    if len(visit_indices) <= 1:
        return list(visit_indices)

    # きたえるーむを分離
    kitaeroom_indices = []
    normal_indices = []

    for idx in visit_indices:
        if visit_df is not None and name_col:
            point_name = visit_df.iloc[idx][name_col]
            if is_kitaeroom(point_name):
                kitaeroom_indices.append(idx)
            else:
                normal_indices.append(idx)
        else:
            normal_indices.append(idx)

    # きたえるーむ以外がない場合
    if not normal_indices:
        return list(kitaeroom_indices)

    # きたえるーむ以外でTSP最適化
    local_size = 1 + len(normal_indices)
    local_matrix = [[0] * local_size for _ in range(local_size)]

    for i in range(local_size):
        for j in range(local_size):
            if i == 0:
                orig_full_idx = shacho_idx
            else:
                orig_full_idx = normal_indices[i - 1] + 2
            if j == 0:
                dest_full_idx = shacho_idx
            else:
                dest_full_idx = normal_indices[j - 1] + 2
            local_matrix[i][j] = time_matrix_all[orig_full_idx][dest_full_idx]

    # TSP計算
    tsp_result = solve_tsp_optimal_order(local_matrix, depot_idx=0)

    # 結果を元のインデックスに変換
    optimized_indices = [normal_indices[idx - 1] for idx in tsp_result]

    # きたえるーむを最後尾に追加
    optimized_indices.extend(kitaeroom_indices)

    return optimized_indices


def optimize_gap_filling_moves(day_routes, visit_df, time_matrix_all, o2_idx, shacho_idx, name_col):
    """
    Gap Filling用のタスク移動処理

    きたえるーむがある日の空き時間を計算し、100分以上の空きがある場合は
    他の日からO2本社・藤沢倉庫を移動させる

    Args:
        day_routes: 各日の訪問先インデックスリスト
        visit_df: 訪問先データフレーム
        time_matrix_all: 全地点の移動時間行列
        o2_idx: O2本社のインデックス（通常0）
        shacho_idx: 社長宅のインデックス（通常1）
        name_col: 名前カラム名

    Returns:
        optimized_day_routes: 最適化後の日程ルート
    """
    if not name_col:
        return day_routes

    # 結果用にコピー
    optimized_routes = [list(route) for route in day_routes]

    # ============================================
    # Step 1: きたえるーむがある日と空き時間を特定
    # ============================================
    kitaeroom_day = None
    kitaeroom_idx_in_route = None

    for day_idx, route in enumerate(optimized_routes):
        for pos, visit_idx in enumerate(route):
            point_name = visit_df.iloc[visit_idx][name_col]
            if is_kitaeroom(point_name):
                kitaeroom_day = day_idx
                kitaeroom_idx_in_route = pos
                break
        if kitaeroom_day is not None:
            break

    # きたえるーむがない場合は何もしない
    if kitaeroom_day is None:
        return optimized_routes

    # ============================================
    # Step 2: きたえるーむ前の空き時間を計算
    # ============================================
    route_with_kitaeroom = optimized_routes[kitaeroom_day]

    # きたえるーむの直前までのスケジュールをシミュレーション
    first_visit_arrival = datetime.combine(
        datetime.today(),
        datetime.strptime(FIRST_VISIT_ARRIVAL_TIME, "%H:%M").time()
    )

    current_time = first_visit_arrival
    prev_matrix_idx = shacho_idx

    # きたえるーむ直前まで処理
    for i, visit_idx in enumerate(route_with_kitaeroom):
        visit_matrix_idx = visit_idx + 2
        point_name = visit_df.iloc[visit_idx][name_col]

        # きたえるーむに到達したら終了
        if is_kitaeroom(point_name):
            break

        layer = visit_df.iloc[visit_idx].get("layer", None) if "layer" in visit_df.columns else None
        stay_duration = get_stay_duration(point_name, layer, None)

        if i == 0:
            arrival = first_visit_arrival
        else:
            travel_time = time_matrix_all[prev_matrix_idx][visit_matrix_idx]
            arrival = current_time + timedelta(seconds=travel_time)

        # 初回は打ち合わせ時間も加算
        if i == 0:
            departure = arrival + timedelta(minutes=MEETING_DURATION + stay_duration)
        else:
            departure = arrival + timedelta(minutes=stay_duration)

        current_time = departure
        prev_matrix_idx = visit_matrix_idx

    # きたえるーむへの移動時間を計算
    kitaeroom_visit_idx = route_with_kitaeroom[kitaeroom_idx_in_route]
    kitaeroom_matrix_idx = kitaeroom_visit_idx + 2

    if kitaeroom_idx_in_route > 0:
        prev_visit_idx = route_with_kitaeroom[kitaeroom_idx_in_route - 1]
        prev_matrix_idx = prev_visit_idx + 2
        travel_to_kitaeroom = time_matrix_all[prev_matrix_idx][kitaeroom_matrix_idx]
    else:
        travel_to_kitaeroom = time_matrix_all[shacho_idx][kitaeroom_matrix_idx]

    kitaeroom_arrival = current_time + timedelta(seconds=travel_to_kitaeroom)
    target_17 = kitaeroom_arrival.replace(hour=17, minute=0, second=0, microsecond=0)

    # 空き時間を計算
    if kitaeroom_arrival < target_17:
        gap_minutes = int((target_17 - kitaeroom_arrival).total_seconds() / 60)
    else:
        gap_minutes = 0

    # ============================================
    # Step 3: 100分以上の空きがある場合、移動対象を探す
    # ============================================
    if gap_minutes < 100:
        return optimized_routes

    # 移動に必要な時間：O2本社(80分) + 移動(10分) + 藤沢倉庫(15分) + 移動(15分) = 約120分
    required_time = O2_HONSHA_TASK["stay_min"] + (O2_TO_FUJISAWA_SECONDS // 60) + \
                    FUJISAWA_SOUKO["stay_min"] + (FUJISAWA_TO_KITAEROOM_SECONDS // 60)

    # 空き時間が足りない場合はスキップ
    if gap_minutes < required_time:
        return optimized_routes

    # ============================================
    # Step 4: 他の日からO2本社・藤沢倉庫を検索して移動
    # ============================================
    o2_found = None  # (day_idx, pos_in_route, visit_idx)
    fujisawa_found = None  # (day_idx, pos_in_route, visit_idx)

    for day_idx, route in enumerate(optimized_routes):
        # きたえるーむがある日からは移動しない（既にそこにある場合）
        if day_idx == kitaeroom_day:
            continue

        for pos, visit_idx in enumerate(route):
            point_name = visit_df.iloc[visit_idx][name_col]

            # O2本社を検索（出発・帰社ではないもの）
            if o2_found is None and is_o2_honsha_task(point_name):
                o2_found = (day_idx, pos, visit_idx)

            # 藤沢倉庫を検索
            if fujisawa_found is None and is_fujisawa_souko(point_name):
                fujisawa_found = (day_idx, pos, visit_idx)

    # ============================================
    # Step 5: 見つかったタスクを移動
    # ============================================
    # 削除は後ろから行う（インデックスがずれないように）
    tasks_to_remove = []
    tasks_to_add = []

    if o2_found:
        tasks_to_remove.append(o2_found)
        tasks_to_add.append(o2_found[2])  # visit_idx

    if fujisawa_found:
        tasks_to_remove.append(fujisawa_found)
        tasks_to_add.append(fujisawa_found[2])  # visit_idx

    # 削除（同じ日の場合は後ろのインデックスから削除）
    # 日ごと・位置ごとにソートして後ろから削除
    tasks_to_remove.sort(key=lambda x: (x[0], x[1]), reverse=True)

    for day_idx, pos, visit_idx in tasks_to_remove:
        if pos < len(optimized_routes[day_idx]):
            optimized_routes[day_idx].pop(pos)

    # きたえるーむの直前に挿入（O2本社 → 藤沢倉庫 の順）
    # きたえるーむのインデックスを再計算（削除により変わっている可能性）
    new_kitaeroom_pos = None
    for pos, visit_idx in enumerate(optimized_routes[kitaeroom_day]):
        point_name = visit_df.iloc[visit_idx][name_col]
        if is_kitaeroom(point_name):
            new_kitaeroom_pos = pos
            break

    if new_kitaeroom_pos is not None:
        # O2本社を先に挿入（藤沢倉庫より前に来るように）
        for visit_idx in tasks_to_add:
            point_name = visit_df.iloc[visit_idx][name_col]
            if is_o2_honsha_task(point_name):
                optimized_routes[kitaeroom_day].insert(new_kitaeroom_pos, visit_idx)
                new_kitaeroom_pos += 1  # 挿入したのでずらす

        # 藤沢倉庫を挿入
        for visit_idx in tasks_to_add:
            point_name = visit_df.iloc[visit_idx][name_col]
            if is_fujisawa_souko(point_name):
                optimized_routes[kitaeroom_day].insert(new_kitaeroom_pos, visit_idx)
                new_kitaeroom_pos += 1

    return optimized_routes


# ========================================
# タイムテーブル作成
# ========================================

def create_day_timetable(day_num, visit_indices, visit_df, time_matrix_all,
                         o2_idx, shacho_idx, name_col, api_key=None):
    """1日分のタイムテーブルを作成"""
    timetable = []
    calendar_text = []

    if not visit_indices:
        return pd.DataFrame(), "", []

    # ============================================
    # 訪問先リストをそのまま使用
    # （Gap Filling移動は optimize_gap_filling_moves で事前処理済み）
    # ============================================
    filtered_visit_indices = list(visit_indices)

    if not filtered_visit_indices:
        return pd.DataFrame(), "", []

    first_visit_arrival = datetime.combine(datetime.today(),
                                           datetime.strptime(FIRST_VISIT_ARRIVAL_TIME, "%H:%M").time())
    first_visit_matrix_idx = filtered_visit_indices[0] + 2

    shacho_to_first_time = time_matrix_all[shacho_idx][first_visit_matrix_idx]
    o2_to_shacho_time = time_matrix_all[o2_idx][shacho_idx]

    shacho_departure = first_visit_arrival - timedelta(seconds=shacho_to_first_time)
    shacho_arrival = shacho_departure - timedelta(minutes=SHACHO_HOME["stay_min"])
    o2_departure = shacho_arrival - timedelta(seconds=o2_to_shacho_time)

    order = 1

    # O2→社長宅の移動時間（分）
    o2_to_shacho_min = int(o2_to_shacho_time) // 60
    shacho_to_first_min = int(shacho_to_first_time) // 60

    # 1. O2本社（出発）
    timetable.append({
        "順番": order,
        "場所名": f"{O2_HONSHA['name']}（出発）",
        "到着時刻": "-",
        "出発時刻": format_time(o2_departure),
        "滞在時間(分)": 0,
        "移動時間(分)": 0,
        "待機時間(分)": 0,
        "備考": "前日準備済"
    })
    calendar_text.append(f"{format_time(o2_departure)} - {format_time(o2_departure)} (0分) {O2_HONSHA['name']} 出発")
    order += 1

    # 2. 社長宅（ピックアップ）
    timetable.append({
        "順番": order,
        "場所名": f"{SHACHO_HOME['name']}（ピックアップ）",
        "到着時刻": format_time(shacho_arrival),
        "出発時刻": format_time(shacho_departure),
        "滞在時間(分)": SHACHO_HOME["stay_min"],
        "移動時間(分)": o2_to_shacho_min,
        "待機時間(分)": 0,
        "備考": "社長同乗"
    })
    calendar_text.append(f"{format_time(shacho_arrival)} - {format_time(shacho_departure)} ({SHACHO_HOME['stay_min']}分) {SHACHO_HOME['name']}（社長同乗） 【移動: {o2_to_shacho_min}分】")
    order += 1

    # 3. 訪問先リスト
    current_time = first_visit_arrival
    lunch_inserted = False
    total_travel_seconds = o2_to_shacho_time + shacho_to_first_time
    total_stay_minutes = SHACHO_HOME["stay_min"]

    for i, visit_idx in enumerate(filtered_visit_indices):
        if name_col:
            point_name = visit_df.iloc[visit_idx][name_col]
        else:
            point_name = f"訪問先{visit_idx + 1}"

        layer = visit_df.iloc[visit_idx].get("layer", None) if "layer" in visit_df.columns else None
        description = visit_df.iloc[visit_idx].get("description", None) if "description" in visit_df.columns else None

        stay_duration = get_stay_duration(point_name, layer, description)
        visit_matrix_idx = visit_idx + 2

        if i == 0:
            travel_time = shacho_to_first_time
            arrival = first_visit_arrival
        else:
            prev_matrix_idx = filtered_visit_indices[i - 1] + 2
            travel_time = time_matrix_all[prev_matrix_idx][visit_matrix_idx]
            arrival = current_time + timedelta(seconds=travel_time)
            total_travel_seconds += travel_time

        # ランチ挿入チェック
        lunch_check_time = datetime.combine(datetime.today(),
                                            datetime.strptime(f"{LUNCH_START_HOUR}:{LUNCH_START_MINUTE}", "%H:%M").time())

        # 同じ場所（事務所→現場）の間には昼食を挟まない
        prev_point_name = ""
        if i > 0:
            prev_visit_idx = filtered_visit_indices[i - 1]
            prev_point_name = visit_df.iloc[prev_visit_idx][name_col] if name_col else ""

        skip_lunch_for_same_location = is_same_location(prev_point_name, point_name)

        if not lunch_inserted and current_time >= lunch_check_time and i > 0 and not skip_lunch_for_same_location:
            # 昼食終了時刻は次の訪問先到着時刻に合わせる（移動時間を考慮）
            # arrival = current_time + travel_time なので、昼食後の到着時刻を計算
            lunch_end = arrival  # 次の訪問先への到着時刻
            lunch_start = lunch_end - timedelta(minutes=LUNCH_DURATION)

            prev_visit_idx = filtered_visit_indices[i - 1]
            prev_lat = visit_df.iloc[prev_visit_idx]["lat"]
            prev_lon = visit_df.iloc[prev_visit_idx]["lon"]

            restaurant_name = "昼食休憩"
            if api_key:
                restaurants, _ = find_nearby_restaurant(prev_lat, prev_lon, api_key)
                if restaurants:
                    restaurant_name = f"昼食：{restaurants[0]['name']}"

            timetable.append({
                "順番": "🍽️",
                "場所名": restaurant_name,
                "到着時刻": format_time(lunch_start),
                "出発時刻": format_time(lunch_end),
                "滞在時間(分)": LUNCH_DURATION,
                "移動時間(分)": 0,
                "待機時間(分)": 0,
                "備考": "昼食休憩"
            })
            calendar_text.append(f"{format_time(lunch_start)} - {format_time(lunch_end)} ({LUNCH_DURATION}分) {restaurant_name}")
            total_stay_minutes += LUNCH_DURATION

            # current_timeは更新しない（arrivalはすでに計算済み）
            lunch_inserted = True

        # 訪問先の処理
        travel_min = int(travel_time) // 60

        # ============================================
        # 昼休み訪問禁止ルール（12:00-13:00）
        # 相手先の昼休みを避けて到着時刻を調整
        # ============================================
        lunch_break_wait = 0
        lunch_break_adjusted = False

        # きたえるーむは17:00固定なので昼休み調整の対象外
        if not is_kitaeroom(point_name):
            # 1件目の場合は打ち合わせ+滞在時間、2件目以降は滞在時間のみ
            if i == 0:
                total_stay_for_check = MEETING_DURATION + stay_duration
            else:
                total_stay_for_check = stay_duration

            adjusted_arrival, lunch_break_wait, lunch_break_adjusted = adjust_for_lunch_break(
                arrival, total_stay_for_check, point_name
            )

            if lunch_break_adjusted:
                arrival = adjusted_arrival

        # ============================================
        # きたえるーむ17:00固定ルール
        # （Gap Fillingによるタスク移動は optimize_gap_filling_moves で事前処理済み）
        # ============================================
        wait_minutes = 0
        remark = ""
        if is_kitaeroom(point_name):
            target_time = arrival.replace(hour=17, minute=0, second=0, microsecond=0)
            if arrival < target_time:
                # 17:00より早く着いた場合は待機
                wait_minutes = int((target_time - arrival).total_seconds() / 60)
                arrival = target_time
                remark = f"💡 {wait_minutes}分待機（17:00固定）"
            # 17:00を過ぎている場合は待機なし（なりゆきの到着時刻で開始）

        if i == 0:
            # 1件目の場合（きたえるーむでも適用後の時刻で処理）
            meeting_end = arrival + timedelta(minutes=MEETING_DURATION)

            # 待機時間を合算（きたえるーむ待機 + 昼休み待機）
            total_wait = wait_minutes + lunch_break_wait

            first_remark = "現場打ち合わせ"
            if lunch_break_adjusted:
                first_remark = f"🍽️ 昼休み{lunch_break_wait}分待機後、打ち合わせ"
            elif wait_minutes > 0:
                first_remark = f"💡 {wait_minutes}分待機後、打ち合わせ"

            timetable.append({
                "順番": f"★{order}",
                "場所名": f"{point_name}（打合せ）",
                "到着時刻": format_time(arrival),
                "出発時刻": format_time(meeting_end),
                "滞在時間(分)": MEETING_DURATION,
                "移動時間(分)": shacho_to_first_min,
                "待機時間(分)": total_wait,
                "備考": first_remark
            })

            wait_info = f"【待機: {total_wait}分】" if total_wait > 0 else ""
            calendar_text.append(f"{format_time(arrival)} - {format_time(meeting_end)} ({MEETING_DURATION}分) {point_name}（打合せ） 【移動: {shacho_to_first_min}分】{wait_info}")
            total_stay_minutes += MEETING_DURATION + total_wait

            work_start = meeting_end
            work_end = work_start + timedelta(minutes=stay_duration)
            timetable.append({
                "順番": order,
                "場所名": f"{point_name}（点検開始）",
                "到着時刻": format_time(work_start),
                "出発時刻": format_time(work_end),
                "滞在時間(分)": stay_duration,
                "移動時間(分)": 0,
                "待機時間(分)": 0,
                "備考": ""
            })
            calendar_text.append(f"{format_time(work_start)} - {format_time(work_end)} ({stay_duration}分) {point_name}（点検開始）")
            total_stay_minutes += stay_duration
            departure = work_end
        else:
            # 2件目以降
            departure = arrival + timedelta(minutes=stay_duration)

            # 待機時間を合算（きたえるーむ待機 + 昼休み待機）
            total_wait = wait_minutes + lunch_break_wait

            # 備考を設定（昼休み調整優先）
            if lunch_break_adjusted:
                final_remark = f"🍽️ 昼休み{lunch_break_wait}分待機（13:00～）"
            else:
                final_remark = remark

            timetable.append({
                "順番": order,
                "場所名": point_name,
                "到着時刻": format_time(arrival),
                "出発時刻": format_time(departure),
                "滞在時間(分)": stay_duration,
                "移動時間(分)": travel_min,
                "待機時間(分)": total_wait,
                "備考": final_remark
            })

            # カレンダーテキスト（移動時間・待機時間を追記）
            info_str = f" 【移動: {travel_min}分】" if travel_min > 0 else ""
            if total_wait > 0:
                info_str += f"【待機: {total_wait}分】"
            calendar_text.append(f"{format_time(arrival)} - {format_time(departure)} ({stay_duration}分) {point_name}{info_str}")
            total_stay_minutes += stay_duration + total_wait

        current_time = departure
        order += 1

    # 4. 社長宅（送り届け）
    last_visit_matrix_idx = filtered_visit_indices[-1] + 2
    last_to_shacho_time = time_matrix_all[last_visit_matrix_idx][shacho_idx]
    last_to_shacho_min = int(last_to_shacho_time) // 60
    total_travel_seconds += last_to_shacho_time

    shacho_return_arrival = current_time + timedelta(seconds=last_to_shacho_time)
    shacho_return_departure = shacho_return_arrival + timedelta(minutes=SHACHO_HOME["stay_min"])

    timetable.append({
        "順番": order,
        "場所名": f"{SHACHO_HOME['name']}（送り届け）",
        "到着時刻": format_time(shacho_return_arrival),
        "出発時刻": format_time(shacho_return_departure),
        "滞在時間(分)": SHACHO_HOME["stay_min"],
        "移動時間(分)": last_to_shacho_min,
        "待機時間(分)": 0,
        "備考": "社長降車"
    })
    calendar_text.append(f"{format_time(shacho_return_arrival)} - {format_time(shacho_return_departure)} ({SHACHO_HOME['stay_min']}分) {SHACHO_HOME['name']}（社長降車） 【移動: {last_to_shacho_min}分】")
    total_stay_minutes += SHACHO_HOME["stay_min"]
    order += 1

    # 5. O2本社（帰社）
    shacho_to_o2_time = time_matrix_all[shacho_idx][o2_idx]
    shacho_to_o2_min = int(shacho_to_o2_time) // 60
    total_travel_seconds += shacho_to_o2_time
    o2_return_arrival = shacho_return_departure + timedelta(seconds=shacho_to_o2_time)

    timetable.append({
        "順番": order,
        "場所名": f"{O2_HONSHA['name']}（帰社）",
        "到着時刻": format_time(o2_return_arrival),
        "出発時刻": "-",
        "滞在時間(分)": 0,
        "移動時間(分)": shacho_to_o2_min,
        "待機時間(分)": 0,
        "備考": "業務終了"
    })
    calendar_text.append(f"{format_time(o2_return_arrival)} - {format_time(o2_return_arrival)} (0分) {O2_HONSHA['name']} 解散 【移動: {shacho_to_o2_min}分】")

    # カレンダー用テキスト整形
    day_header = f"【Day {day_num}】"
    calendar_output = day_header + "\n" + "\n".join(calendar_text)

    # メトリクス情報を追加
    metrics = {
        "total_travel_seconds": total_travel_seconds,
        "total_stay_minutes": total_stay_minutes,
        "start_time": o2_departure,
        "end_time": o2_return_arrival
    }

    return pd.DataFrame(timetable), calendar_output, metrics


def get_name_column(df):
    """名前列を特定"""
    for col in ["name", "名前", "地点名", "名称", "title"]:
        if col in df.columns:
            return col
    return None


# ========================================
# メインアプリケーション
# ========================================

st.title("🏗️ 環境整備スケジュール作成システム")

# サイドバー設定
st.sidebar.header("⚙️ 設定")

# 日程設定
st.sidebar.subheader("🗓️ 日程設定")
num_days = st.sidebar.number_input("確保する日数", value=2, min_value=1, max_value=10, step=1)

st.sidebar.markdown("---")

# ルート構成説明
st.sidebar.subheader("📍 ルート構成")
st.sidebar.info(f"""
**各日のルート:**
🏢 {O2_HONSHA['name']}（出発）
↓
🏠 {SHACHO_HOME['name']}（ピックアップ）
↓
📍 訪問先1件目（{FIRST_VISIT_ARRIVAL_TIME}着）
↓
📍 訪問先2件目〜
↓
🏠 {SHACHO_HOME['name']}（送り届け）
↓
🏢 {O2_HONSHA['name']}（帰着）

※ 定時: {WORK_HOURS_PER_DAY:.0f}時間/日
""")

# API設定（固定値使用）
api_key = DEFAULT_API_KEY

# session_state 初期化
if "route_result" not in st.session_state:
    st.session_state.route_result = None

# ========================================
# データ読み込み
# ========================================

map_df = None

try:
    with st.spinner("マイマップからデータを取得中..."):
        df, error = fetch_data_from_mymap(DEFAULT_MAP_ID)

    if error:
        st.error(f"❌ Googleマイマップを読み込めませんでした。\n\nマップIDまたは公開設定を確認してください。\n\n**エラー詳細:** {error}")
        st.stop()
    elif df is not None and len(df) > 0:
        st.success(f"✅ {len(df)}件のデータを取得しました")
        map_df = df
    else:
        st.error("❌ データが取得できませんでした。マイマップの公開設定を確認してください。")
        st.stop()

except Exception as e:
    st.error(f"❌ Googleマイマップを読み込めませんでした。\n\n**エラー詳細:** {e}")
    st.stop()

# ========================================
# データ処理
# ========================================

if map_df is not None and len(map_df) > 0:
    name_col = get_name_column(map_df)
    map_df = override_coordinates(map_df, name_col)

    # レイヤーカラムがない場合は追加
    if "layer" not in map_df.columns:
        map_df["layer"] = "その他"

    # レイヤー名を正規化
    map_df["layer"] = map_df["layer"].fillna("その他").replace("", "その他")
    map_df["layer_normalized"] = map_df["layer"].apply(normalize_text)

    # 対象レイヤーのデータのみ抽出
    existing_layers = map_df["layer_normalized"].unique().tolist()

    # 不足レイヤーの警告
    missing_layers = [t for t in TARGET_LAYERS_NORMALIZED if t not in existing_layers]
    if missing_layers:
        st.warning(f"⚠️ 以下のレイヤーがデータ内に見つかりませんでした: {', '.join(missing_layers)}")

    # 対象レイヤーのデータをフィルタ
    def is_target_layer(layer_normalized):
        for target in TARGET_LAYERS_NORMALIZED:
            if target in layer_normalized:
                return True
        return False

    filtered_df = map_df[map_df["layer_normalized"].apply(is_target_layer)].copy()

    # 社長宅を除外
    if name_col:
        filtered_df = filtered_df[~filtered_df[name_col].str.contains("社長宅", na=False)]

    # ========================================
    # 訪問先選択UI
    # ========================================

    st.subheader("1️⃣ 訪問先を選択")

    selected_rows_list = []

    for target in TARGET_LAYERS_NORMALIZED:
        layer_df = filtered_df[filtered_df["layer_normalized"].str.contains(target, na=False)].copy()

        if len(layer_df) == 0:
            continue

        # 場所名で並び替え（あいうえお順）
        if name_col and name_col in layer_df.columns:
            layer_df = layer_df.sort_values(by=name_col, key=lambda x: x.str.lower()).reset_index(drop=True)

        # 施工中工事の命名規則チェック
        if target == "施工中工事" and name_col:
            invalid_names = check_naming_rule(layer_df, name_col)
            if invalid_names:
                st.error(f"⚠️ 【ルール違反】以下の場所名は末尾に（事務所）（現場）（事務所・現場）のいずれかが付いていません。")
                st.write(invalid_names)

        # レイヤーアイコン設定
        if "O2" in target or "グループ" in target:
            layer_icon = "🏢"
        elif "施工" in target or "工事" in target:
            layer_icon = "🔨"
        elif "発注" in target:
            layer_icon = "📦"
        else:
            layer_icon = "📍"

        original_layer_name = layer_df["layer"].iloc[0]

        with st.expander(f"{layer_icon} {original_layer_name}（{len(layer_df)}件）", expanded=True):
            if name_col:
                # 選択肢を作成
                options = []
                option_to_name = {}
                for idx, row in layer_df.iterrows():
                    point_name = row[name_col]
                    stay_min = get_stay_duration(point_name, row.get("layer"), row.get("description"))
                    display_name = f"{point_name}（{stay_min}分）"
                    options.append(display_name)
                    option_to_name[display_name] = point_name

                # multiselect（初期値は空）
                selected_display_names = st.multiselect(
                    "訪問する場所:",
                    options=options,
                    default=[],
                    key=f"multiselect_{target}"
                )

                # 選択された行を抽出
                selected_names = [option_to_name[d] for d in selected_display_names]
                selected_in_layer = layer_df[layer_df[name_col].isin(selected_names)]
                selected_rows_list.append(selected_in_layer)

    # 選択結果を統合
    if selected_rows_list:
        selected_df = pd.concat(selected_rows_list, ignore_index=True)
        if name_col:
            selected_point_names = selected_df[name_col].tolist()
        else:
            selected_point_names = [f"地点{i + 1}" for i in range(len(selected_df))]
    else:
        selected_df = pd.DataFrame()
        selected_point_names = []

    # ========================================
    # 訪問先手動追加UI
    # ========================================

    # session_stateで手動追加訪問先を管理
    if "manual_visits" not in st.session_state:
        st.session_state.manual_visits = []

    with st.expander("➕ 訪問先を手動追加", expanded=False):
        st.info("マイマップにない訪問先を追加できます。名前と住所を入力してください。")

        col_name, col_address = st.columns([1, 2])
        with col_name:
            manual_name = st.text_input("場所の名前 *", placeholder="例: 〇〇現場", key="manual_name_input")
        with col_address:
            manual_address = st.text_input("住所 *", placeholder="例: 神奈川県藤沢市...", key="manual_address_input")

        col_stay, col_type, col_btn = st.columns([1, 1, 1])
        with col_stay:
            manual_stay = st.number_input("滞在時間（分）", value=60, min_value=10, max_value=480, step=10, key="manual_stay_input")
        with col_type:
            manual_type = st.selectbox("種別", options=["現場", "事務所", "事務所・現場", "その他"], key="manual_type_input")
        with col_btn:
            st.write("")  # スペーサー
            add_btn = st.button("🔍 住所を検索して追加", key="btn_add_manual_visit", use_container_width=True)

        if add_btn:
            if not manual_name:
                st.error("場所の名前を入力してください")
            elif not manual_address:
                st.error("住所を入力してください")
            else:
                with st.spinner("住所を検索中..."):
                    geo_result, geo_error = geocode_address(manual_address, api_key)

                if geo_error:
                    st.error(f"❌ 住所の検索に失敗しました: {geo_error}")
                elif geo_result:
                    # 名前に種別を付加（現場/事務所の場合）
                    if manual_type != "その他" and f"（{manual_type}）" not in manual_name:
                        display_name = f"{manual_name}（{manual_type}）"
                    else:
                        display_name = manual_name

                    new_visit = {
                        "name": display_name,
                        "lat": geo_result["lat"],
                        "lon": geo_result["lon"],
                        "address": geo_result["formatted_address"],
                        "stay_minutes": manual_stay,
                        "type": manual_type
                    }
                    st.session_state.manual_visits.append(new_visit)
                    st.success(f"✅ 「{display_name}」を追加しました（{geo_result['formatted_address']}）")
                    st.rerun()

        # 追加済みの手動訪問先を表示
        if st.session_state.manual_visits:
            st.markdown("---")
            st.markdown("**追加済みの訪問先:**")
            for i, visit in enumerate(st.session_state.manual_visits):
                col_info, col_del = st.columns([4, 1])
                with col_info:
                    st.write(f"📍 {visit['name']}（{visit['stay_minutes']}分）- {visit['address']}")
                with col_del:
                    if st.button("🗑️", key=f"del_manual_{i}", help="削除"):
                        st.session_state.manual_visits.pop(i)
                        st.rerun()

            if st.button("🗑️ すべての手動追加をクリア", key="btn_clear_manual"):
                st.session_state.manual_visits = []
                st.rerun()

    # 手動追加訪問先をselected_dfに統合
    if st.session_state.manual_visits:
        for visit in st.session_state.manual_visits:
            manual_row = pd.DataFrame([{
                name_col if name_col else "name": visit["name"],
                "lat": visit["lat"],
                "lon": visit["lon"],
                "layer": "手動追加",
                "layer_normalized": "手動追加",
                "description": f"手動追加（{visit['stay_minutes']}分）",
                "manual_stay_minutes": visit["stay_minutes"]
            }])
            selected_df = pd.concat([selected_df, manual_row], ignore_index=True)
            if visit["name"] not in selected_point_names:
                selected_point_names.append(visit["name"])

    # O2本社業務タスクを自動追加
    if len(selected_point_names) > 0:
        selected_has_o2 = any("O2本社" in str(name) for name in selected_point_names)
        if not selected_has_o2:
            o2_task_row = pd.DataFrame([{
                name_col if name_col else "name": O2_HONSHA_TASK["name"],
                "lat": O2_HONSHA_TASK["lat"],
                "lon": O2_HONSHA_TASK["lon"],
                "layer": "O2グループ",
                "layer_normalized": "O2グループ",
                "description": "O2本社での業務（80分）"
            }])
            selected_df = pd.concat([selected_df, o2_task_row], ignore_index=True)
            selected_point_names.append(O2_HONSHA_TASK["name"])
            st.info(f"📌 「{O2_HONSHA_TASK['name']}」（80分）を自動追加しました")

    # 選択件数表示
    if len(selected_point_names) > 0:
        st.success(f"✅ {len(selected_point_names)}件選択 → {num_days}日に分割")
    else:
        st.warning("⚠️ 訪問先を選択してください")

    # ========================================
    # ルート計算
    # ========================================

    st.subheader("2️⃣ ルート最適化")

    if len(selected_point_names) > 0 and st.button("🚀 最適ルートを計算する", type="primary", use_container_width=True):
        all_locations = [
            (O2_HONSHA["lat"], O2_HONSHA["lon"]),
            (SHACHO_HOME["lat"], SHACHO_HOME["lon"]),
        ]
        for idx, row in selected_df.iterrows():
            all_locations.append((row["lat"], row["lon"]))

        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(progress, message):
            progress_bar.progress(progress)
            status_text.text(message)

        full_time_matrix, error = create_distance_matrix_google_batched(
            tuple(all_locations), api_key, progress_callback=update_progress
        )

        progress_bar.empty()
        status_text.empty()

        if error:
            st.error(f"❌ Google APIエラー: {error}")
        elif full_time_matrix:
            with st.spinner("Global TSP & Time Slicing で最適化中..."):
                # 全体TSP → 時間による日程分割（地理的に近い場所は同じ日に）
                day_routes_converted = global_tsp_time_slice_allocation(
                    visit_df=selected_df,
                    time_matrix_all=full_time_matrix,
                    o2_idx=0,
                    shacho_idx=1,
                    name_col=name_col,
                    num_days=num_days
                )

                # Gap Filling最適化：他の日からO2本社・藤沢倉庫を移動
                day_routes_converted = optimize_gap_filling_moves(
                    day_routes=day_routes_converted,
                    visit_df=selected_df,
                    time_matrix_all=full_time_matrix,
                    o2_idx=0,
                    shacho_idx=1,
                    name_col=name_col
                )

            st.session_state.route_result = {
                "day_routes": day_routes_converted,
                "full_time_matrix": full_time_matrix,
                "selected_df": selected_df,
                "selected_point_names": selected_point_names,
                "name_col": name_col,
                "num_days": num_days
            }

    # ========================================
    # 結果表示
    # ========================================

    if st.session_state.route_result is not None:
        result = st.session_state.route_result
        day_routes = result["day_routes"]
        full_time_matrix = result["full_time_matrix"]
        result_selected_df = result["selected_df"]
        result_point_names = result["selected_point_names"]
        result_name_col = result["name_col"]
        result_num_days = result["num_days"]

        st.success(f"✅ {result_num_days}日間のルートが計算されました！")

        # メトリクス表示用の集計
        total_locations = len(result_point_names)
        total_travel_seconds_all = 0
        total_stay_minutes_all = 0
        all_calendar_text = []
        all_timetables = []

        for day_num in range(1, result_num_days + 1):
            day_idx = day_num - 1
            visit_indices = day_routes[day_idx] if day_idx < len(day_routes) else []

            if visit_indices:
                timetable_df, calendar_text, metrics = create_day_timetable(
                    day_num, visit_indices, result_selected_df, full_time_matrix,
                    o2_idx=0, shacho_idx=1, name_col=result_name_col, api_key=api_key
                )
                total_travel_seconds_all += metrics["total_travel_seconds"]
                total_stay_minutes_all += metrics["total_stay_minutes"]
                all_calendar_text.append(calendar_text)
                all_timetables.append((day_num, timetable_df, metrics))

        # メトリクス表示
        st.subheader("📊 サマリー")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("訪問件数", f"{total_locations}件")
        with col2:
            st.metric("総移動時間", format_duration(total_travel_seconds_all))
        with col3:
            st.metric("総滞在時間", f"{total_stay_minutes_all}分")
        with col4:
            total_hours = (total_travel_seconds_all / 3600) + (total_stay_minutes_all / 60)
            st.metric("総所要時間", f"{total_hours:.1f}時間")

        # 時間超過チェック（休憩時間を控除した実労働時間で判定）
        # 休憩時間 = 昼休憩60分 × 日数
        break_hours = (LUNCH_DURATION / 60) * result_num_days
        # 実労働時間 = 総所要時間 - 休憩時間
        actual_work_hours = total_hours - break_hours
        # 定時 = 8時間 × 日数
        limit_hours = WORK_HOURS_PER_DAY * result_num_days

        if actual_work_hours > limit_hours:
            over_hours = actual_work_hours - limit_hours
            st.warning(f"⚠️ **定時（{WORK_HOURS_PER_DAY:.0f}時間/日）を超過しています**\n\n"
                      f"総拘束時間: {total_hours:.1f}時間 - 休憩時間: {break_hours:.1f}時間 = 実労働時間: {actual_work_hours:.1f}時間\n\n"
                      f"定時を **約 {over_hours:.1f} 時間** 超過しています。\n"
                      f"早出・残業で調整するか、日数を増やしてください。")
        else:
            margin = limit_hours - actual_work_hours
            st.success(f"✅ 定時（{WORK_HOURS_PER_DAY:.0f}時間/日）以内に収まっています。\n\n"
                      f"実労働時間: {actual_work_hours:.1f}時間（休憩{break_hours:.1f}時間控除後）、余裕: {margin:.1f}時間")

        # 各日のタイムテーブル
        for day_num, timetable_df, metrics in all_timetables:
            st.subheader(f"📅 Day {day_num}")

            day_idx = day_num - 1
            visit_indices = day_routes[day_idx] if day_idx < len(day_routes) else []
            # visit_dfから直接名前を取得
            day_visits = []
            for i in visit_indices:
                if result_name_col and i < len(result_selected_df):
                    day_visits.append(result_selected_df.iloc[i][result_name_col])
                else:
                    day_visits.append(f"訪問先{i + 1}")
            st.write(f"**訪問先 ({len(visit_indices)}件):** {' → '.join(day_visits)}")

            # 終了時刻チェック
            end_time = metrics["end_time"]
            if end_time.hour >= 20:
                st.error(f"🚨 終了時刻が{format_time(end_time)}です！日数を増やすことを検討してください。")
            elif end_time.hour >= 18:
                st.warning(f"⚠️ 終了時刻が{format_time(end_time)}です（目安18:00超過）")

            # 列の並び順を整理
            column_order = ["順番", "到着時刻", "出発時刻", "滞在時間(分)", "移動時間(分)", "待機時間(分)", "場所名", "備考"]
            existing_cols = [c for c in column_order if c in timetable_df.columns]
            timetable_df = timetable_df[existing_cols]
            st.dataframe(timetable_df, use_container_width=True)

        # ========================================
        # 手動調整UI
        # ========================================
        st.markdown("---")
        st.subheader("🛠️ スケジュール手動調整")
        st.info("訪問先を別の日に移動できます。移動後は自動的にルート順序が再最適化されます。")

        # 各日の訪問先名を取得（visit_dfから直接取得）
        day_visit_names = {}
        day_visit_name_to_idx = {}
        for day_idx in range(result_num_days):
            visit_indices = day_routes[day_idx] if day_idx < len(day_routes) else []
            names = []
            name_to_idx = {}
            for idx in visit_indices:
                # result_selected_dfから直接名前を取得
                if result_name_col and idx < len(result_selected_df):
                    name = result_selected_df.iloc[idx][result_name_col]
                else:
                    name = f"訪問先{idx + 1}"
                names.append(name)
                name_to_idx[name] = idx
            day_visit_names[day_idx] = names
            day_visit_name_to_idx[day_idx] = name_to_idx

        # 2日間の場合の移動UI
        if result_num_days >= 2:
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("#### Day 2 → Day 1 へ移動")
                day2_names = day_visit_names.get(1, [])
                if day2_names:
                    move_to_day1 = st.multiselect(
                        "Day 2 から移動する訪問先:",
                        options=day2_names,
                        default=[],
                        key="move_to_day1"
                    )
                    if st.button("⬆️ Day 1 に移動", key="btn_move_to_day1", use_container_width=True):
                        if move_to_day1:
                            # 移動処理
                            new_day_routes = [list(r) for r in day_routes]
                            for name in move_to_day1:
                                idx = day_visit_name_to_idx[1].get(name)
                                if idx is not None and idx in new_day_routes[1]:
                                    new_day_routes[1].remove(idx)
                                    new_day_routes[0].append(idx)

                            # 両日を再最適化（きたえるーむを最後尾に配置）
                            new_day_routes[0] = reoptimize_day_route(
                                new_day_routes[0], full_time_matrix, shacho_idx=1,
                                visit_df=result_selected_df, name_col=result_name_col
                            )
                            new_day_routes[1] = reoptimize_day_route(
                                new_day_routes[1], full_time_matrix, shacho_idx=1,
                                visit_df=result_selected_df, name_col=result_name_col
                            )

                            # session_state を更新
                            st.session_state.route_result["day_routes"] = new_day_routes
                            st.rerun()
                        else:
                            st.warning("移動する訪問先を選択してください")
                else:
                    st.write("Day 2 に訪問先がありません")

            with col_right:
                st.markdown("#### Day 1 → Day 2 へ移動")
                day1_names = day_visit_names.get(0, [])
                if day1_names:
                    move_to_day2 = st.multiselect(
                        "Day 1 から移動する訪問先:",
                        options=day1_names,
                        default=[],
                        key="move_to_day2"
                    )
                    if st.button("⬇️ Day 2 に移動", key="btn_move_to_day2", use_container_width=True):
                        if move_to_day2:
                            # 移動処理
                            new_day_routes = [list(r) for r in day_routes]
                            for name in move_to_day2:
                                idx = day_visit_name_to_idx[0].get(name)
                                if idx is not None and idx in new_day_routes[0]:
                                    new_day_routes[0].remove(idx)
                                    new_day_routes[1].append(idx)

                            # 両日を再最適化（きたえるーむを最後尾に配置）
                            new_day_routes[0] = reoptimize_day_route(
                                new_day_routes[0], full_time_matrix, shacho_idx=1,
                                visit_df=result_selected_df, name_col=result_name_col
                            )
                            new_day_routes[1] = reoptimize_day_route(
                                new_day_routes[1], full_time_matrix, shacho_idx=1,
                                visit_df=result_selected_df, name_col=result_name_col
                            )

                            # session_state を更新
                            st.session_state.route_result["day_routes"] = new_day_routes
                            st.rerun()
                        else:
                            st.warning("移動する訪問先を選択してください")
                else:
                    st.write("Day 1 に訪問先がありません")

        # 3日以上の場合の汎用移動UI
        if result_num_days >= 3:
            st.markdown("#### 任意の日程間で移動")
            col_from, col_to = st.columns(2)

            with col_from:
                from_day = st.selectbox(
                    "移動元の日程:",
                    options=list(range(1, result_num_days + 1)),
                    format_func=lambda x: f"Day {x}",
                    key="from_day"
                )

            with col_to:
                to_day_options = [d for d in range(1, result_num_days + 1) if d != from_day]
                to_day = st.selectbox(
                    "移動先の日程:",
                    options=to_day_options,
                    format_func=lambda x: f"Day {x}",
                    key="to_day"
                )

            from_day_idx = from_day - 1
            from_names = day_visit_names.get(from_day_idx, [])

            if from_names:
                move_items = st.multiselect(
                    f"Day {from_day} から移動する訪問先:",
                    options=from_names,
                    default=[],
                    key="move_items_generic"
                )

                if st.button(f"🔄 Day {to_day} に移動", key="btn_move_generic", use_container_width=True):
                    if move_items:
                        to_day_idx = to_day - 1
                        new_day_routes = [list(r) for r in day_routes]

                        for name in move_items:
                            idx = day_visit_name_to_idx[from_day_idx].get(name)
                            if idx is not None and idx in new_day_routes[from_day_idx]:
                                new_day_routes[from_day_idx].remove(idx)
                                new_day_routes[to_day_idx].append(idx)

                        # 両日を再最適化（きたえるーむを最後尾に配置）
                        new_day_routes[from_day_idx] = reoptimize_day_route(
                            new_day_routes[from_day_idx], full_time_matrix, shacho_idx=1,
                            visit_df=result_selected_df, name_col=result_name_col
                        )
                        new_day_routes[to_day_idx] = reoptimize_day_route(
                            new_day_routes[to_day_idx], full_time_matrix, shacho_idx=1,
                            visit_df=result_selected_df, name_col=result_name_col
                        )

                        st.session_state.route_result["day_routes"] = new_day_routes
                        st.rerun()
                    else:
                        st.warning("移動する訪問先を選択してください")
            else:
                st.write(f"Day {from_day} に訪問先がありません")

        # リセットボタン
        st.markdown("---")
        if st.button("🔄 自動計算結果にリセット", key="btn_reset"):
            # 再計算
            with st.spinner("ルートを再計算中..."):
                day_routes_reset = global_tsp_time_slice_allocation(
                    visit_df=result_selected_df,
                    time_matrix_all=full_time_matrix,
                    o2_idx=0,
                    shacho_idx=1,
                    name_col=result_name_col,
                    num_days=result_num_days
                )
                # Gap Filling最適化：他の日からO2本社・藤沢倉庫を移動
                day_routes_reset = optimize_gap_filling_moves(
                    day_routes=day_routes_reset,
                    visit_df=result_selected_df,
                    time_matrix_all=full_time_matrix,
                    o2_idx=0,
                    shacho_idx=1,
                    name_col=result_name_col
                )
            st.session_state.route_result["day_routes"] = day_routes_reset
            st.rerun()

        # カレンダー用テキスト出力 + CSVダウンロード（コンパクト）
        st.subheader("📋 カレンダー用テキスト（コピー用）")

        # CSVダウンロードボタンを小さく右寄せで配置
        if all_timetables:
            all_data = []
            for day_num, timetable_df, _ in all_timetables:
                timetable_df = timetable_df.copy()
                timetable_df.insert(0, "日程", f"Day {day_num}")
                all_data.append(timetable_df)

            combined_df = pd.concat(all_data, ignore_index=True)
            csv_data = combined_df.to_csv(index=False, encoding="utf-8-sig")

            col_text, col_btn = st.columns([4, 1])
            with col_btn:
                st.download_button(
                    label="📥 CSV",
                    data=csv_data,
                    file_name=f"schedule_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    help="スケジュールをCSVでダウンロード"
                )

        full_calendar = "\n\n".join(all_calendar_text)
        # 全文表示：行数に基づいて高さを動的に計算（1行約22px + 余白）
        line_count = full_calendar.count('\n') + 1
        dynamic_height = max(200, line_count * 22 + 50)
        st.text_area("", full_calendar, height=dynamic_height)

        # ========================================
        # ドライバー向けナビリンク
        # ========================================
        st.subheader("🚗 ナビで開く（タップで案内開始）")
        st.info("各訪問先をタップするとGoogleマップのナビが起動します")

        for day_num in range(1, result_num_days + 1):
            day_idx = day_num - 1
            visit_indices = day_routes[day_idx] if day_idx < len(day_routes) else []

            with st.expander(f"📅 Day {day_num} のナビリンク", expanded=False):
                # O2本社
                o2_nav_url = f"https://www.google.com/maps/dir/?api=1&destination={O2_HONSHA['lat']},{O2_HONSHA['lon']}&travelmode=driving"
                st.markdown(f"**1. {O2_HONSHA['name']}（出発）** - [📍 ナビを開く]({o2_nav_url})")

                # 社長宅
                shacho_nav_url = f"https://www.google.com/maps/dir/?api=1&destination={SHACHO_HOME['lat']},{SHACHO_HOME['lon']}&travelmode=driving"
                st.markdown(f"**2. {SHACHO_HOME['name']}（ピックアップ）** - [📍 ナビを開く]({shacho_nav_url})")

                # 訪問先
                nav_order = 3
                for i in visit_indices:
                    if i < len(result_selected_df):
                        row = result_selected_df.iloc[i]
                        name = row[result_name_col] if result_name_col else f"訪問先{i+1}"
                        lat = row["lat"]
                        lon = row["lon"]
                        nav_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=driving"
                        st.markdown(f"**{nav_order}. {name}** - [📍 ナビを開く]({nav_url})")
                        nav_order += 1

                # 社長宅（送り届け）
                shacho_drop_url = f"https://www.google.com/maps/dir/?api=1&destination={SHACHO_HOME['lat']},{SHACHO_HOME['lon']}&travelmode=driving"
                st.markdown(f"**{nav_order}. {SHACHO_HOME['name']}（送り届け）** - [📍 ナビを開く]({shacho_drop_url})")
                nav_order += 1

                # O2本社（帰着）
                o2_return_url = f"https://www.google.com/maps/dir/?api=1&destination={O2_HONSHA['lat']},{O2_HONSHA['lon']}&travelmode=driving"
                st.markdown(f"**{nav_order}. {O2_HONSHA['name']}（帰着）** - [📍 ナビを開く]({o2_return_url})")

        # 地図表示
        st.subheader("🗺️ 全日程ルート地図")

        all_lats = [O2_HONSHA["lat"], SHACHO_HOME["lat"]] + result_selected_df["lat"].tolist()
        all_lons = [O2_HONSHA["lon"], SHACHO_HOME["lon"]] + result_selected_df["lon"].tolist()
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)

        m = folium.Map(location=[center_lat, center_lon], zoom_start=9)

        folium.Marker(
            location=[O2_HONSHA["lat"], O2_HONSHA["lon"]],
            popup=f"🏢 {O2_HONSHA['name']}",
            icon=folium.Icon(color="green")
        ).add_to(m)

        folium.Marker(
            location=[SHACHO_HOME["lat"], SHACHO_HOME["lon"]],
            popup=f"🏠 {SHACHO_HOME['name']}",
            icon=folium.Icon(color="purple")
        ).add_to(m)

        for day_idx, visit_indices in enumerate(day_routes):
            if not visit_indices:
                continue

            color = ROUTE_COLORS[day_idx % len(ROUTE_COLORS)]
            day_num = day_idx + 1

            # ルート描画
            poly, _ = get_route_polyline(
                (O2_HONSHA["lat"], O2_HONSHA["lon"]),
                (SHACHO_HOME["lat"], SHACHO_HOME["lon"]),
                api_key
            )
            if poly:
                folium.PolyLine(locations=poly, color=color, weight=3, opacity=0.7).add_to(m)

            if visit_indices:
                first_visit = result_selected_df.iloc[visit_indices[0]]
                poly, _ = get_route_polyline(
                    (SHACHO_HOME["lat"], SHACHO_HOME["lon"]),
                    (first_visit["lat"], first_visit["lon"]),
                    api_key
                )
                if poly:
                    folium.PolyLine(locations=poly, color=color, weight=3, opacity=0.7).add_to(m)

                for i in range(len(visit_indices) - 1):
                    from_row = result_selected_df.iloc[visit_indices[i]]
                    to_row = result_selected_df.iloc[visit_indices[i + 1]]
                    poly, _ = get_route_polyline(
                        (from_row["lat"], from_row["lon"]),
                        (to_row["lat"], to_row["lon"]),
                        api_key
                    )
                    if poly:
                        folium.PolyLine(locations=poly, color=color, weight=3, opacity=0.7).add_to(m)

                last_visit = result_selected_df.iloc[visit_indices[-1]]
                poly, _ = get_route_polyline(
                    (last_visit["lat"], last_visit["lon"]),
                    (SHACHO_HOME["lat"], SHACHO_HOME["lon"]),
                    api_key
                )
                if poly:
                    folium.PolyLine(locations=poly, color=color, weight=3, opacity=0.7).add_to(m)

            poly, _ = get_route_polyline(
                (SHACHO_HOME["lat"], SHACHO_HOME["lon"]),
                (O2_HONSHA["lat"], O2_HONSHA["lon"]),
                api_key
            )
            if poly:
                folium.PolyLine(locations=poly, color=color, weight=3, opacity=0.7).add_to(m)

            for order, visit_idx in enumerate(visit_indices):
                lat = result_selected_df.iloc[visit_idx]["lat"]
                lon = result_selected_df.iloc[visit_idx]["lon"]
                point_name = result_point_names[visit_idx]

                folium.Marker(
                    location=[lat, lon],
                    popup=f"Day{day_num}-{order+1}: {point_name}",
                    icon=folium.DivIcon(html=f'<div style="font-size: 9pt; color: white; background-color: {color}; border-radius: 50%; width: 22px; height: 22px; text-align: center; line-height: 22px;">{order+1}</div>')
                ).add_to(m)

        st_folium(m, width=None, height=500, key="result_map")

        # 凡例
        st.write("**凡例:**")
        legend_items = []
        for day_idx in range(result_num_days):
            color = ROUTE_COLORS[day_idx % len(ROUTE_COLORS)]
            legend_items.append(f"Day {day_idx + 1}: {color}")
        st.write(" | ".join(legend_items))

elif map_df is not None:
    st.warning("有効な緯度・経度データがありません")
