import os
import logging
from datetime import datetime
import requests
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# -----------------------------
# LOGGING SETUP (Daily file, monthly folder)
# -----------------------------
def setup_logging():
    now = datetime.now()
    month_folder = now.strftime("%Y-%m")
    os.makedirs(month_folder, exist_ok=True)

    log_filename = now.strftime("log_trainstat_%Y%m%d.txt")
    log_path = os.path.join(month_folder, log_filename)

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

setup_logging()
logging.info("Program started")

# -----------------------------
# API CONFIG
# -----------------------------
API_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"                    # Get your own key from https://dev-portal.at.gov.nz
URL = "https://api.at.govt.nz/realtime/legacy/tripupdates"

LINES = {
    "Southern": "STH-201",                                      # STH-201 is the route ID for Southern line
    "Eastern": "EAST-201",                                      # EAST-201 is the route ID for Eastern line
    "Western": "WEST-201",                                      # WEST-201 is the route ID for Western line
    "Onehunga": "ONE-201"                                       # ONE-201 is the route ID for Onehunga line
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
userid = 'atpythonuser01'           # This could be based on your own configuration
password = 'xxxxxxxxxxx'            # This could be based on your own configuration
host = '127.0.0.1'                  # This could be based on your own configuration
port = 3306                         # This could be based on your own configuration
database = 'auckland_transport_db'  # This could be based on your own configuration

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
    Trip_ID = Column(String(50), nullable=True)  # NEW COLUMN

Base.metadata.create_all(engine)

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
    if rel == 3: # or (isinstance(rel, str) and str(rel).upper() == "CANCELED"):
        return True

    for stu in trip_update.get("stop_time_update", []):
        if isinstance(stu, dict):
            rel2 = stu.get("schedule_relationship")
            if rel2 == 3: # or (isinstance(rel2, str) and str(rel2).upper() == "CANCELED"):
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
            if trip.get("route_id") == route_prefix: #and trip.get("direction_id") == 0:
                line_entities.append(e)

        if not line_entities:
            results[line_name] = "STOPPED"
            log_status(line_name, "STOPPED", route_prefix)
            continue

        total = len(line_entities)
        valid_count = 0
        cancelled_found = False
        track_found = False

        for e in line_entities:
            trip_id = e.get("trip_update", {}).get("trip", {}).get("trip_id")

            # Log each cancelled trip with its trip_id
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
            # line-level CANCELLED already logged per trip; no extra log_status here
            continue

        if valid_count == 0:
            results[line_name] = "STOPPED"
            log_status(line_name, "STOPPED", route_prefix)
            continue

        if track_found == False:
            results[line_name] = "PARTIALLY CLOSED"
            log_status(line_name, "PARTIALLY CLOSED", route_prefix)
            continue

        results[line_name] = "OK"
        log_status(line_name, "OK", route_prefix)

    return results

# -----------------------------
# MAIN EXECUTION
# -----------------------------
if __name__ == "__main__":
    entities = fetch_tripupdates()
    status = classify_lines(entities)

    print("Train Line Status:")
    for line, state in status.items():
        print(f"{line}: {state}")
        logging.info(f"{line}: {state}")
