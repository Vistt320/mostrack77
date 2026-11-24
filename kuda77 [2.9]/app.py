from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
import math
import urllib.request
import json
import time
import os
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'mostrack_secret_key_school_project_2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

# ==============================================================================
# УПОРЯДОЧЕННЫЙ СПИСОК ВСЕХ 24 СТАНЦИЙ ЗАМОСКВОРЕЦКОЙ ЛИНИИ (СЕВЕР -> ЮГ)
# ==============================================================================
LINE_NAME = "Замоскворецкая"
LINE_COLOR = "#10b981"

LINE_STATIONS = [
    {"name": "Ховрино", "lat": 55.8778, "lng": 37.4875},
    {"name": "Беломорская", "lat": 55.8647, "lng": 37.4764},
    {"name": "Речной вокзал", "lat": 55.8549, "lng": 37.4761},
    {"name": "Водный стадион", "lat": 55.8398, "lng": 37.4872},
    {"name": "Войковская", "lat": 55.8191, "lng": 37.4981},
    {"name": "Сокол", "lat": 55.8051, "lng": 37.5152},
    {"name": "Аэропорт", "lat": 55.8003, "lng": 37.5329},
    {"name": "Динамо", "lat": 55.7897, "lng": 37.5583},
    {"name": "Белорусская", "lat": 55.7770, "lng": 37.5821},
    {"name": "Маяковская", "lat": 55.7698, "lng": 37.5962},
    {"name": "Тверская", "lat": 55.7644, "lng": 37.6056},
    {"name": "Театральная", "lat": 55.7582, "lng": 37.6186},
    {"name": "Новокузнецкая", "lat": 55.7423, "lng": 37.6295},
    {"name": "Павелецкая", "lat": 55.7301, "lng": 37.6360},
    {"name": "Автозаводская", "lat": 55.7067, "lng": 37.6570},
    {"name": "Технопарк", "lat": 55.6940, "lng": 37.6644},
    {"name": "Коломенская", "lat": 55.6784, "lng": 37.6639},
    {"name": "Каширская", "lat": 55.6552, "lng": 37.6489},
    {"name": "Кантемировская", "lat": 55.6360, "lng": 37.6560},
    {"name": "Царицыно", "lat": 55.6214, "lng": 37.6692},
    {"name": "Орехово", "lat": 55.6105, "lng": 37.7011},
    {"name": "Домодедовская", "lat": 55.6111, "lng": 37.7183},
    {"name": "Красногвардейская", "lat": 55.6142, "lng": 37.7450},
    {"name": "Алма-Атинская", "lat": 55.6334, "lng": 37.7656}
]

STATIONS_BY_NAME = {s["name"]: s for s in LINE_STATIONS}
STATION_INDEX = {s["name"]: i for i, s in enumerate(LINE_STATIONS)}


def calc_walk_time(lat1, lng1, lat2, lng2):
    d_lat = (lat1 - lat2) * 111.0
    d_lng = (lng1 - lng2) * 64.0
    dist_km = math.hypot(d_lat, d_lng)
    if dist_km < 0.08:
        return 0.0
    return max(2.0, min(15.0, (dist_km / 4.5) * 60.0))


def build_metro_route(start_name, end_name, user_lat=None, user_lng=None):
    if start_name not in STATION_INDEX:
        start_name = "Красногвардейская"
    if end_name not in STATION_INDEX:
        end_name = start_name

    idx1 = STATION_INDEX[start_name]
    idx2 = STATION_INDEX[end_name]
    st_start = STATIONS_BY_NAME[start_name]

    walk_to_metro_min = 0.0
    if user_lat is not None and user_lng is not None:
        walk_to_metro_min = calc_walk_time(user_lat, user_lng, st_start["lat"], st_start["lng"])

    stops_count = abs(idx1 - idx2)
    metro_time_min = stops_count * 2.5

    if stops_count == 0:
        segments = []
        if walk_to_metro_min >= 2.0:
            instr = (
                f"Пройдите к входу м. <strong>«{start_name}»</strong> (~{round(walk_to_metro_min)} мин), "
                f"поездка в вагоне не требуется — объект рядом с вашей станцией."
            )
        else:
            instr = f"Вы уже на станции <strong>«{start_name}»</strong>! Поездка на метро не требуется — объект в пешей доступности."
    else:
        step = 1 if idx1 < idx2 else -1
        direction = "Алма-Атинской" if idx1 < idx2 else "Ховрино"
        coords = [[LINE_STATIONS[i]["lat"], LINE_STATIONS[i]["lng"]] for i in range(idx1, idx2 + step, step)]
        segments = [{
            "line": LINE_NAME,
            "color": LINE_COLOR,
            "coords": coords
        }]
        pre_walk = f"Дойдите до м. <strong>«{start_name}»</strong> (~{round(walk_to_metro_min)} мин), затем спуститесь в метро. " if walk_to_metro_min >= 2.0 else ""
        instr = (
            f"{pre_walk}Садитесь на ст. <strong>«{start_name}»</strong> (Замоскворецкая линия) и поездом в сторону ст. "
            f"<strong>«{direction}»</strong> проедьте <strong>{stops_count} ост. (~{round(metro_time_min)} мин)</strong> "
            f"до ст. <strong>«{end_name}»</strong>."
        )

    return {
        "walk_to_metro_min": round(walk_to_metro_min, 1),
        "time_min": round(metro_time_min, 1),
        "stops_count": stops_count,
        "segments": segments,
        "instructions": instr
    }


