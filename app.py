import os
import uuid
import zipfile
import threading
import time

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from playwright.sync_api import sync_playwright

app = Flask(__name__)
CORS(app)  # frontend کو یہ backend استعمال کرنے کی اجازت دیتا ہے

JOBS = {}  # job_id -> {status, total, processed, done, failed, zip_path}
JOBS_DIR = "/tmp/bise_jobs"
os.makedirs(JOBS_DIR, exist_ok=True)


def run_job(job_id, target_url, session, start_roll, end_roll):
    job = JOBS[job_id]
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            for roll_no in range(start_roll, end_roll + 1):
                try:
                    # اب یہ فرنٹ اینڈ سے موصول ہونے والا متحرک یو آر ایل استعمال کرے گا
                    page.goto(target_url, wait_until="networkidle", timeout=30000)

                    # اگر سیشن موجود ہو تب ہی سلیکٹ کرنے کی کوشش کرے گا
                    if session:
                        try:
                            page.select_option("select", label=session)
                        except Exception:
                            for dd in page.query_selector_all("select"):
                                try:
                                    dd.select_option(label=session)
                                    break
                                except Exception:
                                    continue

                    roll_input = page.query_selector("input[type='text']")
                    if roll_input is None:
                        raise Exception("Roll No field not found")
                    roll_input.fill(str(roll_no))

                    page.click("text=Get Result")
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

        # تمام پی ڈی ایف فائلز کو زپ (ZIP) کرنا
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
    target_url = data.get("url")  # فرنٹ اینڈ سے یو آر ایل حاصل کیا جا رہا ہے
    session = data.get("session", "")  # سیشن اختیاری ہو سکتا ہے
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
    return jsonify({"status": "ok", "message": "BISE FSD backend is running"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
