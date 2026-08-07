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
# 1. Check Website (Vercel Safe - No Playwright)
# ---------------------------------------------------------
@app.route("/api/check", methods=["GET", "POST"])
def check_website():
    if request.method == "GET":
        return jsonify({"message": "Vercel API Working. Send POST request with URL."})
        
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    
    if not target_url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(target_url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        sessions_list = []
        has_session = False
        
        select_tags = soup.find_all("select")
        for select in select_tags:
            name_attr = select.get("name", "").lower()
            id_attr = select.get("id", "").lower()
            
            if "session" in name_attr or "exam" in name_attr or "ddl" in name_attr:
                has_session = True
                for opt in select.find_all("option"):
                    text = opt.get_text(strip=True)
                    val = opt.get("value", text)
                    if text and not any(k in text.lower() for k in ['select', 'choose', '--']):
                        sessions_list.append({'label': text, 'value': val})
                break 
                
        return jsonify({
            'success': True,
            'has_session': has_session,
            'sessions': sessions_list
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ---------------------------------------------------------
# 2. Scrape & Download HTML (Vercel Safe)
# ---------------------------------------------------------
@app.route("/api/job", methods=["POST"])
def start_job():
    # Vercel پر بیک گراؤنڈ Thread کام نہیں کرتے، اس لیے یہ synchronous ہے۔
    # 10 سیکنڈ ٹائم آؤٹ سے بچنے کے لیے ایک وقت میں 10-15 رول نمبرز بھیجیں۔
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    session_val = data.get("session", "")
    
    custom_rolls = data.get("custom_rolls", [])
    start_roll = data.get("start_roll", 0)
    end_roll = data.get("end_roll", 0)

    roll_list = []
    if custom_rolls:
        roll_list = [int(r) for r in custom_rolls if str(r).isdigit()]
    elif start_roll and end_roll:
        roll_list = list(range(int(start_roll), int(end_roll) + 1))

    if not target_url or not roll_list:
        return jsonify({"error": "رول نمبرز درست نہیں ہیں"}), 400

    job_id = str(uuid.uuid4())
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    sess = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    done = 0
    failed = []

    for roll_no in roll_list:
        try:
            # 1. Get ViewState & Form Data
            init_res = sess.get(target_url, headers=headers, timeout=10)
            soup = BeautifulSoup(init_res.text, "html.parser")

            payload = {}
            for hidden in soup.find_all("input", type="hidden"):
                if hidden.get("name"):
                    payload[hidden["name"]] = hidden.get("value", "")

            roll_input = soup.find("input", {"type": "text"}) or soup.find("input", id=lambda x: x and "roll" in x.lower())
            if roll_input and roll_input.get("name"):
                payload[roll_input["name"]] = str(roll_no)

            if session_val:
                select_tag = soup.find("select")
                if select_tag and select_tag.get("name"):
                    payload[select_tag["name"]] = session_val

            submit_btn = soup.find("input", type="submit") or soup.find("button", type="submit")
            if submit_btn and submit_btn.get("name"):
                payload[submit_btn["name"]] = submit_btn.get("value", "Search")

            # 2. Submit Form
            res = sess.post(target_url, data=payload, headers=headers, timeout=15)
            
            # Save as HTML instead of PDF
            file_path = os.path.join(out_dir, f"{roll_no}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(res.text)
            
            done += 1
        except Exception as e:
            failed.append({"roll_no": roll_no, "error": str(e)})

    # Zip the HTML files
    zip_path = os.path.join(JOBS_DIR, f"{job_id}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
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
    return jsonify(job)

# ---------------------------------------------------------
# 4. Zip Download Route
# ---------------------------------------------------------
@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "not ready"}), 400
    return send_file(job["zip_path"], as_attachment=True, download_name=f"results_{job_id}.zip")

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Vercel HTML Scraper Running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))