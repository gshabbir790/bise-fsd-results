import os
import uuid
import zipfile
import threading
import time

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from playwright.sync_api import sync_playwright

app = Flask(__name__)
CORS(app)

JOBS = {}
JOBS_DIR = "/tmp/bise_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)

# ---------------------------------------------------------
# 1. Check Website Route (Advanced Debugging Version)
# ---------------------------------------------------------
@app.route("/api/check", methods=["GET", "POST"])
def check_website():
    if request.method == "GET":
        return jsonify({"message": "API is working. Please use POST request with a 'url' JSON body."})

    data = request.get_json(force=True)
    url = data.get("url")

    if not url:
        return jsonify({"error": "url is required"}), 400

    has_session = False
    browser = None  # Finally block کے لیے متغیر
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            
            # User-Agent اور Viewport شامل کر دیا گیا
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768}
            )
            
            print("--- ADVANCED DEBUGGING START ---")
            
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            print("Current URL:", page.url)
            print("Title:", page.title())

            # HTML کا حصہ پرنٹ کرنا
            html = page.content()
            print("HTML Length:", len(html))
            print("HTML Snippet (first 3000 chars):\n", html[:3000])
            
            # Screenshot لینا (Railway پر /tmp فولڈر استعمال کرنا بہتر ہے)
            page.screenshot(path="/tmp/debug.png", full_page=True)
            print("Screenshot saved at /tmp/debug.png")

            # تمام جدید Locators کی گنتی
            print("Select count (Main Page):", page.locator("select").count())
            print("Input count:", page.locator("input").count())
            print("Button count:", page.locator("button").count())
            print("Form count:", page.locator("form").count())
            print("Combobox count:", page.locator("[role='combobox']").count())
            print("Select2 count:", page.locator(".select2").count())
            print("Bootstrap Select count:", page.locator(".bootstrap-select").count())
            print("Iframe count:", page.locator("iframe").count())

            frames = page.frames
            print("Total Frames (including main):", len(frames))

            for i, frame in enumerate(frames):
                print(f"Frame [{i}] URL: {frame.url}")
                # فریم کے اندر سلیکٹس چیک کرنا
                frame_selects = frame.query_selector_all("select")
                for s in frame_selects:
                    options = s.query_selector_all("option")
                    if len(options) > 1:
                        has_session = True

            print("Final has_session =", has_session)
            print("--- ADVANCED DEBUGGING END ---")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Check URL Error: {e}")
    finally:
        # Browser کو محفوظ طریقے سے بند کرنا
        if browser:
            browser.close()

    return jsonify({"has_session": has_session})

# ---------------------------------------------------------
# 2. Scrape & Download Logic (Background Thread)
# ---------------------------------------------------------
def run_job(job_id, target_url, session, start_roll, end_roll):
    job = JOBS[job_id]
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            page = browser.new_page()

            for roll_no in range(start_roll, end_roll + 1):
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
                        page.query_selector("input[type='text']")
                        or page.query_selector("input[name*='roll']")
                        or page.query_selector("input[id*='roll']")
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
                        "text=Get Result",
                        "text=Search",
                        "text=Submit",
                        "text=View Result",
                        "text=Show Result",
                        "text=Find Result",
                        "text=Search Result",
                        "button[type='submit']",
                        "input[type='submit']"
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

            browser.close()

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
    data = request.get_json(force=True)
    target_url = data.get("url")
    session = data.get("session", "")
    start_roll = int(data.get("start_roll"))
    end_roll = int(data.get("end_roll"))

    if not target_url or start_roll > end_roll:
        return jsonify({"error": "invalid input"}), 400

    if (end_roll - start_roll + 1) > 300:
        return jsonify({"error": "ایک بار میں 300 سے زیادہ رول نمبرز کی اجازت نہیں"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "running",
        "total": end_roll - start_roll + 1,
        "processed": 0,
        "done": 0,
        "failed": [],
        "zip_path": None,
        "created": time.time(),
    }

    t = threading.Thread(target=run_job, args=(job_id, target_url, session, start_roll, end_roll))
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

# ---------------------------------------------------------
# 6. Health Check / Root Route
# ---------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Universal BISE Result Downloader backend is running"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
