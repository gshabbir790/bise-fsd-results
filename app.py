import os
import time
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)

def download_results():
    # یہاں آپ اپنی ضرورت کے مطابق URL اور رول نمبرز سیٹ کر سکتے ہیں
    target_url = os.environ.get("TARGET_URL", "https://example.com/result") # یہاں بورڈ کی لنک دیں
    roll_no = os.environ.get("ROLL_NO", "123456") # یہاں رول نمبر دیں
    
    out_dir = "/tmp/bise_results"
    os.makedirs(out_dir, exist_ok=True)

    logging.info(f"Starting download for Roll No: {roll_no}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page()

            # ویب سائٹ پر جائیں
            page.goto(target_url, wait_until="networkidle", timeout=30000)

            # رول نمبر ان پٹ فیلڈ تلاش کریں اور نمبر لکھیں
            roll_input = (
                page.query_selector("input[type='text']") or 
                page.query_selector("input[name*='roll']") or 
                page.query_selector("input[id*='roll']")
            )

            if roll_input is None:
                raise Exception("Roll No input field not found")

            roll_input.fill(str(roll_no))

            # سرچ یا سبمٹ بٹن پر کلک کریں
            button_selectors = [
                "text=Get Result", "text=Search", "text=Submit",
                "text=View Result", "text=Show Result", "button[type='submit']"
            ]

            clicked = False
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

            # رزلٹ لوڈ ہونے کا انتظار کریں اور پی ڈی ایف سیو کریں
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            pdf_path = os.path.join(out_dir, f"{roll_no}.pdf")
            page.pdf(path=pdf_path, format="A4", print_background=True)
            
            logging.info(f"Successfully downloaded PDF to {pdf_path}")
            browser.close()

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")

if __name__ == "__main__":
    download_results()
