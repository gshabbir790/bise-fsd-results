import os
import threading
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

app = Flask(__name__)

# PDF محفوظ کرنے کے لیے فولڈر
os.makedirs("results", exist_ok=True)

def check_bise_url(url):
    """
    URL چیک کرنے اور درست Session Dropdown کی شناخت کرنے کا فنکشن۔
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # ASP.NET پیجز کے لیے domcontentloaded اور networkidle کا بہتر combination
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle")
            
            # 'ddl' کو نکال دیا گیا ہے تاکہ غلط detection نہ ہو
            keywords = ["session", "exam", "year", "sess"]
            selects = page.locator("select").all()
            
            session_data = []
            session_selector = None

            for select in selects:
                name = (select.get_attribute("name") or "").lower()
                id_attr = (select.get_attribute("id") or "").lower()
                
                # درست dropdown کی شناخت
                if any(k in name or k in id_attr for k in keywords):
                    # Options کے لوڈ ہونے کا انتظار (اگر dynamically populate ہو رہے ہوں)
                    select.wait_for_element_state("visible")
                    
                    options = select.locator("option").all()
                    for opt in options:
                        val = opt.get_attribute("value")
                        text = opt.inner_text().strip()
                        # 'Select' یا خالی آپشنز کو نظر انداز کریں
                        if val and text and "select" not in text.lower():
                            session_data.append({"label": text, "value": val})
                    
                    if session_data:
                        session_selector = {
                            "tag": "select",
                            "id": select.get_attribute("id"),
                            "name": select.get_attribute("name")
                        }
                        break  # پہلا درست dropdown ملنے پر رک جائیں

            return {
                "success": True,
                "has_session": bool(session_data),
                "sessions": session_data,
                "session_selector": session_selector
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            browser.close()

@app.route('/api/check', methods=['POST'])
def api_check():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400
    
    result = check_bise_url(url)
    return jsonify(result)

def process_bulk_download(job_data):
    """
    Background worker جو محفوظ طریقے سے سیشن سلیکٹ کرے گا اور PDFs بنائے گا۔
    """
    url = job_data['url']
    session_value = job_data['session_value']
    session_label = job_data['session_label']
    selector_meta = job_data['session_selector']
    roll_numbers = job_data['roll_numbers']
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        
        for roll in roll_numbers:
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle")
                
                # Selector Metadata کا استعمال کرتے ہوئے درست Dropdown تلاش کرنا
                selector_str = None
                if selector_meta and selector_meta.get("id"):
                    selector_str = f"#{selector_meta['id']}"
                elif selector_meta and selector_meta.get("name"):
                    selector_str = f"select[name='{selector_meta['name']}']"
                    
                if not selector_str:
                    raise ValueError("No valid session selector metadata provided.")
                
                # سیشن سلیکٹ کرنا (بدون silent fallback)
                try:
                    page.wait_for_selector(selector_str, timeout=10000)
                    page.select_option(selector_str, value=session_value)
                except Exception as e:
                    # واضح ایرر، کوئی blind selection نہیں
                    raise Exception(f"Session '{session_label}' could not be selected. Selector used: {selector_str}. Error: {e}")

                # یہاں آپ کے Roll Number input اور Submit بٹن کا logic آئے گا
                # مثال کے طور پر:
                # page.fill("input[name='rollnumber']", str(roll))
                # page.click("input[type='submit']")
                
                page.wait_for_load_state("networkidle")
                
                # --- PDF Validity Check ---
                # پیج کا ٹیکسٹ نکال کر ایررز چیک کریں
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
                        print(f"[FAILED] Roll {roll} skipped. Reason: {err.upper()} detected on page.")
                        # یہاں آپ failed_rolls کی لسٹ میں بھی اضافہ کر سکتے ہیں
                        break
                        
                # صرف درست رزلٹ ہونے پر PDF بنائیں
                if is_valid:
                    pdf_path = f"results/{roll}.pdf"
                    page.pdf(path=pdf_path, format="A4", print_background=True)
                    print(f"[SUCCESS] Roll {roll} saved to {pdf_path}")
                    # job["done"] += 1 (اگر آپ کے پاس global status object ہو)
                    
            except Exception as e:
                print(f"[ERROR] Exception processing Roll {roll}: {str(e)}")
            finally:
                page.close()
                
        browser.close()

@app.route('/api/job', methods=['POST'])
def api_job():
    data = request.json
    
    # Validation
    required_fields = ['url', 'session_value', 'session_label', 'session_selector', 'roll_numbers']
    for field in required_fields:
        if field not in data:
            return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400

    # Job کو background میں چلائیں تاکہ API فوراً رسپانس دے سکے
    thread = threading.Thread(target=process_bulk_download, args=(data,))
    thread.start()
    
    return jsonify({
        "success": True, 
        "message": f"Job started successfully for {len(data['roll_numbers'])} roll numbers."
    })

if __name__ == '__main__':
    # Railway deployment کے لیے PORT environment variable استعمال کریں
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
