import os
import re
import logging
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from pypdf import PdfMerger

logging.basicConfig(level=logging.INFO)

def _find_session_select(soup):
    for select in soup.find_all("select"):
        name_attr = (select.get("name") or "").lower()
        id_attr = (select.get("id") or "").lower()
        if any(k in name_attr or k in id_attr for k in ("session", "exam", "ddl", "year")):
            return select, True
    first = soup.find("select")
    return first, False

def _find_roll_input(soup):
    roll_input = soup.find("input", id=lambda x: x and "roll" in x.lower())
    if roll_input is None:
        roll_input = soup.find("input", attrs={"name": lambda x: x and "roll" in x.lower()})
    if roll_input is None:
        roll_input = soup.find("input", {"type": "text"})
    return roll_input, roll_input is not None and roll_input.get("id") and "roll" in (roll_input.get("id") or "").lower()

def _find_submit_control(soup, payload):
    submit_btn = soup.find("input", type="submit") or soup.find("button", type="submit")
    if submit_btn is None:
        for b in soup.find_all("button"):
            if b.get("type") is None:
                submit_btn = b
                break
    if submit_btn is not None:
        if submit_btn.get("name"):
            payload[submit_btn["name"]] = submit_btn.get("value", "Search")
        return True
    
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

def download_and_convert_results():
    target_url = os.environ.get("TARGET_URL", "")
    session_val = os.environ.get("SESSION", "")
    merge_choice = os.environ.get("MERGE_PDFS", "Yes (Merge into one file)")
    
    if session_val == 'None (No session required)':
        session_val = ""

    try:
        start_roll = int(os.environ.get("START_ROLL", "100001"))
        end_roll = int(os.environ.get("END_ROLL", "100005"))
    except ValueError:
        logging.error("Roll numbers must be valid numbers.")
        return

    roll_list = list(range(start_roll, end_roll + 1))
    
    html_dir = "/tmp/bise_htmls"
    pdf_dir = "/tmp/bise_results"
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    parsed_url = urlparse(target_url)
    base_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

    sess = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # مرحلہ 1: HTML ڈاؤن لوڈ کرنا
    logging.info(f"Step 1: Downloading HTML for {len(roll_list)} roll numbers...")
    for roll_no in roll_list:
        try:
            init_res = sess.get(target_url, headers=headers, timeout=10)
            soup = BeautifulSoup(init_res.text, "html.parser")

            payload = {}
            for hidden in soup.find_all("input", type="hidden"):
                if hidden.get("name"):
                    payload[hidden["name"]] = hidden.get("value", "")

            roll_input, _ = _find_roll_input(soup)
            if roll_input and roll_input.get("name"):
                payload[roll_input["name"]] = str(roll_no)

            if session_val:
                select_tag, _ = _find_session_select(soup)
                if select_tag and select_tag.get("name"):
                    payload[select_tag["name"]] = session_val

            _find_submit_control(soup, payload)

            res = sess.post(target_url, data=payload, headers=headers, timeout=15)
            
            result_soup = BeautifulSoup(res.text, "html.parser")
            for tag in result_soup.find_all(['link', 'script', 'img'], href=True):
                if tag['href'].startswith('/'):
                    tag['href'] = base_origin + tag['href']
            for tag in result_soup.find_all(['img', 'script'], src=True):
                if tag['src'].startswith('/'):
                    tag['src'] = base_origin + tag['src']

            file_path = os.path.join(html_dir, f"{roll_no}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(result_soup))
        except Exception as e:
            logging.error(f"Failed HTML download for Roll No {roll_no}: {str(e)}")

    # مرحلہ 2: PDF میں تبدیل کرنا
    logging.info("Step 2: Converting HTML files to PDFs...")
    successful_pdfs = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page()

            for roll_no in roll_list:
                html_path = os.path.join(html_dir, f"{roll_no}.html")
                pdf_path = os.path.join(pdf_dir, f"{roll_no}.pdf")
                
                if os.path.exists(html_path):
                    try:
                        page.goto(f"file://{html_path}", wait_until="load", timeout=15000)
                        page.pdf(path=pdf_path, format="A4", print_background=True)
                        successful_pdfs.append(pdf_path)
                    except Exception as e:
                        logging.error(f"Failed PDF conversion for Roll No {roll_no}: {str(e)}")

            browser.close()

        # مرحلہ 3: اگر یوزر نے مرج کا کہا ہے تو تمام پی ڈی ایف کو ایک فائل میں جوڑ دیں
        if "Yes" in merge_choice and successful_pdfs:
            logging.info("Step 3: Merging all PDFs into a single master file...")
            merger = PdfMerger()
            for pdf in successful_pdfs:
                merger.append(pdf)
            
            merged_pdf_path = os.path.join(pdf_dir, "All_Results_Merged.pdf")
            merger.write(merged_pdf_path)
            merger.close()
            logging.info("Successfully created merged PDF: All_Results_Merged.pdf")

    except Exception as e:
        logging.error(f"Error during PDF processing: {str(e)}")

if __name__ == "__main__":
    download_and_convert_results()