# ==============================================================================
# БАЗА ДАННЫХ, НАСТРОЙКИ И АВТОРИЗАЦИЯ
# ==============================================================================
def get_db_connection():
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'kuda77.db'))
    conn.execute('PRAGMA foreign_keys = ON;')
    conn.row_factory = sqlite3.Row
    return conn


def get_settings_dict():
    conn = get_db_connection()
    rows = conn.execute('SELECT key, value FROM site_settings').fetchall()
    conn.close()
    res = {
        'metro_fare': '87',
        'bus_fare': '80',
        'weather_source': 'open_meteo',
        'site_title': 'MosTrack',
        'welcome_text': 'Умный AI-навигатор по Замоскворецкой линии Москвы с реальным расчётом маршрутов, бюджета и льгот.'
    }
    for r in rows:
        res[r['key']] = r['value']
    return res


def get_explorer_rank(visited_count):
    if visited_count == 0:
        return "Новичок ветки"
    if visited_count <= 3:
        return "Первооткрыватель"
    if visited_count <= 8:
        return "Путешественник Москвы"
    if visited_count <= 16:
        return "Знаток Замоскворецкой"
    if visited_count <= 30:
        return "Мастер маршрутов"
    return "Легенда Зелёной линии"


def get_current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    conn = get_db_connection()
    user = conn.execute(
        'SELECT id, username, role, display_name, home_station, is_student, has_pushkin FROM users WHERE id = ?',
        (uid,)
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            return jsonify({"ok": False, "message": "Требуется вход в аккаунт"}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        u = get_current_user()
        if not u or u['role'] != 'admin':
            return jsonify({"ok": False, "message": "Доступ только для разработчика (admin)"}), 403
        return f(*args, **kwargs)
    return decorated


# ==============================================================================
# ПОГОДНЫЙ ДВИЖОК (Open-Meteo / wttr.in / Демо-режимы)
# ==============================================================================
WEATHER_CACHE = {"ts": 0, "source": "", "data": None}

def get_moscow_weather():
    settings = get_settings_dict()
    source = settings.get('weather_source', 'open_meteo')
    weekday = datetime.now().weekday()
    is_monday = (weekday == 0)

    if source == 'demo_rain':
        return {"temp": 11, "desc": "Дождь (Демо)", "icon": "\uD83C\uDF27\uFE0F", "is_bad_weather": True, "weekday": weekday, "is_monday": is_monday, "source": source}
    if source == 'demo_snow':
        return {"temp": -14, "desc": "Мороз/Снег (Демо)", "icon": "\u2744\uFE0F", "is_bad_weather": True, "weekday": weekday, "is_monday": is_monday, "source": source}
    if source == 'demo_clear':
        return {"temp": 19, "desc": "Солнечно (Демо)", "icon": "\u2600\uFE0F", "is_bad_weather": False, "weekday": weekday, "is_monday": is_monday, "source": source}

    now = time.time()
    if WEATHER_CACHE["data"] and WEATHER_CACHE["source"] == source and (now - WEATHER_CACHE["ts"] < 600):
        return WEATHER_CACHE["data"]

    default_w = {"temp": 2, "desc": "Облачно", "icon": "\u26C5", "is_bad_weather": False, "weekday": weekday, "is_monday": is_monday, "source": source}

    try:
        if source == 'wttr':
            url = "https://wttr.in/Moscow?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "MosTrackApp/2.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                cur = raw.get("current_condition", [{}])[0]
                temp = int(cur.get("temp_C", 2))
                w_desc = cur.get("weatherDesc", [{}])[0].get("value", "").lower()
                bad = ("rain" in w_desc) or ("snow" in w_desc) or ("shower" in w_desc) or (temp <= -12)
                icon = "\uD83C\uDF27\uFE0F" if "rain" in w_desc else ("\u2744\uFE0F" if "snow" in w_desc else "\u26C5")
                desc = "Дождь" if "rain" in w_desc else ("Снег" if "snow" in w_desc else "Облачно")
                data = {"temp": temp, "desc": desc, "icon": icon, "is_bad_weather": bad, "weekday": weekday, "is_monday": is_monday, "source": source}
                WEATHER_CACHE["ts"] = now
                WEATHER_CACHE["source"] = source
                WEATHER_CACHE["data"] = data
                return data
        else:
            url = "https://api.open-meteo.com/v1/forecast?latitude=55.7558&longitude=37.6173&current=temperature_2m,weather_code,precipitation"
            req = urllib.request.Request(url, headers={"User-Agent": "MosTrackApp/2.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                cur = raw.get("current", {})
                temp = round(cur.get("temperature_2m", 2))
                code = cur.get("weather_code", 2)
                precip = cur.get("precipitation", 0)
                desc, icon, bad = "Ясно", "\u2600\uFE0F", False
                if code in (1, 2, 3):
                    desc, icon = "Облачно", "\u26C5"
                elif code in (45, 48):
                    desc, icon = "Туман", "\uD83C\uDF2B\uFE0F"
                elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82) or (precip > 0.1 and temp > 1):
                    desc, icon, bad = "Дождь", "\uD83C\uDF27\uFE0F", True
                elif code in (71, 73, 75, 77, 85, 86) or (precip > 0.1 and temp <= 1):
                    desc, icon, bad = "Снег", "\u2744\uFE0F", True
                elif code >= 95:
                    desc, icon, bad = "Гроза", "\u26C8\uFE0F", True
                if temp <= -12:
                    bad = True
                data = {"temp": temp, "desc": desc, "icon": icon, "is_bad_weather": bad, "weekday": weekday, "is_monday": is_monday, "source": source}
                WEATHER_CACHE["ts"] = now
                WEATHER_CACHE["source"] = source
                WEATHER_CACHE["data"] = data
                return data
    except Exception:
        return default_w


# ==============================================================================
# ОСНОВНЫЕ МАРШРУТЫ ПРИЛОЖЕНИЯ
# ==============================================================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/public_config')
def api_public_config():
    s = get_settings_dict()
    return jsonify({
        "site_title": s.get("site_title", "MosTrack"),
        "welcome_text": s.get("welcome_text", ""),
        "metro_fare": int(s.get("metro_fare", 87)),
        "bus_fare": int(s.get("bus_fare", 80)),
        "weather_source": s.get("weather_source", "open_meteo")
    })


@app.route('/api/weather')
def api_weather():
    return jsonify(get_moscow_weather())


@app.route('/api/stations')
def get_stations():
    return jsonify({
        "line": LINE_NAME,
        "color": LINE_COLOR,
        "stations": LINE_STATIONS
    })


@app.route('/api/places')
def get_places():
    budget = int(request.args.get('budget', 5000))
    time_limit = float(request.args.get('time', 12.0))
    student_filter = request.args.get('student', 'false').lower() == 'true'
    pushkin_only = request.args.get('pushkin', 'false').lower() == 'true'
    indoor_only = request.args.get('indoor', 'false').lower() == 'true'
    category_filter = request.args.get('category', 'all')
    query_str = request.args.get('q', '').strip().lower()
    user_station_name = request.args.get('station', 'Красногвардейская')

    u_lat = request.args.get('lat')
    u_lng = request.args.get('lng')
    user_lat = float(u_lat) if u_lat else None
    user_lng = float(u_lng) if u_lng else None

    if user_station_name not in STATIONS_BY_NAME:
        user_station_name = 'Красногвардейская'

    settings = get_settings_dict()
    metro_fare = int(settings.get('metro_fare', 87))
    weather = get_moscow_weather()
    today_wd = weather["weekday"]

    cur_user = get_current_user()
    fav_ids = set()
    visited_ids = set()

    conn = get_db_connection()
    if cur_user:
        fav_rows = conn.execute('SELECT place_id FROM favorites WHERE user_id = ?', (cur_user['id'],)).fetchall()
        fav_ids = set(r['place_id'] for r in fav_rows)
        vis_rows = conn.execute('SELECT place_id FROM visited_places WHERE user_id = ?', (cur_user['id'],)).fetchall()
        visited_ids = set(r['place_id'] for r in vis_rows)

    rev_stats = {}
    for rs in conn.execute('SELECT place_id, AVG(rating) AS avg_r, COUNT(*) AS cnt FROM reviews GROUP BY place_id').fetchall():
        rev_stats[rs['place_id']] = (round(rs['avg_r'], 1), rs['cnt'])

    rows = conn.execute("SELECT * FROM places WHERE status = 'approved'").fetchall()
    conn.close()

    filtered = []
    for r in rows:
        p = dict(r)

        if indoor_only and p['indoor'] != 1:
            continue
        if category_filter != 'all' and p['category'] != category_filter:
            continue
        if query_str:
            haystack = f"{p['title']} {p['description']} {p['metro']} {p['category']}".lower()
            if query_str not in haystack:
                continue
        if pushkin_only and p['pushkin_card'] != 1:
            continue

        has_student_discount = (p['price_student'] < p['price_adult']) or (p['pushkin_card'] == 1) or (p['price_adult'] == 0)
        if student_filter and not has_student_discount:
            continue

        if pushkin_only and p['pushkin_card'] == 1:
            ticket_price = 0
        elif student_filter:
            ticket_price = p['price_student']
        else:
            ticket_price = p['price_adult']

        if ticket_price > budget:
            continue

        dest_station_name = p['metro'] if p['metro'] in STATIONS_BY_NAME else user_station_name
        metro_route = build_metro_route(user_station_name, dest_station_name, user_lat, user_lng)
        dest_st = STATIONS_BY_NAME[dest_station_name]

        walk_from_metro_min = max(2.0, calc_walk_time(p['lat'], p['lng'], dest_st['lat'], dest_st['lng']))
        total_min = metro_route["walk_to_metro_min"] + metro_route["time_min"] + walk_from_metro_min + (p['time_needed'] * 60.0)
        total_time_hours = round(total_min / 60.0, 1)

        if total_time_hours > time_limit:
            continue

        transport_cost = 0 if metro_route["stops_count"] == 0 else metro_fare
        avg_r, rev_cnt = rev_stats.get(p['id'], (0.0, 0))

        p['calculated_price'] = ticket_price
        p['transport_cost'] = transport_cost
        p['total_cost'] = ticket_price + transport_cost
        p['walk_to_metro_min'] = round(metro_route["walk_to_metro_min"])
        p['metro_time_min'] = round(metro_route["time_min"])
        p['walk_time_min'] = round(walk_from_metro_min)
        p['total_time_hours'] = total_time_hours
        p['stops_count'] = metro_route["stops_count"]
        p['metro_segments'] = metro_route["segments"]
        p['metro_instructions'] = metro_route["instructions"]
        p['has_student_discount'] = (p['price_student'] < p['price_adult'])
        p['is_closed_today'] = (p['closed_weekday'] != -1 and p['closed_weekday'] == today_wd)
        p['is_favorite'] = (p['id'] in fav_ids)
        p['is_visited'] = (p['id'] in visited_ids)
        p['avg_rating'] = avg_r
        p['reviews_count'] = rev_cnt

        filtered.append(p)

    filtered.sort(key=lambda x: (x['is_closed_today'], x['walk_to_metro_min'] + x['metro_time_min'] + x['walk_time_min'], x['total_time_hours']))
    return jsonify(filtered)


# ==============================================================================
# ПОЛНОЦЕННЫЙ МНОГОВАРИАНТНЫЙ КОНСТРУКТОР МАРШРУТОВ ДНЯ
# ==============================================================================
@app.route('/api/plan_day')
def plan_day():
    budget = int(request.args.get('budget', 5000))
    time_limit = float(request.args.get('time', 4.0))
    student_filter = request.args.get('student', 'false').lower() == 'true'
    pushkin_only = request.args.get('pushkin', 'false').lower() == 'true'
    indoor_only = request.args.get('indoor', 'false').lower() == 'true'
    user_station = request.args.get('station', 'Красногвардейская')
    mode = request.args.get('mode', 'balanced')  # balanced, culture, parks, surprise
    variant = int(request.args.get('variant', 0))

    u_lat = request.args.get('lat')
    u_lng = request.args.get('lng')
    user_lat = float(u_lat) if u_lat else None
    user_lng = float(u_lng) if u_lng else None

    if user_station not in STATIONS_BY_NAME:
        user_station = 'Красногвардейская'

    settings = get_settings_dict()
    metro_fare = int(settings.get('metro_fare', 87))
    weather = get_moscow_weather()
    today_wd = weather["weekday"]

    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM places WHERE status = 'approved'").fetchall()
    conn.close()

    candidates = []
    for r in rows:
        p = dict(r)
        if indoor_only and p['indoor'] != 1:
            continue
        if p['closed_weekday'] != -1 and p['closed_weekday'] == today_wd:
            continue
        if pushkin_only and p['pushkin_card'] != 1:
            continue

        if mode == 'culture' and p['category'] not in ('Музей', 'Культура', 'История', 'Архитектура'):
            continue
        if mode == 'parks' and p['category'] not in ('Парк', 'Прогулка', 'Обзор'):
            continue

        if pushkin_only and p['pushkin_card'] == 1:
            t_price = 0
        elif student_filter:
            t_price = p['price_student']
        else:
            t_price = p['price_adult']

        if t_price > budget:
            continue

        p['eff_price'] = t_price
        p['saved'] = max(0, p['price_adult'] - t_price)
        candidates.append(p)

    if not candidates:
        return jsonify({"ok": False, "message": "Под выбранный режим и фильтры нет открытых мест. Попробуйте сменить стиль маршрута или увеличить бюджет/время."})

    def cat_group(c):
        if c in ('Музей', 'Культура', 'История'):
            return 'culture'
        if c in ('Еда', 'Обзор', 'Архитектура'):
            return 'leisure'
        return 'walk'

    max_minutes = time_limit * 60.0
    all_chains = []
    seen_sets = set()

    # Подготовка первых шагов (учитываем все доступные точки, отсортированные по дистанции/разнообразию)
    first_options = []
    for p in candidates:
        mr = build_metro_route(user_station, p['metro'], user_lat, user_lng)
        st_dest = STATIONS_BY_NAME.get(p['metro'], STATIONS_BY_NAME[user_station])
        wk = max(2.0, calc_walk_time(p['lat'], p['lng'], st_dest['lat'], st_dest['lng']))
        t_min = mr['walk_to_metro_min'] + mr['time_min'] + wk + p['time_needed'] * 60.0
        tr_c = 0 if mr['stops_count'] == 0 else metro_fare
        if t_min <= max_minutes and not (budget >= metro_fare and (p['eff_price'] + tr_c) > budget):
            first_options.append((t_min, p, mr, wk, tr_c))

    if not first_options:
        return jsonify({"ok": False, "message": "Не удалось подобрать ни одного места под это время/бюджет."})

    # В режиме «Сюрприз» перемешиваем кандидатов, иначе пробуем широкий срез (топ-25)
    if mode == 'surprise':
        random.shuffle(first_options)
    else:
        first_options.sort(key=lambda x: x[0])

    for t1, p1, mr1, wk1, tr1 in first_options[:25]:
        chain1 = [(p1, mr1, wk1, tr1, t1)]
        sc1 = 90 - (mr1['time_min'] + wk1) * 0.6 + (25 if p1['pushkin_card'] else 0)
        sig1 = tuple([p1['id']])
        if sig1 not in seen_sets:
            seen_sets.add(sig1)
            all_chains.append((sc1, chain1))

        # Ищем 2-ю точку
        second_cands = [p for p in candidates if p['id'] != p1['id']]
        if mode == 'surprise':
            random.shuffle(second_cands)

        added_2 = 0
        for p2 in second_cands:
            mr2 = build_metro_route(p1['metro'], p2['metro'])
            st2 = STATIONS_BY_NAME.get(p2['metro'], STATIONS_BY_NAME[p1['metro']])
            wk2 = max(2.0, calc_walk_time(p2['lat'], p2['lng'], st2['lat'], st2['lng']))
            seg2_min = mr2['time_min'] + wk2 + p2['time_needed'] * 60.0
            t2 = t1 + seg2_min
            if t2 > max_minutes:
                continue

            tr2 = 0 if mr2['stops_count'] == 0 else metro_fare
            tk12 = p1['eff_price'] + p2['eff_price']
            tc12 = tr1 + tr2
            if tk12 > budget or (budget >= metro_fare and (tk12 + tc12) > budget):
                continue

            div2 = 70 if cat_group(p2['category']) != cat_group(p1['category']) else 15
            chain2 = chain1 + [(p2, mr2, wk2, tr2, seg2_min)]
            sc2 = 240 + div2 - (mr1['time_min'] + mr2['time_min']) * 0.9 + (20 if p2['pushkin_card'] else 0)
            sig2 = tuple(sorted([p1['id'], p2['id']]))
            if sig2 not in seen_sets:
                seen_sets.add(sig2)
                all_chains.append((sc2, chain2))
                added_2 += 1

            # Ищем 3-ю точку
            if max_minutes - t2 >= 32:
                third_cands = [p for p in candidates if p['id'] not in (p1['id'], p2['id'])]
                for p3 in third_cands:
                    mr3 = build_metro_route(p2['metro'], p3['metro'])
                    st3 = STATIONS_BY_NAME.get(p3['metro'], STATIONS_BY_NAME[p2['metro']])
                    wk3 = max(2.0, calc_walk_time(p3['lat'], p3['lng'], st3['lat'], st3['lng']))
                    seg3_min = mr3['time_min'] + wk3 + p3['time_needed'] * 60.0
                    t3 = t2 + seg3_min
                    if t3 > max_minutes:
                        continue

                    tr3 = 0 if mr3['stops_count'] == 0 else metro_fare
                    tk123 = tk12 + p3['eff_price']
                    tc123 = tc12 + tr3
                    if tk123 > budget or (budget >= metro_fare and (tk123 + tc123) > budget):
                        continue

                    cats = {cat_group(p1['category']), cat_group(p2['category']), cat_group(p3['category'])}
                    chain3 = chain2 + [(p3, mr3, wk3, tr3, seg3_min)]
                    sc3 = 420 + len(cats) * 60 - (mr1['time_min'] + mr2['time_min'] + mr3['time_min']) * 1.0 + (20 if p3['pushkin_card'] else 0)
                    sig3 = tuple(sorted([p1['id'], p2['id'], p3['id']]))
                    if sig3 not in seen_sets:
                        seen_sets.add(sig3)
                        all_chains.append((sc3, chain3))
                        break
            if added_2 >= 4:
                break

    # Предпочитаем цепочки из 2-3 мест, если они есть
    multi_chains = [c for c in all_chains if len(c[1]) >= 2]
    pool = multi_chains if multi_chains else all_chains

    if mode != 'surprise':
        pool.sort(key=lambda x: x[0], reverse=True)

    # Берём топ-12 уникальных разнообразных маршрутов и выбираем по индексу variant
    top_pool = pool[:12]
    chosen_idx = variant % len(top_pool)
    chosen_chain = top_pool[chosen_idx][1]

    stops_out = []
    total_time_min = 0
    total_tickets = 0
    total_transport = 0
    total_saved = 0

    for idx, (p, mr, wk, tr_c, seg_min) in enumerate(chosen_chain):
        total_time_min += seg_min
        total_tickets += p['eff_price']
        total_transport += tr_c
        total_saved += p['saved']

        stops_out.append({
            "step": idx + 1,
            "id": p['id'],
            "title": p['title'],
            "category": p['category'],
            "metro": p['metro'],
            "lat": p['lat'],
            "lng": p['lng'],
            "image_url": p['image_url'],
            "price": p['eff_price'],
            "pushkin_card": p['pushkin_card'],
            "visit_min": round(p['time_needed'] * 60),
            "walk_to_metro_min": round(mr.get('walk_to_metro_min', 0)),
            "walk_min": round(wk),
            "metro_min": round(mr['time_min']),
            "stops_count": mr['stops_count'],
            "metro_segments": mr['segments'],
            "metro_instructions": mr['instructions'],
            "from_station": user_station if idx == 0 else chosen_chain[idx - 1][0]['metro'],
            "to_station": p['metro']
        })

    return jsonify({
        "ok": True,
        "mode": mode,
        "variant_index": chosen_idx + 1,
        "total_variants": len(top_pool),
        "start_station": user_station,
        "stops": stops_out,
        "total_time_hours": round(total_time_min / 60.0, 1),
        "total_tickets": total_tickets,
        "total_transport": total_transport,
        "total_cost": total_tickets + total_transport,
        "total_saved": total_saved,
        "weather": weather
    })


# ==============================================================================
# АККАУНТЫ, ЧЕК-ИНЫ, ОТЗЫВЫ, ИЗБРАННОЕ И МАРШРУТЫ
# ==============================================================================
@app.route('/api/me')
def api_me():
    u = get_current_user()
    if not u:
        return jsonify({"logged_in": False, "user": None, "favorites": [], "visited": [], "saved_routes": [], "rank": "Гость"})

    conn = get_db_connection()
    fav_places = conn.execute('''
        SELECT p.id, p.title, p.metro, p.category, p.lat, p.lng
        FROM favorites f JOIN places p ON p.id = f.place_id
        WHERE f.user_id = ? AND p.status = 'approved'
        ORDER BY f.created_at DESC
    ''', (u['id'],)).fetchall()

    vis_places = conn.execute('''
        SELECT p.id, p.title, p.metro, v.visited_at
        FROM visited_places v JOIN places p ON p.id = v.place_id
        WHERE v.user_id = ? AND p.status = 'approved'
        ORDER BY v.visited_at DESC
    ''', (u['id'],)).fetchall()

    routes_rows = conn.execute('''
        SELECT id, title, start_station, stops_json, total_time, total_cost, created_at
        FROM saved_routes WHERE user_id = ? ORDER BY created_at DESC
    ''', (u['id'],)).fetchall()

    total_approved = conn.execute("SELECT COUNT(*) FROM places WHERE status = 'approved'").fetchone()[0]
    conn.close()

    saved_routes = []
    for rr in routes_rows:
        item = dict(rr)
        try:
            item['stops'] = json.loads(item['stops_json'])
        except Exception:
            item['stops'] = []
        saved_routes.append(item)

    vis_list = [dict(x) for x in vis_places]
    return jsonify({
        "logged_in": True,
        "user": u,
        "favorites": [dict(x) for x in fav_places],
        "visited": vis_list,
        "total_places": total_approved,
        "rank": get_explorer_rank(len(vis_list)),
        "saved_routes": saved_routes
    })


@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    display_name = data.get('display_name', '').strip() or username

    if len(username) < 3 or len(password) < 4:
        return jsonify({"ok": False, "message": "Логин от 3 символов, пароль от 4 символов."}), 400

    conn = get_db_connection()
    if conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
        conn.close()
        return jsonify({"ok": False, "message": "Такой логин уже занят."}), 400

    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (username, password_hash, role, display_name, home_station, is_student, has_pushkin)
        VALUES (?, ?, 'user', ?, 'Красногвардейская', 1, 0)
    ''', (username, pw_hash, display_name))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    session['user_id'] = new_id
    return jsonify({"ok": True, "message": "Добро пожаловать в MosTrack!"})


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"ok": False, "message": "Неверный логин или пароль."}), 401

    session['user_id'] = user['id']
    return jsonify({"ok": True, "role": user['role']})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('user_id', None)
    return jsonify({"ok": True})


@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_profile_update():
    u = get_current_user()
    data = request.get_json() or {}
    home_station = data.get('home_station', u['home_station'])
    if home_station not in STATIONS_BY_NAME:
        home_station = u['home_station']
    is_student = 1 if data.get('is_student') else 0
    has_pushkin = 1 if data.get('has_pushkin') else 0
    display_name = data.get('display_name', u['display_name']).strip() or u['display_name']

    conn = get_db_connection()
    conn.execute('''
        UPDATE users SET home_station = ?, is_student = ?, has_pushkin = ?, display_name = ? WHERE id = ?
    ''', (home_station, is_student, has_pushkin, display_name, u['id']))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Настройки профиля сохранены!"})


@app.route('/api/favorites/toggle', methods=['POST'])
@login_required
def api_toggle_favorite():
    u = get_current_user()
    place_id = int((request.get_json() or {}).get('place_id', 0))
    conn = get_db_connection()
    ex = conn.execute('SELECT id FROM favorites WHERE user_id = ? AND place_id = ?', (u['id'], place_id)).fetchone()
    if ex:
        conn.execute('DELETE FROM favorites WHERE id = ?', (ex['id'],))
        added = False
    else:
        conn.execute('INSERT INTO favorites (user_id, place_id) VALUES (?, ?)', (u['id'], place_id))
        added = True
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "added": added})


@app.route('/api/visited/toggle', methods=['POST'])
@login_required
def api_toggle_visited():
    u = get_current_user()
    place_id = int((request.get_json() or {}).get('place_id', 0))
    conn = get_db_connection()
    ex = conn.execute('SELECT id FROM visited_places WHERE user_id = ? AND place_id = ?', (u['id'], place_id)).fetchone()
    if ex:
        conn.execute('DELETE FROM visited_places WHERE id = ?', (ex['id'],))
        visited = False
    else:
        conn.execute('INSERT INTO visited_places (user_id, place_id) VALUES (?, ?)', (u['id'], place_id))
        visited = True
    conn.commit()
    cnt = conn.execute('SELECT COUNT(*) FROM visited_places WHERE user_id = ?', (u['id'],)).fetchone()[0]
    conn.close()
    return jsonify({"ok": True, "visited": visited, "visited_count": cnt, "rank": get_explorer_rank(cnt)})


@app.route('/api/places/<int:place_id>/reviews', methods=['GET', 'POST'])
def api_place_reviews(place_id):
    conn = get_db_connection()
    if request.method == 'GET':
        rows = conn.execute('''
            SELECT r.id, r.user_id, r.rating, r.comment, r.created_at, u.display_name, u.username
            FROM reviews r JOIN users u ON u.id = r.user_id
            WHERE r.place_id = ?
            ORDER BY r.created_at DESC
        ''', (place_id,)).fetchall()
        conn.close()
        return jsonify([dict(x) for x in rows])

    u = get_current_user()
    if not u:
        conn.close()
        return jsonify({"ok": False, "message": "Войдите в аккаунт, чтобы оставить отзыв"}), 401

    data = request.get_json() or {}
    rating = max(1, min(5, int(data.get('rating', 5))))
    comment = data.get('comment', '').strip()
    if len(comment) < 2:
        conn.close()
        return jsonify({"ok": False, "message": "Напишите короткий отзыв или совет"}), 400

    conn.execute('INSERT INTO reviews (user_id, place_id, rating, comment) VALUES (?, ?, ?, ?)',
                 (u['id'], place_id, rating, comment))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Отзыв опубликован!"})


@app.route('/api/reviews/<int:review_id>', methods=['DELETE'])
@login_required
def api_delete_review(review_id):
    u = get_current_user()
    conn = get_db_connection()
    if u['role'] == 'admin':
        conn.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
    else:
        conn.execute('DELETE FROM reviews WHERE id = ? AND user_id = ?', (review_id, u['id']))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route('/api/routes/save', methods=['POST'])
@login_required
def api_save_route():
    u = get_current_user()
    data = request.get_json() or {}
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO saved_routes (user_id, title, start_station, stops_json, total_time, total_cost)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        u['id'],
        data.get('title', 'Маршрут по Замоскворецкой линии'),
        data.get('start_station', 'Красногвардейская'),
        json.dumps(data.get('stops', []), ensure_ascii=False),
        float(data.get('total_time', 1.0)),
        int(data.get('total_cost', 0))
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Маршрут сохранён в личный кабинет!"})


@app.route('/api/routes/<int:route_id>', methods=['DELETE'])
@login_required
def api_delete_route(route_id):
    u = get_current_user()
    conn = get_db_connection()
    conn.execute('DELETE FROM saved_routes WHERE id = ? AND user_id = ?', (route_id, u['id']))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route('/api/places/suggest', methods=['POST'])
@login_required
def api_suggest_place():
    u = get_current_user()
    data = request.get_json() or {}

    title = data.get('title', '').strip()
    if not title:
        return jsonify({"ok": False, "message": "Укажите название места"}), 400

    status = 'approved' if u['role'] == 'admin' else 'pending'

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO places (
            title, category, metro, lat, lng, price_adult, price_student, pushkin_card,
            time_needed, indoor, closed_weekday, image_url, description, walk_route_info,
            bus_route_info, bus_number, status, created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        title,
        data.get('category', 'Парк'),
        data.get('metro', 'Красногвардейская'),
        float(data.get('lat', 55.7558)),
        float(data.get('lng', 37.6173)),
        int(data.get('price_adult', 0)),
        int(data.get('price_student', 0)),
        1 if data.get('pushkin_card') else 0,
        float(data.get('time_needed', 0.5)),
        1 if data.get('indoor') else 0,
        int(data.get('closed_weekday', -1)),
        data.get('image_url', '').strip() or 'https://upload.wikimedia.org/wikipedia/commons/6/69/Red_Square_%289148926031%29.jpg',
        data.get('description', '').strip() or 'Интересная достопримечательность Москвы.',
        data.get('walk_route_info', '').strip() or 'Пешком от ближайшего выхода метро.',
        data.get('bus_route_info', '').strip() or 'Наземный транспорт от остановки рядом с метро.',
        data.get('bus_number', '').strip() or 'Пешком',
        status,
        u['id']
    ))
    conn.commit()
    conn.close()

    msg = "Место добавлено на карту!" if status == 'approved' else "Заявка отправлена разработчику на модерацию!"
    return jsonify({"ok": True, "message": msg, "status": status})


# ==============================================================================
# ЭКСКЛЮЗИВНАЯ ПАНЕЛЬ РАЗРАБОТЧИКА (ADMIN CMS & SQL ИНСПЕКТОР)
# ==============================================================================
@app.route('/api/upload_photo', methods=['POST'])
@login_required
def api_upload_photo():
    if 'file' not in request.files:
        return jsonify({"ok": False, "message": "Файл не выбран"}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({"ok": False, "message": "Пустое имя файла"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"ok": False, "message": "Разрешены только картинки (PNG, JPG, WEBP, GIF)"}), 400

    new_name = f"place_{int(time.time() * 1000)}{ext}"
    f.save(os.path.join(UPLOAD_FOLDER, new_name))
    return jsonify({"ok": True, "url": f"/static/uploads/{new_name}"})


@app.route('/api/admin/places', methods=['GET'])
@admin_required
def admin_get_places():
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT p.*, u.username AS creator_name
        FROM places p
        LEFT JOIN users u ON u.id = p.created_by
        ORDER BY CASE WHEN p.status = 'pending' THEN 0 ELSE 1 END, p.id DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/admin/places/<int:place_id>', methods=['PUT'])
@admin_required
def admin_update_place(place_id):
    data = request.get_json() or {}
    conn = get_db_connection()
    conn.execute('''
        UPDATE places SET
            title = ?, category = ?, metro = ?, lat = ?, lng = ?,
            price_adult = ?, price_student = ?, pushkin_card = ?, time_needed = ?,
            indoor = ?, closed_weekday = ?, image_url = ?, description = ?,
            walk_route_info = ?, bus_route_info = ?, bus_number = ?, status = ?
        WHERE id = ?
    ''', (
        data.get('title', '').strip(),
        data.get('category', 'Парк'),
        data.get('metro', 'Красногвардейская'),
        float(data.get('lat', 55.7558)),
        float(data.get('lng', 37.6173)),
        int(data.get('price_adult', 0)),
        int(data.get('price_student', 0)),
        1 if data.get('pushkin_card') else 0,
        float(data.get('time_needed', 0.5)),
        1 if data.get('indoor') else 0,
        int(data.get('closed_weekday', -1)),
        data.get('image_url', '').strip(),
        data.get('description', '').strip(),
        data.get('walk_route_info', '').strip(),
        data.get('bus_route_info', '').strip(),
        data.get('bus_number', '').strip() or 'Пешком',
        data.get('status', 'approved'),
        place_id
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Место успешно обновлено в SQL-базе!"})


@app.route('/api/admin/places/<int:place_id>/approve', methods=['POST'])
@admin_required
def admin_approve_place(place_id):
    conn = get_db_connection()
    conn.execute("UPDATE places SET status = 'approved' WHERE id = ?", (place_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Место одобрено и опубликовано на карте!"})


@app.route('/api/admin/places/<int:place_id>', methods=['DELETE'])
@admin_required
def admin_delete_place(place_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM places WHERE id = ?', (place_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "Место удалено из базы."})


@app.route('/api/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    conn = get_db_connection()
    if request.method == 'GET':
        rows = conn.execute('SELECT key, value, label FROM site_settings').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])

    data = request.get_json() or {}
    for k, v in data.items():
        conn.execute('UPDATE site_settings SET value = ? WHERE key = ?', (str(v), k))
    conn.commit()
    conn.close()
    WEATHER_CACHE["ts"] = 0
    return jsonify({"ok": True, "message": "Настройки сайта применены!"})


@app.route('/api/admin/sql/<table_name>')
@admin_required
def admin_sql_table(table_name):
    allowed_tables = {'places', 'users', 'favorites', 'visited_places', 'reviews', 'saved_routes', 'site_settings'}
    if table_name not in allowed_tables:
        return jsonify({"ok": False, "message": "Недопустимая таблица"}), 400

    conn = get_db_connection()
    if table_name == 'users':
        rows = conn.execute('SELECT id, username, role, display_name, home_station, is_student, has_pushkin, created_at FROM users').fetchall()
    else:
        rows = conn.execute(f'SELECT * FROM {table_name} LIMIT 200').fetchall()
    conn.close()

    if not rows:
        return jsonify({"ok": True, "columns": [], "rows": []})

    cols = list(rows[0].keys())
    return jsonify({"ok": True, "columns": cols, "rows": [dict(r) for r in rows]})


@app.route('/api/admin/users/<int:user_id>/role', methods=['POST'])
@admin_required
def admin_toggle_user_role(user_id):
    cur = get_current_user()
    if cur['id'] == user_id:
        return jsonify({"ok": False, "message": "Нельзя снять права с самого себя."}), 400
    data = request.get_json() or {}
    new_role = 'admin' if data.get('role') == 'admin' else 'user'
    conn = get_db_connection()
    conn.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)