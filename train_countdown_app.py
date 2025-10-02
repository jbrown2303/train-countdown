import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import streamlit as st
import time
import os

API_ENDPOINT = "https://lite.realtime.nationalrail.co.uk/OpenLDBWS/ldbsvws.asmx"
API_KEY = os.getenv("DARWIN_API_KEY")  # pulled from Streamlit Secrets

NAMESPACE = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "ldb": "http://thalesgroup.com/RTTI/2017-10-01/ldb/"
}

def parse_time_hhmm(tstr):
    now = datetime.now()
    try:
        hh, mm = map(int, tstr.split(":"))
    except Exception:
        return None
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate < now - timedelta(hours=6):
        candidate += timedelta(days=1)
    return candidate

def best_departure_datetime(std, etd):
    if etd and ":" in etd:
        dt = parse_time_hhmm(etd)
        if dt:
            return dt, "Estimated"
    if std:
        dt = parse_time_hhmm(std)
        if dt:
            return dt, "Scheduled"
    return None, None

def fetch_services(origin, destination=None, toc=None, rows=20):
    filter_crs = f"<filterCrs>{destination}</filterCrs>" if destination else ""
    filter_toc = f"<filterTOC>{toc}</filterTOC>" if toc else ""

    payload = f"""
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <GetDepBoardWithDetailsRequest xmlns="http://thalesgroup.com/RTTI/2017-10-01/ldb/">
          <crs>{origin}</crs>
          {filter_crs}
          <numRows>{rows}</numRows>
          {filter_toc}
          <accessToken><TokenValue>{API_KEY}</TokenValue></accessToken>
        </GetDepBoardWithDetailsRequest>
      </soap:Body>
    </soap:Envelope>
    """

    headers = {"Content-Type": "text/xml"}
    resp = requests.post(API_ENDPOINT, data=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    services = []
    for svc in root.findall(".//ldb:service", NAMESPACE):
        std = svc.findtext("ldb:std", default="", namespaces=NAMESPACE)
        etd = svc.findtext("ldb:etd", default="", namespaces=NAMESPACE)
        operator = svc.findtext("ldb:operator", default="", namespaces=NAMESPACE)
        dest_node = svc.find(".//ldb:destination//ldb:location//ldb:locationName", NAMESPACE)
        destination_name = dest_node.text if dest_node is not None else ""
        platform = svc.findtext("ldb:platform", default="", namespaces=NAMESPACE)

        depart_dt, basis = best_departure_datetime(std, etd)
        services.append({
            "std": std,
            "etd": etd,
            "basis": basis,
            "operator": operator,
            "destination": destination_name,
            "platform": platform,
            "depart_dt": depart_dt
        })
    return services

# ---- Streamlit UI ----
st.title("🚆 Train Service Finder + Countdown")

col1, col2, col3 = st.columns(3)
origin = col1.text_input("Origin CRS (e.g., PAD)", "PAD").upper()
destination = col2.text_input("Destination CRS (optional)", "").upper()
toc = col3.text_input("TOC Code (optional, e.g., GW)", "").upper()

if st.button("Fetch Services"):
    try:
        services = fetch_services(origin, destination or None, toc or None, rows=20)
    except Exception as e:
        st.error(f"Error fetching services: {e}")
        services = []

    if not services:
        st.warning("No services found.")
    else:
        st.session_state["services"] = services

if "services" in st.session_state:
    services = st.session_state["services"]
    st.subheader("Available Services")

    options = []
    for i, s in enumerate(services):
        options.append(
            f"{i+1}. {s['std']} → {s['destination']} "
            f"(ETD {s['etd']}, Plat {s['platform']}, {s['operator']})"
        )

    choice = st.selectbox("Select a service:", options, index=0)
    chosen = services[int(choice.split(".")[0]) - 1]

    if st.button("Start 5-Minute Countdown"):
        st.session_state["target_dt"] = chosen["depart_dt"]
        st.session_state["chosen"] = chosen

if "target_dt" in st.session_state and st.session_state["target_dt"]:
    chosen = st.session_state["chosen"]
    st.subheader(f"Countdown for {chosen['destination']} service")
    target = st.session_state["target_dt"]

    placeholder = st.empty()
    status = st.empty()

    while True:
        now = datetime.now()
        remaining = target - now
        total_sec = int(remaining.total_seconds())

        if total_sec <= 0:
            placeholder.markdown("## ⏰ Departing now!")
            break

        if total_sec > 300:
            until_start = total_sec - 300
            mm, ss = divmod(until_start, 60)
            start_at = (now + timedelta(seconds=until_start)).strftime("%H:%M:%S")
            status.text(f"5-minute countdown will begin at {start_at} (in {mm}m {ss}s)")
            placeholder.markdown("## --:--")
        else:
            mm, ss = divmod(total_sec, 60)
            status.text("Counting down to departure…")
            placeholder.markdown(f"## {mm:02d}:{ss:02d}")

        time.sleep(1)
