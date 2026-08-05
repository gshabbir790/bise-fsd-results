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


@app.route("/api/check", methods=["POST"])
def check_website():
    data = request.get_json(force=True)
    url = data.get("url")

    if not url:
        return jsonify({"error": "url is required"}), 400

    has_session = False
    try:
        with sync_playwright() as p:
            # Railway اور Linux کے لیے مستحکم براؤزر لانچ کنفیگریشن
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)

            for select in page.query_selector_all("select"):
                sid = (select.get_attribute("id") or "").lower()
                sname = (select.get_attribute("name") or "").lower()
                text = (select.inner_text() or "").lower()

                # "year" کو ہٹا کر صرف درست سیشن کی ورڈز رکھے گئے ہیں تاکہ false positive نہ ہو
                if any(k in sid for k in ["session", "sess"]):
                    has_session = True
                    break
                if any(k in sname for k in ["session", "sess"]):
                    has_session = True
                    break
                if any(k in text for k in ["session", "annual", "supplementary", "1st annual", "2nd annual"]):
                    has_session = True
                    break

            browser.close()
    except Exception as e:
        print(f"Check URL Error: {e}")

    return jsonify({"has_session": has_session})


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

                    # سیشن سلیکٹ کرنے کا عمل
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

                    # رول نمبر ان پٹ فیلڈ تلاش کرنا (سنٹیکس ایرر درست کر دیا گیا ہے)
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

                    # یونیورسل بٹن کلک کرنے کا طریقہ (Locator استعمال کرتے ہوئے)
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


@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "not ready"}), 400
    return send_file(job["zip_path"], as_attachment=True, download_name=f"results_{job_id}.zip")


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Universal BISE Result Downloader backend is running"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
