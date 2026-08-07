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

@app.route("/api/check", methods=["GET", "POST"])
def check_website():
    if request.method == "GET":
        return jsonify({"message": "API is working."})

    data = request.get_json(force=True) or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": "url is required"}), 400

    has_session = False
    debug_info = {"url": url, "has_session": False, "selects_found": 0}
    
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")

        selects = soup.find_all("select")
        debug_info["selects_found"] = len(selects)

        # Enhanced detection for ASP.NET & normal select tags
        if len(selects) > 0:
            has_session = True

        debug_info["has_session"] = has_session
        return jsonify({"success": True, "has_session": has_session, "debug": debug_info})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/job", methods=["POST"])
def start_job():
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    session_val = data.get("session", "")
    
    custom_rolls_raw = data.get("custom_rolls", [])
    start_roll = data.get("start_roll", 0)
    end_roll = data.get("end_roll", 0)

    roll_list = []
    if custom_rolls_raw:
        for r in custom_rolls_raw:
            try: roll_list.append(int(r))
            except ValueError: pass
    else:
        try:
            start_r, end_r = int(start_roll), int(end_roll)
            if start_r > 0 and end_r >= start_r:
                roll_list = list(range(start_r, end_r + 1))
        except ValueError: pass

    if not target_url or not roll_list:
        return jsonify({"error": "غلط ان پٹ یا رول نمبرز"}), 400

    if len(roll_list) > 15:
        return jsonify({"error": "Vercel پر ایک وقت میں 15 سے زیادہ رول نمبر ممکن نہیں"}), 400

    job_id = str(uuid.uuid4())
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    done = 0
    failed = []
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    session_req = requests.Session()

    for roll_no in roll_list:
        try:
            # Step 1: GET Request to extract ASP.NET ViewState
            init_res = session_req.get(target_url, headers=headers, timeout=10)
            soup = BeautifulSoup(init_res.text, "html.parser")

            payload = {}
            # Extract all hidden inputs (ASP.NET requires these)
            for hidden in soup.find_all("input", type="hidden"):
                if hidden.get("name"):
                    payload[hidden["name"]] = hidden.get("value", "")

            # Step 2: Map Roll No Field
            roll_input = soup.find("input", {"type": "text"}) or soup.find("input", id=lambda x: x and "roll" in x.lower())
            roll_field_name = roll_input.get("name") if roll_input else "txtRollNo"
            payload[roll_field_name] = str(roll_no)

            # Step 3: Map Session Select Field if applicable
            select_tag = soup.find("select")
            if select_tag and session_val:
                select_name = select_tag.get("name", "ddlExam")
                payload[select_name] = session_val

            # Step 4: Map Submit Button Name
            submit_btn = soup.find("input", type="submit") or soup.find("button", type="submit")
            if submit_btn and submit_btn.get("name"):
                payload[submit_btn["name"]] = submit_btn.get("value", "Get Result")

            # Step 5: Submit Form
            res = session_req.post(target_url, data=payload, headers=headers, timeout=12)
            
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

@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job: return jsonify({"error": "job not found"}), 404
    return jsonify(job)

@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done": return jsonify({"error": "not ready"}), 400
    return send_file(job["zip_path"], as_attachment=True, download_name=f"results_{job_id}.zip")

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Backend running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
    
