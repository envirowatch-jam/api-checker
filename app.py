#!/usr/bin/env python3
"""
API Status Checker - Flask Web Version
Monitors three APIs: MOTE SOAP, AirQWeb iPM, Tracker API
Works in a web browser instead of a desktop window
"""

from flask import Flask, render_template_string, jsonify
from datetime import datetime, timedelta, timezone
from zeep import Client
from zeep.transports import Transport
import requests
import urllib.request
import json
import threading

app = Flask(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

MOTE_WSDL_URL = "http://api-bt.envirowatch.ltd.uk/moteservice.asmx?WSDL"
MOTE_EMAIL = "jneasham8@gmail.com"
MOTE_PASSWORD = "wambamjam"

AIRQWEB_BASE_URL = "https://datacollector.airqweb.com"
AIRQWEB_USER_ID = "IsCorbridgeOnline"
AIRQWEB_TOKEN = "191aVAGl6Jel02ALqxShQbI7lBFKDisKDDn68ut0JA5McSNNAFe8GdJnT64DNS9F"
AIRQWEB_INSTRUMENT_ID = "P0027"

TRACKER_BASE_URL = "https://envirowatchapi.azurewebsites.net"
TRACKER_API_KEY = "5E84B60244F9206C9E23F9675A"
TRACKER_IDS = [1,2,3,5,6,7,8,9,11,12,13,14,15,16,17,18,19,20,21,22]

# ──────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def is_online(timestamp_str):
    """Check if a timestamp is within the last hour"""
    try:
        # Handle datetime objects
        if hasattr(timestamp_str, 'strftime'):
            ts = timestamp_str
        elif 'T' in str(timestamp_str):
            ts = datetime.fromisoformat(str(timestamp_str).replace('Z', '+00:00'))
        else:
            ts = datetime.strptime(str(timestamp_str), "%d/%m/%Y %H:%M:%S")
            ts = ts.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        age = now - ts
        return age < timedelta(hours=1)
    except Exception as e:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# API CHECK FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def check_mote():
    """Check MOTE SOAP API"""
    try:
        session = requests.Session()
        transport = Transport(session=session)
        client = Client(wsdl=MOTE_WSDL_URL, transport=transport)
        
        # Login with named parameters
        login_resp = client.service.Login(emailAddress=MOTE_EMAIL, password=MOTE_PASSWORD)
        
        if login_resp.LoginResult.ResponseType != "Success":
            return {"api_working": False, "error": "Login failed"}
        
        token = login_resp.token
        
        # Get motes and latest data
        motes_resp = client.service.GetMotes(token=token)
        latest_resp = client.service.GetLatest(token=token)
        
        if motes_resp.GetMotesResult.ResponseType != "Success":
            return {"api_working": False, "error": "Could not retrieve motes"}
        
        # Build timestamp map
        latest_map = {}
        if latest_resp.moteDataSets and latest_resp.moteDataSets.MoteDataSet:
            for ds in latest_resp.moteDataSets.MoteDataSet:
                latest_map[ds.SensorId] = ds.TimeStamp
        
        # Categorize motes
        online = []
        offline = []
        
        if motes_resp.motes and motes_resp.motes.Mote:
            for mote in motes_resp.motes.Mote:
                sensor_id = mote.SensorId
                ts = latest_map.get(sensor_id)
                
                if ts:
                    if hasattr(ts, 'strftime'):
                        ts_str = ts.strftime('%d/%m/%Y %H:%M:%S')
                    else:
                        ts_str = str(ts)
                    is_on = is_online(ts_str)
                else:
                    is_on = False
                
                if is_on:
                    online.append(sensor_id)
                else:
                    offline.append(sensor_id)
        
        return {
            "api_working": True,
            "online": online,
            "offline": offline,
            "count": f"{len(online)} online, {len(offline)} offline"
        }
    
    except Exception as e:
        return {"api_working": False, "error": str(e)}


def check_airqweb():
    """Check AirQWeb iPM API"""
    try:
        url = f"{AIRQWEB_BASE_URL}/latestData?userID={AIRQWEB_USER_ID}&token={AIRQWEB_TOKEN}&instrumentID={AIRQWEB_INSTRUMENT_ID}"
        response = urllib.request.urlopen(url, timeout=30)
        data = json.loads(response.read())
        
        if not data or len(data) == 0:
            return {"api_working": False, "error": "No data returned"}
        
        reading = data[0]
        timestamp = reading.get('timestamp', 'Unknown')
        is_on = is_online(timestamp)
        
        online = [AIRQWEB_INSTRUMENT_ID] if is_on else []
        offline = [] if is_on else [AIRQWEB_INSTRUMENT_ID]
        
        return {
            "api_working": True,
            "online": online,
            "offline": offline,
            "count": f"1 online, 0 offline" if is_on else "0 online, 1 offline"
        }
    
    except Exception as e:
        return {"api_working": False, "error": str(e)}


def check_tracker():
    """Check Tracker API"""
    try:
        online = []
        offline = []
        errors = []
        
        for tracker_id in TRACKER_IDS:
            serial = f"Tracker{tracker_id}"
            url = f"{TRACKER_BASE_URL}/VehicleLatestPoint/v1/{serial}"
            try:
                request = urllib.request.Request(url, headers={"x-api-key": TRACKER_API_KEY})
                response = urllib.request.urlopen(request, timeout=10)
                data = json.loads(response.read())
                fix_time = data.get('fixTime', 'Unknown')
                
                try:
                    # Handle both datetime objects and strings
                    if hasattr(fix_time, 'strftime'):
                        fix_dt = fix_time
                    else:
                        fix_dt = datetime.strptime(str(fix_time), "%Y-%m-%dT%H:%M:%S")
                        fix_dt = fix_dt.replace(tzinfo=timezone.utc)
                    
                    if is_online(fix_dt):
                        online.append(serial)
                    else:
                        offline.append(serial)
                except:
                    offline.append(serial)
            
            except Exception:
                errors.append(serial)
        
        return {
            "api_working": True,
            "online": online,
            "offline": offline,
            "errors": errors,
            "count": f"{len(online)} online, {len(offline)} offline, {len(errors)} errors"
        }
    
    except Exception as e:
        return {"api_working": False, "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# HTML TEMPLATE
# ──────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>API Status Checker</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background: #0f1419;
            color: #f1f5f9;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        .header {
            background: #1a1f2e;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 28px;
            margin-bottom: 5px;
        }
        
        .header p {
            color: #94a3b8;
            font-size: 14px;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 1px solid #334155;
        }
        
        .tab-btn {
            padding: 12px 20px;
            background: transparent;
            color: #cbd5e1;
            border: none;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            border-bottom: 2px solid transparent;
            transition: all 0.3s;
        }
        
        .tab-btn:hover {
            color: #f1f5f9;
        }
        
        .tab-btn.active {
            color: #3b82f6;
            border-bottom-color: #3b82f6;
        }
        
        .tab-content {
            display: none;
            background: #1a1f2e;
            padding: 30px;
            border-radius: 8px;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .status-header {
            margin-bottom: 20px;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
            background: #94a3b8;
        }
        
        .status-indicator.working {
            background: #10b981;
        }
        
        .status-indicator.error {
            background: #ef4444;
        }
        
        .check-btn {
            background: #10b981;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
        }
        
        .check-btn:hover {
            background: #059669;
        }
        
        .check-btn:disabled {
            background: #6b7280;
            cursor: not-allowed;
        }
        
        .results {
            margin-top: 20px;
        }
        
        .result-section {
            margin-bottom: 20px;
        }
        
        .result-header {
            color: #3b82f6;
            font-weight: 500;
            margin-bottom: 8px;
        }
        
        .device-item {
            padding: 8px;
            margin: 4px 0;
            padding-left: 16px;
            color: #cbd5e1;
        }
        
        .device-item.online {
            color: #10b981;
        }
        
        .device-item.online:before {
            content: "✓ ";
        }
        
        .device-item.offline {
            color: #ef4444;
        }
        
        .device-item.offline:before {
            content: "✗ ";
        }
        
        .device-item.error {
            color: #f59e0b;
        }
        
        .device-item.error:before {
            content: "⚠ ";
        }
        
        .error-message {
            color: #ef4444;
            background: rgba(239, 68, 68, 0.1);
            padding: 12px;
            border-radius: 6px;
            margin-top: 10px;
        }
        
        .loading {
            display: none;
            color: #f59e0b;
        }
        
        .loading.active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 API Status Checker</h1>
            <p>Monitor your API endpoints and device connectivity</p>
        </div>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab(0)">📡 MOTE SOAP</button>
            <button class="tab-btn" onclick="switchTab(1)">💨 AirQWeb iPM</button>
            <button class="tab-btn" onclick="switchTab(2)">🚗 Tracker API</button>
        </div>
        
        <!-- MOTE Tab -->
        <div class="tab-content active">
            <div class="status-header">
                <span class="status-indicator" id="mote-indicator"></span>
                <strong id="mote-status">Ready to check status</strong>
            </div>
            <button class="check-btn" onclick="checkAPI('mote')" id="mote-btn">▶ CHECK STATUS</button>
            <div class="loading" id="mote-loading">Loading...</div>
            <div class="results" id="mote-results"></div>
        </div>
        
        <!-- AirQWeb Tab -->
        <div class="tab-content">
            <div class="status-header">
                <span class="status-indicator" id="airqweb-indicator"></span>
                <strong id="airqweb-status">Ready to check status</strong>
            </div>
            <button class="check-btn" onclick="checkAPI('airqweb')" id="airqweb-btn">▶ CHECK STATUS</button>
            <div class="loading" id="airqweb-loading">Loading...</div>
            <div class="results" id="airqweb-results"></div>
        </div>
        
        <!-- Tracker Tab -->
        <div class="tab-content">
            <div class="status-header">
                <span class="status-indicator" id="tracker-indicator"></span>
                <strong id="tracker-status">Ready to check status</strong>
            </div>
            <button class="check-btn" onclick="checkAPI('tracker')" id="tracker-btn">▶ CHECK STATUS</button>
            <div class="loading" id="tracker-loading">Loading...</div>
            <div class="results" id="tracker-results"></div>
        </div>
    </div>
    
    <script>
        function switchTab(index) {
            // Hide all tabs
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(c => c.classList.remove('active'));
            
            // Remove active from buttons
            const buttons = document.querySelectorAll('.tab-btn');
            buttons.forEach(b => b.classList.remove('active'));
            
            // Show selected tab
            contents[index].classList.add('active');
            buttons[index].classList.add('active');
        }
        
        function checkAPI(api) {
            const btn = document.getElementById(api + '-btn');
            const loading = document.getElementById(api + '-loading');
            const results = document.getElementById(api + '-results');
            const indicator = document.getElementById(api + '-indicator');
            const status = document.getElementById(api + '-status');
            
            btn.disabled = true;
            loading.classList.add('active');
            results.innerHTML = '';
            
            fetch(`/api/${api}`)
                .then(response => response.json())
                .then(data => {
                    loading.classList.remove('active');
                    
                    if (data.api_working) {
                        indicator.className = 'status-indicator working';
                        status.textContent = '✓ API WORKING';
                        
                        let html = '';
                        
                        // Offline section
                        html += `<div class="result-section">
                            <div class="result-header">Offline (${data.offline.length})</div>`;
                        if (data.offline.length > 0) {
                            data.offline.forEach(item => {
                                html += `<div class="device-item offline">${item}</div>`;
                            });
                        } else {
                            html += '<div class="device-item">(none)</div>';
                        }
                        html += '</div>';
                        
                        // Online section
                        html += `<div class="result-section">
                            <div class="result-header">Online (${data.online.length})</div>`;
                        if (data.online.length > 0) {
                            data.online.forEach(item => {
                                html += `<div class="device-item online">${item}</div>`;
                            });
                        } else {
                            html += '<div class="device-item">(none)</div>';
                        }
                        html += '</div>';
                        
                        // Error section (if tracker)
                        if (data.errors && data.errors.length > 0) {
                            html += `<div class="result-section">
                                <div class="result-header">Errors (${data.errors.length})</div>`;
                            data.errors.forEach(item => {
                                html += `<div class="device-item error">${item}</div>`;
                            });
                            html += '</div>';
                        }
                        
                        results.innerHTML = html;
                    } else {
                        indicator.className = 'status-indicator error';
                        status.textContent = '✗ API FAILED';
                        results.innerHTML = `<div class="error-message">Error: ${data.error}</div>`;
                    }
                })
                .catch(error => {
                    loading.classList.remove('active');
                    indicator.className = 'status-indicator error';
                    status.textContent = '✗ Connection failed';
                    results.innerHTML = `<div class="error-message">Error: ${error.message}</div>`;
                })
                .finally(() => {
                    btn.disabled = false;
                });
        }
    </script>
</body>
</html>
"""

# ──────────────────────────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Main page"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/mote')
def api_mote():
    """API endpoint for MOTE check"""
    return jsonify(check_mote())


@app.route('/api/airqweb')
def api_airqweb():
    """API endpoint for AirQWeb check"""
    return jsonify(check_airqweb())


@app.route('/api/tracker')
def api_tracker():
    """API endpoint for Tracker check"""
    return jsonify(check_tracker())


# ──────────────────────────────────────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
