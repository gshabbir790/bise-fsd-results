import os
import uuid
import zipfile
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)

JOBS = {}
JOBS_DIR = "/tmp/bise_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)

# ---------------------------------------------------------
# 1. Check Website Route
# ---------------------------------------------------------
@app.route("/api/check", methods=["GET", "POST"])
def check_website():
    if request.method == "GET":
        return jsonify({"message": "API is working. Please use POST request with a 'url' JSON body."})

    data = request.get_json(force=True) or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": "url is required"}), 400

    has_session = False
    debug_info = {
        "url": url,
        "has_session": False,
        "selects_found": 0,
        "iframes_found": 0,
        "html_snippet": ""
    }
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")

        debug_info["html_snippet"] = response.text[:1000]
        selects = soup.find_all("select")
        debug_info["selects_found"] = len(selects)

        for sel in selects:
            name_attr = sel.get("name", "")
            id_attr = sel.get("id", "")
            if "session" in name_attr.lower() or "session" in id_attr.lower() or "year" in name_attr.lower():
                has_session = True

        iframes = soup.find_all("iframe")
        debug_info["iframes_found"] = len(iframes)

        debug_info["has_session"] = has_session

        return jsonify({
            "success": True,
            "has_session": has_session,
            "debug": debug_info
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "debug": debug_info
        }), 500

# ---------------------------------------------------------
# 2. Synchronous Scrape & Download Logic for Serverless
# ---------------------------------------------------------
@app.route("/api/job", methods=["POST"])
def start_job():
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    session = data.get("session", "")
    
    custom_rolls_raw = data.get("custom_rolls", [])
    start_roll = data.get("start_roll", 0)
    end_roll = data.get("end_roll", 0)

    roll_list = []

    if custom_rolls_raw and len(custom_rolls_raw) > 0:
        for r in custom_rolls_raw:
            try:
                roll_list.append(int(r))
            except ValueError:
                pass
    else:
        try:
            start_r = int(start_roll)
            end_r = int(end_roll)
            if start_r > 0 and end_r >= start_r:
                roll_list = list(range(start_r, end_r + 1))
        except ValueError:
            pass

    if not target_url or not roll_list:
        return jsonify({"error": "invalid input یا رول نمبرز درست نہیں ہیں"}), 400

    # Serverless execution limit constraint
    if len(roll_list) > 10:
        return jsonify({"error": "Vercel فری سرور پر ایک وقت میں صرف 10 رول نمبر پروسیس ہو سکتے ہیں۔"}), 400

    job_id = str(uuid.uuid4())
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    done = 0
    failed = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }

    session_req = requests.Session()

    for roll_no in roll_list:
        try:
            payload = {
                "rollno": str(roll_no),
                "session": session
            }
            res = session_req.post(target_url, data=payload, headers=headers, timeout=10)
            
            file_path = os.path.join(out_dir, f"{roll_no}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(res.text)
            done += 1
        except Exception as e:
            failed.append({"roll_no": roll_no, "error": str(e)})

    zip_path = os.path.join(JOBS_DIR, f"{job_id}.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for fname in os.listdir(out_dir):
            zf.write(os.path.join(out_dir, fname), fname)

    JOBS[job_id] = {
        "status": "done",
        "total": len(roll_list),
        "processed": len(roll_list),
        "done": done,
        "failed": failed,
        "zip_path": zip_path
    }

    return jsonify({"job_id": job_id, "status": "done"})

# ---------------------------------------------------------
# 3. Job Status Route
# ---------------------------------------------------------
@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify({
        "status": job["status"],
        "total": job["total"],
        "processed": job["processed"],
        "done": job["done"],
        "failed": job["failed"],
    })

# ---------------------------------------------------------
# 4. Zip Download Route
# ---------------------------------------------------------
@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "not ready"}), 400
    return send_file(job["zip_path"], as_attachment=True, download_name=f"results_{job_id}.zip")

# ---------------------------------------------------------
# 5. Health Check
# ---------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Universal BISE Result Downloader backend is running on Vercel"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
    
