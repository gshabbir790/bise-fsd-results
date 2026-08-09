import os
os.system("playwright install chromium")
import os
import streamlit as st
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

st.set_page_config(page_title="BISE Result Downloader", page_icon="🎓", layout="centered")

st.title("🎓 BISE Result Downloader")
st.write("براؤزر بیسڈ تیز ترین رزلٹ ڈاؤن لوڈنگ اور پی ڈی ایف مرجر ٹول")

# یوزر انٹرفیس (خوبصورت فارم)
target_url = st.text_input("Board Result URL", placeholder="https://www.bisefsd.edu.pk/InterResults.aspx")

session_val = st.selectbox(
    "Select Session / Exam",
    ["None", "Second Annual 2025", "Annual 2025", "Annual 2024", "Annual 2023"]
)

col1, col2 = st.columns(2)
with col1:
    start_roll = st.number_input("Start Roll Number", min_value=1, value=472014)
with col2:
    end_roll = st.number_input("End Roll Number", min_value=1, value=472020)

merge_choice = st.radio(
    "PDF Output Format",
    ["Yes (Merge into one file)", "No (Keep separate only)"]
)

if st.button("🚀 Start Downloading Results", type="primary"):
    if not target_url:
        st.error("براہ کرم رزلٹ کا URL درج کریں!")
    else:
        if session_val == 'None':
            session_val = ""

        roll_list = list(range(int(start_roll), int(end_roll) + 1))
        pdf_dir = "/tmp/bise_results"
        os.makedirs(pdf_dir, exist_ok=True)
        successful_pdfs = []

        progress_text = st.empty()
        progress_bar = st.progress(0)

        try:
            progress_text.text("براؤزر شروع ہو رہا ہے...")
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True, 
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                context = browser.new_context()
                page = context.new_page()

                # سپیڈ تیز کرنے کے لیے فالتو تصاویر بلاک کرنا
                page.route("**/*.{png,jpg,jpeg,svg,gif,woff,woff2}", lambda route: route.abort())

                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

                if session_val:
                    for select in page.query_selector_all("select"):
                        options = select.query_selector_all("option")
                        matched_val = None
                        for opt in options:
                            if session_val.lower() in opt.inner_text().strip().lower():
                                matched_val = opt.get_attribute("value")
                                break
                        if matched_val:
                            select.select_option(value=matched_val)
                            break

                total_rolls = len(roll_list)
                for idx, roll_no in enumerate(roll_list):
                    progress_text.text(f"ڈاؤن لوڈ ہو رہا ہے: رول نمبر {roll_no} ({idx+1}/{total_rolls})...")
                    progress_bar.progress((idx + 1) / total_rolls)

                    try:
                        try:
                            close_btn = page.query_selector(".modal .close, button.close, [data-dismiss='modal']")
                            if close_btn:
                                close_btn.click()
                        except:
                            pass

                        roll_input = (
                            page.query_selector("input[id*='roll']") or
                            page.query_selector("input[name*='roll']") or
                            page.query_selector("input[type='text']")
                        )

                        if roll_input is None:
                            continue

                        roll_input.fill("")
                        roll_input.fill(str(roll_no))

                        button_selectors = [
                            "input[type='submit']", "button[type='submit']",
                            "text=Search", "text=Get Result", "text=Submit", "text=View Result"
                        ]
                        
                        clicked = False
                        for selector in button_selectors:
                            loc = page.locator(selector)
                            if loc.count() > 0:
                                loc.first.click(force=True)
                                clicked = True
                                break

                        if not clicked:
                            page.evaluate("if(typeof __doPostBack == 'function') { __doPostBack(); }")

                        page.wait_for_load_state("domcontentloaded", timeout=10000)
                        
                        pdf_path = os.path.join(pdf_dir, f"{roll_no}.pdf")
                        page.pdf(path=pdf_path, format="A4", print_background=True)
                        successful_pdfs.append(pdf_path)

                        if page.url != target_url:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                            if session_val:
                                for select in page.query_selector_all("select"):
                                    options = select.query_selector_all("option")
                                    matched_val = None
                                    for opt in options:
                                        if session_val.lower() in opt.inner_text().strip().lower():
                                            matched_val = opt.get_attribute("value")
                                            break
                                    if matched_val:
                                        select.select_option(value=matched_val)
                                        break

                    except Exception as e:
                        continue

                browser.close()

            # مرج کرنے کا عمل
            if "Yes" in merge_choice and successful_pdfs:
                progress_text.text("تمام رزلٹس کو ایک فائل میں مرج کیا جا رہا ہے...")
                merger = PdfWriter()
                for pdf in successful_pdfs:
                    merger.append(pdf)
                
                merged_pdf_path = os.path.join(pdf_dir, "All_Results_Merged.pdf")
                merger.write(merged_pdf_path)
                merger.close()

                st.success("🎉 تمام رزلٹس کامیابی سے ڈاؤن لوڈ اور مرج ہو چکے ہیں!")
                
                with open(merged_pdf_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Merged PDF File",
                        data=f,
                        file_name="All_Results_Merged.pdf",
                        mime="application/pdf"
                    )
            else:
                st.success("🎉 رزلٹس کامیابی سے ڈاؤن لوڈ ہو گئے ہیں!")

        except Exception as e:
            st.error(f"کوئی خرابی پیش آئی: {str(e)}")
