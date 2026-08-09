import os
import uuid
import zipfile
import threading
import time
import logging
import traceback
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from playwright.sync_api import sync_playwright

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

JOBS = {}
JOBS_DIR = "/tmp/bise_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)

# ---------------------------------------------------------
# 0. Home Route (API Status Check - دوسری فائل سے لیا گیا)
# ---------------------------------------------------------
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "BISE Result Downloader API is running successfully!"
    })

# ---------------------------------------------------------
# 1. Check Website Route (دونوں فائلوں کا بہترین امتزاج)
# ---------------------------------------------------------
@app.route("/api/check", methods=["GET", "POST"])
def check_website():
    if request.method == "GET":
        return jsonify({
            "message": "API is working. Use POST with JSON: {'url': '...'}"
        })

    try:
        data = request.get_json(silent=True) or {}
        url = data.get("url")

        if not url:
            return jsonify({"error": "url is required"}), 400

        print("\n========== CHECK START ==========")
        print("Target URL:", url)

        sessions_list = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )

            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768}
            )

            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # جاوا اسکرپٹ لوڈ ہونے کے لیے تھوڑا انتظار
            page.wait_for_timeout(5000)

            # ایک فنکشن جو کسی بھی پیج یا فریم سے سیشنز نکالے گا (پہلی فائل کا لاجک)
            def extract_sessions_from_context(context_page):
                extracted = []
                try:
                    # سیشن سے متعلقہ تمام ڈراپ ڈاؤنز کو ڈھونڈیں
                    selects = context_page.query_selector_all('select')
                    for select in selects:
                        name = (select.get_attribute('name') or '').lower()
                        sid = (select.get_attribute('id') or '').lower()
                        
                        # اگر ڈراپ ڈاؤن کا نام سیشن، ایگزام وغیرہ سے ملتا ہے
                        if any(k in name or k in sid for k in ["session", "exam", "year", "ddl", "sess"]):
                            options = select.query_selector_all('option')
                            for opt in options:
                                text = opt.inner_text().strip()
                                val = opt.get_attribute('value') or text
                                # فالتو آپشنز کو نکالیں
                                if text and not any(k in text.lower() for k in ['select', 'choose', 'پوچھیں', '--']):
                                    extracted.append({'label': text, 'value': val})
                except Exception as ex:
                    pass
                return extracted

            # 1. مین پیج سے سیشنز نکالیں
            main_page_sessions = extract_sessions_from_context(page)
            for s in main_page_sessions:
                if s not in sessions_list:
                    sessions_list.append(s)

            # 2. فریمز کے اندر سے سیشنز نکالیں (دوسری فائل کا لاجک)
            for frame in page.frames:
                frame_sessions = extract_sessions_from_context(frame)
                for s in frame_sessions:
                    if s not in sessions_list:
                        sessions_list.append(s)

            print("Extracted Sessions:", sessions_list)
            print("========== CHECK END ==========\n")

        return jsonify({
            "success": True,
            "has_session": len(sessions_list) > 0,
            "sessions": sessions_list,
            "url": url
        })

    except Exception as e:
        print("\n========== CHECK ERROR ==========")
        traceback.print_exc()
        print("========== CHECK ERROR END ==========\n")
        return jsonify({
            "success": False,
            "has_session": False,
            "error": str(e)
        }), 500

# ---------------------------------------------------------
# 2. Scrape & Download Logic (Background Thread)
# ---------------------------------------------------------
def run_job(job_id, target_url, session, roll_list):
    job = JOBS[job_id]
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page()

            for roll_no in roll_list:
                try:
                    page.goto(target_url, wait_until="networkidle", timeout=30000)

                    if session:
                        selected = False
                        for select in page.query_selector_all("select"):
                            try:
                                select.select_option(label=session)
                                selected = True
                                break
                            except Exception:
                                try:
                                    select.select_option(value=session)
                                    selected = True
                                    break
                                except Exception:
                                    continue
                        if not selected:
                            try:
                                page.select_option("select", label=session)
                            except Exception:
                                pass

                    roll_input = (
                        page.query_selector("input[type='text']") or 
                        page.query_selector("input[name*='roll']") or 
                        page.query_selector("input[id*='roll']")
                    )

                    if roll_input is None:
                        inputs = page.query_selector_all("input")
                        for inp in inputs:
                            itype = (inp.get_attribute("type") or "").lower()
                            if itype in ["", "text", "number"]:
                                roll_input = inp
                                break

                    if roll_input is None:
                        raise Exception("Roll No input field not found")

                    roll_input.fill(str(roll_no))

                    clicked = False
                    button_selectors = [
                        "text=Get Result", "text=Search", "text=Submit",
                        "text=View Result", "text=Show Result", "text=Find Result",
                        "text=Search Result", "button[type='submit']", "input[type='submit']"
                    ]

                    for selector in button_selectors:
                        loc = page.locator(selector)
                        if loc.count() > 0:
                            loc.first.click()
                            clicked = True
                            break

                    if not clicked:
                        btn = page.query_selector("button") or page.query_selector("input[type='button']")
                        if btn:
                            btn.click()
                        else:
                            raise Exception("Submit button not found")

                    page.wait_for_load_state("networkidle", timeout=30000)
                    page.wait_for_timeout(1500)

                    pdf_path = os.path.join(out_dir, f"{roll_no}.pdf")
                    page.pdf(path=pdf_path, format="A4", print_background=True)

                    job["done"] += 1

                except Exception as e:
                    job["failed"].append({"roll_no": roll_no, "error": str(e)})
                finally:
                    job["processed"] += 1

            zip_path = os.path.join(JOBS_DIR, f"{job_id}.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                for fname in os.listdir(out_dir):
                    zf.write(os.path.join(out_dir, fname), fname)

            job["zip_path"] = zip_path
            job["status"] = "done"

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)

# ---------------------------------------------------------
# 3. Job Start Route
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

    if len(roll_list) > 300:
        return jsonify({"error": "ایک بار میں 300 سے زیادہ رول نمبرز کی اجازت نہیں"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "running",
        "total": len(roll_list),
        "processed": 0,
        "done": 0,
        "failed": [],
        "zip_path": None,
        "created": time.time(),
    }

    t = threading.Thread(target=run_job, args=(job_id, target_url, session, roll_list))
    t.start()

    return jsonify({"job_id": job_id})

# ---------------------------------------------------------
# 4. Job Status Route
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
# 5. Zip Download Route
# ---------------------------------------------------------
@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "not ready"}), 400
        
    return send_file(job["zip_path"], as_attachment=True, download_name=f"results_{job_id}.zip")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
