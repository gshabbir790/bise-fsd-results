import os
import uuid
import threading
import time
import logging
import traceback
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter, PdfReader

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

JOBS = {}
JOBS_DIR = "/tmp/bise_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs("results", exist_ok=True)

# ---------------------------------------------------------
# 0. Home Route (API Status Check)
# ---------------------------------------------------------
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "BISE Result Downloader API is running successfully!"
    })

# ---------------------------------------------------------
# 1. Check Website Route (فریمز سپورٹ + درست سیشن سلیکٹر اور میٹا ڈیٹا)
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
        session_selector = None

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )

            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768}
            )

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            keywords = ["session", "exam", "year", "sess"]

            def extract_from_context(context_page):
                nonlocal session_selector
                extracted = []
                try:
                    selects = context_page.query_selector_all('select')
                    for select in selects:
                        name = (select.get_attribute('name') or '').lower()
                        sid = (select.get_attribute('id') or '').lower()
                        
                        if any(k in name or k in sid for k in keywords):
                            options = select.query_selector_all('option')
                            for opt in options:
                                text = opt.inner_text().strip()
                                val = opt.get_attribute('value') or text
                                if text and not any(k in text.lower() for k in ['select', 'choose', 'پوچھیں', '--']):
                                    extracted.append({'label': text, 'value': val})
                            
                            if extracted and not session_selector:
                                session_selector = {
                                    "tag": "select",
                                    "id": select.get_attribute('id'),
                                    "name": select.get_attribute('name')
                                }
                except Exception:
                    pass
                return extracted

            # مین پیج سے چیک کریں
            sessions_list = extract_from_context(page)

            # اگر مین پیج پر نہ ملے تو فریمز میں چیک کریں
            if not sessions_list:
                for frame in page.frames:
                    sessions_list = extract_from_context(frame)
                    if sessions_list:
                        break

            print("Extracted Sessions:", sessions_list)
            print("Session Selector:", session_selector)
            print("========== CHECK END ==========\n")

        return jsonify({
            "success": True,
            "has_session": len(sessions_list) > 0,
            "sessions": sessions_list,
            "session_selector": session_selector,
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
# 2. Scrape & Download Logic (Background Thread + Validation)
# ---------------------------------------------------------
def run_job(job_id, target_url, session_value, session_label, selector_meta, roll_list):
    job = JOBS[job_id]
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context()

            for roll_no in roll_list:
                page = context.new_page()
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_load_state("networkidle")

                    # سیشن سلیکٹ کرنے کا محفوظ طریقہ (کوئی سائلنٹ فال بیک نہیں)
                    if session_value and selector_meta:
                        selector_str = None
                        if selector_meta.get("id"):
                            selector_str = f"#{selector_meta['id']}"
                        elif selector_meta.get("name"):
                            selector_str = f"select[name='{selector_meta['name']}']"

                        if selector_str:
                            try:
                                page.wait_for_selector(selector_str, timeout=10000)
                                page.select_option(selector_str, value=session_value)
                            except Exception as e:
                                raise Exception(f"Session '{session_label}' could not be selected using {selector_str}. Error: {e}")

                    # رول نمبر ان پٹ فیلڈ کی تلاش
                    roll_input = (
                        page.query_selector("input[type='text']") or 
                        page.query_selector("input[name*='roll']") or 
                        page.query_selector("input[id*='roll']")
                    )

                    if roll_input is None:
                        for inp in page.query_selector_all("input"):
                            itype = (inp.get_attribute("type") or "").lower()
                            if itype in ["", "text", "number"]:
                                roll_input = inp
                                break

                    if roll_input is None:
                        raise Exception("Roll No input field not found")

                    roll_input.fill(str(roll_no))

                    # سبمٹ بٹن پر کلک کرنا
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

                    # --- PDF Validity Check (نیا فیچر) ---
                    page_text = page.locator("body").inner_text().lower()
                    error_keywords = [
                        "record not found", 
                        "invalid roll number", 
                        "server error", 
                        "captcha",
                        "not found"
                    ]
                    
                    is_valid = True
                    for err in error_keywords:
                        if err in page_text:
                            is_valid = False
                            job["failed"].append({"roll_no": roll_no, "error": f"Page validation failed: {err.upper()}"})
                            break

                    if is_valid:
                        pdf_path = os.path.join(out_dir, f"{roll_no}.pdf")
                        page.pdf(path=pdf_path, format="A4", print_background=True)
                        job["done"] += 1

                except Exception as e:
                    job["failed"].append({"roll_no": roll_no, "error": str(e)})
                finally:
                    page.close()
                    job["processed"] += 1

            pdf_files = []
            for fname in os.listdir(out_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_files.append(fname)

            pdf_files.sort(key=lambda x: int(os.path.splitext(x)[0]))

            if not pdf_files:
                raise Exception("کوئی valid PDF تیار نہیں ہوئی")

            merged_path = os.path.join(JOBS_DIR, f"results_{job_id}.pdf")

            writer = PdfWriter()
            for fname in pdf_files:
                pdf_path = os.path.join(out_dir, fname)
                reader = PdfReader(pdf_path)
                for page in reader.pages:
                    writer.add_page(page)

            with open(merged_path, "wb") as output:
                writer.write(output)

            writer.close()

            job["merged_path"] = merged_path
            job["status"] = "done"
            browser.close()

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)

# ---------------------------------------------------------
# 3. Job Start Route
# ---------------------------------------------------------
@app.route("/api/job", methods=["POST"])
def start_job():
    data = request.get_json(silent=True) or {}
    target_url = data.get("url")
    session_value = data.get("session_value", "")
    session_label = data.get("session_label", "")
    session_selector = data.get("session_selector", None)
    
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
        return jsonify({"success": False, "error": "invalid input یا رول نمبرز درست نہیں ہیں"}), 400

    if len(roll_list) > 300:
        return jsonify({"success": False, "error": "ایک بار میں 300 سے زیادہ رول نمبرز کی اجازت نہیں"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "running",
        "total": len(roll_list),
        "processed": 0,
        "done": 0,
        "failed": [],
        "merged_path": None,
        "created": time.time(),
    }

    t = threading.Thread(
        target=run_job, 
        args=(job_id, target_url, session_value, session_label, session_selector, roll_list)
    )
    t.start()

    return jsonify({"success": True, "job_id": job_id})

# ---------------------------------------------------------
# 4. Job Status Route
# ---------------------------------------------------------
@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "job not found"}), 404
    return jsonify({
        "success": True,
        "status": job["status"],
        "total": job["total"],
        "processed": job["processed"],
        "done": job["done"],
        "failed": job["failed"],
        "error": job.get("error")
    })

# ---------------------------------------------------------
# 5. Merged PDF Download Route
# ---------------------------------------------------------
@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id):
    job = JOBS.get(job_id)

    if (
        not job
        or job["status"] != "done"
        or not job.get("merged_path")
        or not os.path.exists(job["merged_path"])
    ):
        return jsonify({
            "success": False,
            "error": "merged PDF not ready"
        }), 400

    return send_file(
        job["merged_path"],
        as_attachment=True,
        download_name=f"BISE_Results_{job_id}.pdf",
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
