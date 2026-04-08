import os
import pytz
import logging
from datetime import datetime
import requests
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

import azure.functions as func

# -----------------------------
# LOGGING SETUP (Azure-friendly)
# -----------------------------
logging.basicConfig(level=logging.INFO)
logging.info("Program started")

# -----------------------------
# API CONFIG
# -----------------------------
API_KEY = os.environ["API_KEY"]  # From Environment variables in Function App
URL = "https://api.at.govt.nz/realtime/legacy/tripupdates"

LINES = {
    "Southern": "STH-201",
    "Eastern": "EAST-201",
    "Western": "WEST-201",
    "Onehunga": "ONE-201"
}

HEADSIGN_RULES = {
    "Southern": ("Pukekohe", "Brit"),
    "Eastern": ("Manukau", "Brit"),
    "Western": ("Brit", "Swanson"),
    "Onehunga": ("Onehunga", "Newmarket")
}

# -----------------------------
# DATABASE SETUP
# -----------------------------
userid = os.environ["DB_USER"]       # From Environment variables in Function App
password = os.environ["DB_PASSWORD"] # From Environment variables in Function App
host = os.environ["DB_HOST"]         # From Environment variables in Function App
database = os.environ["DB_NAME"]     # From Environment variables in Function App
port = 3306

DATABASE_URL = (
    f"mysql+mysqlconnector://{userid}:{password}@{host}:{port}/{database}"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class TrainLineLog(Base):
    __tablename__ = "attrainstoplog"

    PKEY = Column(Integer, primary_key=True, autoincrement=True)
    DateTimeExtracted = Column(DateTime, nullable=False)
    TrainLine = Column(String(50), nullable=False)
    Status = Column(String(30), nullable=False)
    WhereTaken = Column(String(50), nullable=False)
    Route_ID = Column(String(20), nullable=False)
    Trip_ID = Column(String(50), nullable=True)


def log_status(train_line, status, route_id, trip_id=None):
    session = SessionLocal()
    try:
        entry = TrainLineLog(
            DateTimeExtracted=datetime.now(),
            TrainLine=train_line,
            Status=status,
            WhereTaken="Real Time API",
            Route_ID=route_id,
            Trip_ID=trip_id
        )
        session.add(entry)
        session.commit()
        logging.info(f"{train_line} logged as {status} (Trip_ID={trip_id})")
    except Exception as e:
        session.rollback()
        logging.error(f"DB Error: {e}")
    finally:
        session.close()


# -----------------------------
# API CALLS
# -----------------------------
def fetch_tripupdates():
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    response = requests.get(URL, headers=headers)
    response.raise_for_status()
    return response.json()["response"]["entity"]


def fetch_trip_headsign(trip_id):
    url = f"https://api.at.govt.nz/gtfs/v3/trips/{trip_id}"
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}

    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        return data["data"]["attributes"].get("trip_headsign", "")
    except Exception as e:
        logging.error(f"Error fetching headsign for {trip_id}: {e}")
        return ""


# -----------------------------
# CANCELLATION DETECTION
# -----------------------------
def is_cancelled(entity):
    trip_update = entity.get("trip_update", {})

    rel = trip_update.get("trip", {}).get("schedule_relationship")
    if rel == 3:
        return True

    for stu in trip_update.get("stop_time_update", []):
        if isinstance(stu, dict):
            rel2 = stu.get("schedule_relationship")
            if rel2 == 3:
                return True

    return False


# -----------------------------
# CLASSIFICATION LOGIC
# -----------------------------
def classify_lines(entities):
    results = {}

    for line_name, route_prefix in LINES.items():
        begin, end = HEADSIGN_RULES[line_name]

        line_entities = []
        for e in entities:
            trip = e.get("trip_update", {}).get("trip", {})
            if trip.get("route_id") == route_prefix:
                line_entities.append(e)

        if not line_entities:
            results[line_name] = "STOPPED"
            log_status(line_name, "STOPPED", route_prefix)
            continue

        valid_count = 0
        cancelled_found = False
        track_found = False

        for e in line_entities:
            trip_id = e.get("trip_update", {}).get("trip", {}).get("trip_id")

            if is_cancelled(e):
                cancelled_found = True
                log_status(line_name, "CANCELLED", route_prefix, trip_id)

            if trip_id:
                headsign = fetch_trip_headsign(trip_id)
                if begin.lower() in headsign.lower() and end.lower() in headsign.lower():
                    valid_count += 1
                    track_found = True

        if cancelled_found:
            results[line_name] = "CANCELLED"
            continue

        if valid_count == 0:
            results[line_name] = "PARTIALLY RUNNING"
            log_status(line_name, "PARTIALLY RUNNING", route_prefix)
            continue

        if not track_found:
            results[line_name] = "PARTIALLY RUNNING"
            log_status(line_name, "PARTIALLY RUNNING", route_prefix)
            continue

        results[line_name] = "OK"
        log_status(line_name, "OK", route_prefix)

    return results

def is_within_nz_window(start_hour=5, end_hour=23):
    nz = pytz.timezone("Pacific/Auckland")
    now_nz = datetime.now(nz)
    hour = now_nz.hour
    return start_hour <= hour < end_hour

# -----------------------------
# AZURE FUNCTION ENTRY POINT
# -----------------------------
def main(mytimer: func.TimerRequest):
    if not is_within_nz_window():
        logging.info("Outside NZ time window (5AM–11PM). Skipping execution.")
    else:
        logging.info("Within NZ time window. Running extraction.")
        entities = fetch_tripupdates()
        status = classify_lines(entities)

        print("Train Line Status:")
        for line, state in status.items():
            print(f"{line}: {state}")
            logging.info(f"{line}: {state}")