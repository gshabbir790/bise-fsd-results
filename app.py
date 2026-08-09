import os
import time
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)

def download_results():
    # گٹ ہب کے ان پٹس (UI) سے ویلیوز حاصل کرنا
    target_url = os.environ.get("TARGET_URL", "https://www.bisefgd.edu.pk/result")
    session = os.environ.get("SESSION", "")
    
    # رول نمبرز کو انٹیجر (Integer) میں تبدیل کرنا
    try:
        start_roll = int(os.environ.get("START_ROLL", "100001"))
        end_roll = int(os.environ.get("END_ROLL", "100005"))
    except ValueError:
        logging.error("Roll numbers must be valid numbers.")
        return

    # دی گئی رینج کے مطابق رول نمبرز کی لسٹ بنانا
    roll_list = list(range(start_roll, end_roll + 1))

    # رزلٹ محفوظ کرنے کے لیے فولڈر بنانا
    out_dir = "/tmp/bise_results"
    os.makedirs(out_dir, exist_ok=True)

    logging.info(f"Starting download for {len(roll_list)} roll numbers from {start_roll} to {end_roll}...")

    try:
        with sync_playwright() as p:
            # براؤزر کو ہیڈلیس موڈ (بیک گراؤنڈ) میں لانچ کرنا
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page()

            for roll_no in roll_list:
                try:
                    # ویب سائٹ پر جائیں
                    page.goto(target_url, wait_until="networkidle", timeout=30000)

                    # اگر سیشن سلیکٹ کرنے کی ضرورت ہو تو اسے سلیکٹ کریں
                    if session:
                        for select in page.query_selector_all("select"):
                            try:
                                select.select_option(label=session)
                                break
                            except Exception:
                                try:
                                    select.select_option(value=session)
                                    break
                                except Exception:
                                    continue

                    # رول نمبر ان پٹ فیلڈ تلاش کریں اور نمبر درج کریں
                    roll_input = (
                        page.query_selector("input[type='text']") or 
                        page.query_selector("input[name*='roll']") or 
                        page.query_selector("input[id*='roll']")
                    )

                    if roll_input is None:
                        raise Exception("Roll No input field not found")

                    roll_input.fill(str(roll_no))

                    # سرچ یا سبمٹ بٹن تلاش کر کے اس پر کلک کریں
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
                    page.wait_for_timeout(1500)

                    pdf_path = os.path.join(out_dir, f"{roll_no}.pdf")
                    page.pdf(path=pdf_path, format="A4", print_background=True)
                    
                    logging.info(f"Successfully downloaded: Roll No {roll_no}")

                except Exception as e:
                    logging.error(f"Failed for Roll No {roll_no}: {str(e)}")

            browser.close()
            logging.info("All results downloaded successfully!")

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")

if __name__ == "__main__":
    download_results()
