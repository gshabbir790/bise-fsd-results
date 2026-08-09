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

    logging.info(f"Starting optimized Playwright download for {len(roll_list)} roll numbers...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context()
            page = context.new_page()

            # سپیڈ تیز کرنے کے لیے تصاویر اور فالتو چیزوں کو بلاک کرنا
            page.route("**/*.{png,jpg,jpeg,svg,gif,woff,woff2}", lambda route: route.abort())

            for roll_no in roll_list:
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

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

                    roll_input = (
                        page.query_selector("input[id*='roll']") or
                        page.query_selector("input[name*='roll']") or
                        page.query_selector("input[type='text']")
                    )

                    if roll_input is None:
                        raise Exception("Roll number input field not found")

                    roll_input.fill(str(roll_no))

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

                    page.wait_for_load_state("networkidle", timeout=15000)
                    
                    pdf_path = os.path.join(pdf_dir, f"{roll_no}.pdf")
                    page.pdf(path=pdf_path, format="A4", print_background=True)
                    successful_pdfs.append(pdf_path)
                    
                    logging.info(f"Successfully generated PDF for Roll No {roll_no}")

                except Exception as e:
                    logging.error(f"Failed for Roll No {roll_no}: {str(e)}")

            browser.close()

        # اگر یوزر نے مرج کا کہا ہے تو تمام پی ڈی ایف کو جوڑ کر الگ الگ فائلیں ڈیلیٹ کر دیں
        if "Yes" in merge_choice and successful_pdfs:
            logging.info("Merging all PDFs into a single master file and cleaning up separate files...")
            merger = PdfWriter()
            for pdf in successful_pdfs:
                merger.append(pdf)
            
            merged_pdf_path = os.path.join(pdf_dir, "All_Results_Merged.pdf")
            merger.write(merged_pdf_path)
            merger.close()

            # اب الگ الگ فائلوں کو ڈیلیٹ کر دیں تاکہ صرف ایک سنگل فائل بچے
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
                        
