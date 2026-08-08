import os
import re
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

# Vercel's Hobby-plan serverless functions hard-kill a request around ~10s.
# /api/job below is fully synchronous (background threads don't survive on
# Vercel), so we cap how many roll numbers one call may process — matches
# the limit already noted in the original comment, now actually enforced.
MAX_ROLLS_PER_JOB = 20


def _find_session_select(soup):
    """Finds the <select> that actually controls session/year/exam choice —
    NOT just "the first <select> on the page". FIX: the previous version
    used `soup.find("select")`, which grabs whichever dropdown happens to
    come first in the HTML (e.g. a "Board" or "Class" selector) if the site
    has more than one <select>. Posting the session value under the WRONG
    field's name silently leaves the real session field on its default
    value, so valid roll numbers get searched under the wrong session and
    come back "No record found". We match by name/id keyword first, same
    heuristic /api/check already uses, and only fall back to "first select"
    if nothing matches (so behavior never gets worse than before).
    """
    for select in soup.find_all("select"):
        name_attr = (select.get("name") or "").lower()
        id_attr = (select.get("id") or "").lower()
        if any(k in name_attr or k in id_attr for k in ("session", "exam", "ddl", "year")):
            return select, True
    first = soup.find("select")
    return first, False


def _find_roll_input(soup):
    """Finds the roll-number text input. FIX: the previous version tried
    `input[type='text']` FIRST — the least specific possible match. If the
    page has more than one text input (e.g. a site search box) positioned
    before the real roll-number field in the HTML, the roll number gets
    posted under the WRONG field's name while the real field is left empty
    — the search then runs with no roll number at all, so every result
    looks the same (whatever the page's default/blank state is) or comes
    back "No record found". We now try id/name containing "roll" FIRST and
    only fall back to the generic `type=text` match.
    """
    roll_input = soup.find("input", id=lambda x: x and "roll" in x.lower())
    if roll_input is None:
        roll_input = soup.find("input", attrs={"name": lambda x: x and "roll" in x.lower()})
    if roll_input is None:
        roll_input = soup.find("input", {"type": "text"})
    return roll_input, roll_input is not None and roll_input.get("id") and "roll" in (roll_input.get("id") or "").lower()


def _find_submit_control(soup, payload):
    """Finds the search/submit control and adds whatever the browser would
    have posted for it. Handles two real-world cases the previous version
    missed:
      1) A <button> with NO explicit type="submit" attribute — per the
         HTML spec a <button>'s default type IS "submit", but
         `soup.find("button", type="submit")` only matches when the
         attribute is explicitly present, so plain `<button>Search</button>`
         markup was silently skipped entirely.
      2) ASP.NET WebForms `LinkButton` controls, which render as
         `<a onclick="javascript:__doPostBack('id','')">Search</a>` instead
         of a real submit input — extremely common on WebForms sites. If
         nothing else was found, we extract the __doPostBack target and post
         __EVENTTARGET/__EVENTARGUMENT, which is the only way to actually
         trigger that control's server-side click.
    Returns True if a submit mechanism was identified (informational only).
    """
    submit_btn = soup.find("input", type="submit") or soup.find("button", type="submit")
    if submit_btn is None:
        for b in soup.find_all("button"):
            if b.get("type") is None:  # default button type is "submit"
                submit_btn = b
                break

    if submit_btn is not None:
        if submit_btn.get("name"):
            payload[submit_btn["name"]] = submit_btn.get("value", "Search")
        return True

    # No real submit control — look for an ASP.NET LinkButton doPostBack.
    postback_link = None
    candidates = soup.find_all("a", onclick=lambda v: v and "__doPostBack" in v)
    for a in candidates:
        text = a.get_text(strip=True).lower()
        if any(k in text for k in ("search", "submit", "get result", "show result", "view result", "find")):
            postback_link = a
            break
    if postback_link is None and candidates:
        postback_link = candidates[0]

    if postback_link is not None:
        m = re.search(r"__doPostBack\('([^']*)'\s*,\s*'([^']*)'\)", postback_link["onclick"])
        if m:
            payload["__EVENTTARGET"] = m.group(1)
            payload["__EVENTARGUMENT"] = m.group(2)
            return True

    return False


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

        select, matched_by_keyword = _find_session_select(soup)
        if select is not None and matched_by_keyword:
            has_session = True
            for opt in select.find_all("option"):
                text = opt.get_text(strip=True)
                val = opt.get("value", text)
                if text and not any(k in text.lower() for k in ['select', 'choose', '--']):
                    sessions_list.append({'label': text, 'value': val})

        return jsonify({
            'success': True,
            'has_session': has_session,
            'sessions': sessions_list,
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

    # FIX: previously unbounded — a large range would run past Vercel's sync
    # execution limit and the function gets killed mid-loop with NOTHING
    # saved (no partial zip, no job entry), which looks like a total failure
    # to the app for no obvious reason. Now rejected up front with a clear,
    # actionable message instead of a silent timeout.
    if len(roll_list) > MAX_ROLLS_PER_JOB:
        return jsonify({
            "error": (
                f"Vercel کے sync ٹائم آؤٹ کی وجہ سے ایک بار میں زیادہ سے زیادہ "
                f"{MAX_ROLLS_PER_JOB} رول نمبرز بھیجے جا سکتے ہیں (آپ نے "
                f"{len(roll_list)} بھیجے ہیں)۔ بڑی رینج کو چھوٹے حصوں میں "
                f"تقسیم کر کے الگ الگ درخواستیں بھیجیں۔"
            )
        }), 400

    job_id = str(uuid.uuid4())
    out_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(out_dir, exist_ok=True)

    sess = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    done = 0
    failed = []
    warnings = []

    for roll_no in roll_list:
        try:
            # 1. Get ViewState & Form Data — a FRESH GET every iteration, so
            #    __VIEWSTATE/__EVENTVALIDATION are never stale across roll
            #    numbers even though this loop is synchronous.
            init_res = sess.get(target_url, headers=headers, timeout=10)
            soup = BeautifulSoup(init_res.text, "html.parser")

            payload = {}
            for hidden in soup.find_all("input", type="hidden"):
                if hidden.get("name"):
                    payload[hidden["name"]] = hidden.get("value", "")

            roll_input, roll_matched_confidently = _find_roll_input(soup)
            if roll_input and roll_input.get("name"):
                payload[roll_input["name"]] = str(roll_no)
            else:
                warnings.append(f"Roll {roll_no}: roll-number input field not found on the page.")

            if session_val:
                select_tag, matched_by_keyword = _find_session_select(soup)
                if select_tag and select_tag.get("name"):
                    payload[select_tag["name"]] = session_val
                    if not matched_by_keyword:
                        warnings.append(
                            f"Roll {roll_no}: session field guessed (no select named "
                            f"'session/exam/ddl/year' found) — result may use the wrong session."
                        )

            submit_found = _find_submit_control(soup, payload)
            if not submit_found:
                warnings.append(f"Roll {roll_no}: no submit control found — form may not have been triggered.")

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
        # FIX: previously nothing surfaced *why* a page came back wrong —
        # now the client (or you, debugging) can see exactly which
        # field-matching step was uncertain for which roll number.
        "warnings": warnings,
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
