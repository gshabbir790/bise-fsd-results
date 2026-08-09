import os
import logging
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

logging.basicConfig(level=logging.INFO)

def download_and_convert_results():
    target_url = os.environ.get("TARGET_URL", "")
    session_val = os.environ.get("SESSION", "")
    merge_choice = os.environ.get("MERGE_PDFS", "Yes (Merge into one file)")
    
    if session_val == 'None':
        session_val = ""

    try:
        start_roll = int(os.environ.get("START_ROLL", "100001"))
        end_roll = int(os.environ.get("END_ROLL", "100005"))
    except ValueError:
        logging.error("Roll numbers must be valid numbers.")
        return

    roll_list = list(range(start_roll, end_roll + 1))
    
    pdf_dir = "/tmp/bise_results"
    os.makedirs(pdf_dir, exist_ok=True)

    successful_pdfs = []

    logging.info(f"Starting lightning-fast Playwright download for {len(roll_list)} roll numbers...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context()
            page = context.new_page()

            # فالتو تصاویر اور فونٹس بلاک کرنا تاکہ سپیڈ تیز ہو
            page.route("**/*.{png,jpg,jpeg,svg,gif,woff,woff2}", lambda route: route.abort())

            # ویب سائٹ کو صرف ایک بار کھولیں
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

            # اگر سیشن موجود ہو تو اسے ایک بار سلیکٹ کر لیں
            if session_val:
                for select in page.query_selector_all("select"):
                    try:
                        select.select_option(label=session_val)
                        break
                    except Exception:
                        try:
                            select.select_option(value=session_val)
                            break
                        except Exception:
                            continue

            for roll_no in roll_list:
                try:
                    # رول نمبر ان پٹ فیلڈ تلاش کریں
                    roll_input = (
                        page.query_selector("input[id*='roll']") or
                        page.query_selector("input[name*='roll']") or
                        page.query_selector("input[type='text']")
                    )

                    if roll_input is None:
                        raise Exception("Roll number input field not found")

                    # پرانا نمبر مٹا کر نیا رول نمبر لکھیں
                    roll_input.fill("")
                    roll_input.fill(str(roll_no))

                    # سرچ بٹن پر کلک کریں
                    button_selectors = [
                        "input[type='submit']", "button[type='submit']",
                        "text=Search", "text=Get Result", "text=Submit", "text=View Result"
                    ]
                    
                    clicked = False
                    for selector in button_selectors:
                        loc = page.locator(selector)
                        if loc.count() > 0:
                            loc.first.click()
                            clicked = True
                            break

                    if not clicked:
                        page.evaluate("if(typeof __doPostBack == 'function') { __doPostBack(); }")

                    # رزلٹ لوڈ ہونے کا انتظار کریں
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    
                    pdf_path = os.path.join(pdf_dir, f"{roll_no}.pdf")
                    page.pdf(path=pdf_path, format="A4", print_background=True)
                    successful_pdfs.append(pdf_path)
                    
                    logging.info(f"Successfully generated PDF for Roll No {roll_no}")

                    # اگر ویب سائٹ رزلٹ دکھانے کے بعد دوسرے پیج پر چلی گئی ہے تو واپس سرچ فارم پر آئیں
                    if page.url != target_url:
                        page.go_back(wait_until="domcontentloaded")

                except Exception as e:
                    logging.error(f"Failed for Roll No {roll_no}: {str(e)}")
                    # اگر کوئی ایرر آئے تو کوشش کریں کہ واپس مین پیج پر آ جائے
                    try:
                        if page.url != target_url:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                    except:
                        pass

            browser.close()

        # پی ڈی ایف مرج کرنے کا عمل
        if "Yes" in merge_choice and successful_pdfs:
            logging.info("Merging all PDFs into a single master file...")
            merger = PdfWriter()
            for pdf in successful_pdfs:
                merger.append(pdf)
            
            merged_pdf_path = os.path.join(pdf_dir, "All_Results_Merged.pdf")
            merger.write(merged_pdf_path)
            merger.close()

            for pdf in successful_pdfs:
                try:
                    os.remove(pdf)
                except Exception:
                    pass

            logging.info("Successfully created merged PDF and removed individual files.")

    except Exception as e:
        logging.error(f"Error during execution: {str(e)}")

if __name__ == "__main__":
    download_and_convert_results()
            
