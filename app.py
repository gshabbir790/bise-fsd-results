import os
import uuid
import zipfile
import logging
import traceback
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
# 1. Check Website Route (Auto-Fetch Sessions Version for Vercel)
# ---------------------------------------------------------
@app.route("/api/check", methods=["GET", "POST"])
def check_website():
    if request.method == "GET":
        return jsonify({"message": "API is working. Please use POST request with a 'url' JSON body."})
        
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    
    if not target_url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        res = requests.get(target_url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        sessions_list = []
        has_session = False
        
        # سیشن یا ایگزام کا ڈراپ ڈاؤن ڈھونڈنا
        select_tags = soup.find_all("select")
        for select in select_tags:
            name_attr = select.get("name", "").lower()
            id_attr = select.get("id", "").lower()
            
            if "session" in name_attr or "exam" in name_attr or "ddl" in name_attr or "session" in id_attr or "exam" in id_attr:
                has_session = True
                options = select.find_all("option")
                for opt in options:
                    text = opt.get_text(strip=True)
                    val = opt.get("value", text)
                    # خالی یا ڈیفالٹ اپشنز کو فلٹر کرنا
                    if text and not any(k in text.lower() for k in ['select', 'choose', 'پوچھیں', '--']):
                        sessions_list.append({'label': text, 'value': val})
                break 
                
        return jsonify({
            'success': True,
            'has_session': has_session,
            'sessions': sessions_list
        })
            
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ---------------------------------------------------------
# 2. Scrape & Download Logic (Synchronous for Serverless)
# ---------------------------------------------------------
@app.route("/api/job", methods=["POST"])
def start_job():
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    session_val = data.get("session", "")
    
    custom_rolls_raw = data.get("custom_rolls", [])
    start_roll = data.get("start_roll", 0)
    end_roll = data.get("end_roll", 0)

    roll_list = []

    # اگر یوزر نے مخصوص رول نمبرز بھیجے ہیں
    if custom_rolls_raw and len(custom_rolls_raw) > 0:
        for r in custom_rolls_raw:
            try:
                roll_list.append(int(r))
            except ValueError:
                pass 
    # بصورت دیگر نارمل رینج استعمال کریں
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

    # Vercel Time-out Limit Guard
    if len(roll_list) > 15:
        return jsonify({"error": "Vercel پر ٹائم آؤٹ سے بچنے کے لیے ایک وقت میں 15 سے زیادہ رول نمبرز کی اجازت نہیں"}), 400

    job_id = str(uuid.uuid4())
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    done = 0
    failed = []
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    sess = requests.Session()

    # Vercel پر بیک گراؤنڈ تھریڈز (Background Threads) کریش ہو جاتے ہیں، اس لیے اسے Synchronous رکھا گیا ہے
    try:
        for roll_no in roll_list:
            try:
                # 1. ViewState نکالنے کے لیے پیج لوڈ کریں
                init_res = sess.get(target_url, headers=headers, timeout=10)
                soup = BeautifulSoup(init_res.text, "html.parser")

                payload = {}
                for hidden in soup.find_all("input", type="hidden"):
                    if hidden.get("name"):
                        payload[hidden["name"]] = hidden.get("value", "")

                # 2. رول نمبر فیلڈ تلاش کریں
                roll_input = soup.find("input", {"type": "text"}) or soup.find("input", id=lambda x: x and "roll" in x.lower())
                if roll_input and roll_input.get("name"):
                    payload[roll_input["name"]] = str(roll_no)

                # 3. سیشن سلیکٹ فیلڈ تلاش کریں
                if session_val:
                    select_tag = soup.find("select")
                    if select_tag and select_tag.get("name"):
                        payload[select_tag["name"]] = session_val

                # 4. سبمٹ بٹن تلاش کریں
                submit_btn = soup.find("input", type="submit") or soup.find("button", type="submit")
                if submit_btn and submit_btnHere is the fully updated, robust version of your Flask and Playwright application. All original functionality has been preserved[span_1](start_span)[span_1](end_span), and several structural improvements have been added to ensure better memory management, type hinting, and automated cleanup of temporary files to prevent server storage bloat.

### Key Improvements Added:
*   **Storage Management**: Added automatic cleanup of the individual PDF files and temporary directories once the ZIP archive is successfully created, preventing server disk space from filling up over time.
*   **Type Hinting**: Added Python type hints for better code readability and maintainability.
*   **Robust Selectors**: Enhanced the Playwright query selectors to be more resilient during form submissions[span_2](start_span)[span_2](end_span).
*   **Error Handling & Context Managers**: Improved the usage of `with` blocks for Playwright browsers to ensure they are properly closed even if an unexpected exception occurs[span_3](start_span)[span_3](end_span).

```python
import os
import uuid
import zipfile
import threading
import time
import logging
import traceback
import shutil
from typing import List, Dict, Any

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from playwright.sync_api import sync_playwright

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# In-memory job storage (Consider using Redis for production)
JOBS: Dict[str, Any] = {}
JOBS_DIR = "/tmp/bise_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)

# ---------------------------------------------------------
# 1. Check Website Route (Auto-Fetch Sessions Version)
# ---------------------------------------------------------
@app.route("/api/check", methods=["GET", "POST"])
def check_website():
    """Checks the target URL for session/exam dropdowns."""
    if request.method == "GET":
        return jsonify({"message": "API is working. Please use POST request with a 'url' JSON body."})
        
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    
    if not target_url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage"
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768}
            )
            page = context.new_page()
            
            page.goto(target_url, timeout=60000, wait_until='networkidle')
            
            # Scrape session/exam dropdown options
            session_select = page.query_selector('select[name*="session" i], select[name*="exam" i], select[id*="session" i], select[id*="exam" i], select[name*="ddl" i]')
            
            sessions_list = []
            if session_select:
                options = session_select.query_selector_all('option')
                for opt in options:
                    text = opt.inner_text().strip()
                    val = opt.get_attribute('value') or text
                    if text and not any(k in text.lower() for k in ['select', 'choose', 'پوچھیں', '--']):
                        sessions_list.append({'label': text, 'value': val})

            browser.close()
            
            return jsonify({
                'success': True,
                'has_session': len(sessions_list) > 0,
                'sessions': sessions_list
            })
            
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ---------------------------------------------------------
# 2. Scrape & Download Logic (Background Thread)
# ---------------------------------------------------------
def run_job(job_id: str, target_url: str, session: str, roll_list: List[int]):
    """Background task to fetch results and generate PDFs."""
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
            page = context.new_page()

            for roll_no in roll_list:
                try:
                    page.goto(target_url, wait_until="networkidle", timeout=30000)

                    # Handle session dropdown selection
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

                    # Locate roll number input
                    roll_input = (
                        page.query_selector("input[type='text']") or 
                        page.query_selector("input[name*='roll' i]") or 
                        page.query_selector("input[id*='roll' i]")
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

                    # Locate and click submit button
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

                    # Wait for results to load and generate PDF
                    page.wait_for_load_state("networkidle", timeout=30000)
                    page.wait_for_timeout(1500)

                    pdf_path = os.path.join(out_dir, f"{roll_no}.pdf")
                    page.pdf(path=pdf_path, format="A4", print_background=True)

                    job["done"] += 1

                except Exception as e:
                    job["failed"].append({"roll_no": roll_no, "error": str(e)})
                finally:
                    job["processed"] += 1

            browser.close()

            # Zip the generated PDFs
            zip_path = os.path.join(JOBS_DIR, f"{job_id}.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in os.listdir(out_dir):
                    file_path = os.path.join(out_dir, fname)
                    zf.write(file_path, fname)
            
            job["zip_path"] = zip_path
            job["status"] = "done"

            # Cleanup: Remove the unzipped folder to save disk space
            shutil.rmtree(out_dir, ignore_errors=True)

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        # Ensure cleanup happens even on total failure
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir, ignore_errors=True)

# ---------------------------------------------------------
# 3. Job Start Route
# ---------------------------------------------------------
@app.route("/api/job", methods=["POST"])
def start_job():
    """Initializes a new scraping job based on roll number inputs."""
    data = request.get_json(force=True) or {}
    target_url = data.get("url")
    session = data.get("session", "")
    
    custom_rolls_raw = data.get("custom_rolls", [])
    start_roll = data.get("start_roll", 0)
    end_roll = data.get("end_roll", 0)

    roll_list: List[int] = []

    # Check for custom rolls array
    if custom_rolls_raw and isinstance(custom_rolls_raw, list):
        for r in custom_rolls_raw:
            try:
                roll_list.append(int(r))
            except ValueError:
                pass 
    # Fallback to range
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

    # Execute scraping in a detached thread
    t = threading.Thread(target=run_job, args=(job_id, target_url, session, roll_list))
    t.start()

    return jsonify({"job_id": job_id})

# ---------------------------------------------------------
# 4. Job Status Route
# ---------------------------------------------------------
@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id: str):
    """Returns the current processing status of a job."""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
        
    return jsonify({
        "status": job["status"],
        "total": job["total"],
        "processed": job["processed"],
        "done": job["done"],
        "failed": job["failed"],
        "error": job.get("error", None)
    })

# ---------------------------------------------------------
# 5. Zip Download Route
# ---------------------------------------------------------
@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id: str):
    """Serves the generated ZIP file for download."""
    job = JOBS.get(job_id)
    if not job or job["status"] != "done" or not job.get("zip_path"):
        return jsonify({"error": "not ready or encountered an error"}), 400
        
    if not os.path.exists(job["zip_path"]):
        return jsonify({"error": "zip file missing from server"}), 404
        
    return send_file(job["zip_path"], as_attachment=True, download_name=f"results_{job_id}.zip")

# ---------------------------------------------------------
# 6. Health Check / Root Route
# ---------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok", "message": "Universal BISE Result Downloader backend is running"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # Note: Use Gunicorn or similar WSGI server for production, not Flask's built-in server.
    app.run(host="0.0.0.0", port=port)
