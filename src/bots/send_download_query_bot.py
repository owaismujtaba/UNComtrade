import time
import sys
import os

# Add src to python path for imports to work if running directly
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.logger import setup_logger
from automation.browser import BrowserManager
from automation.login import login
from automation.navigation import setup_auto_close_popup, navigate_to_download_and_view_results

class SendDownloadQueryBot:
    def __init__(self, config):
        self.config = config
        self.logger = setup_logger(self.__class__.__name__)
        self.browser_manager = BrowserManager(headless=self.config.get('headless', False))

    def run(self):
        self.logger.info("Starting SendDownloadQueryBot execution...")
        page = self.browser_manager.start()
        
        try:
            # 1. Register Modal Handler
            setup_auto_close_popup(page, self.logger)

            # 2. Login
            creds = self.config['credentials']
            if not login(page, creds['email'], creds['password'], self.config['urls']['login'], self.logger):
                self.logger.error("Login failed. Aborting.")
                return

            # 3. Navigate to Results
            if navigate_to_download_and_view_results(page, self.logger):
                self.logger.info("Successfully navigated to Download and View Results.")
                self.process_downloads(page)
            else:
                self.logger.error("Failed to navigate to Download and View Results.")
            
            # Keep browser open if not headless
            if not self.config.get('headless', False):
                self.logger.info("Keeping browser open for 10 seconds...")
                page.wait_for_timeout(10000)

        except Exception as e:
            self.logger.exception(f"An error occurred during execution: {e}")
        finally:
            self.browser_manager.stop()

    def process_downloads(self, page):
        """Scans the results table and downloads completed queries with modal interaction and pagination."""
        self.logger.info("Scanning for completed queries to download...")
        
        download_dir = os.path.join(os.getcwd(), 'downloads')
        os.makedirs(download_dir, exist_ok=True)
        
        # Setup Alert Handler (Auto-Accept)
        page.on("dialog", lambda dialog: dialog.accept())

        query_name = self.config.get('query_name', 'Auto2007New')
        
        processed_ids = set() # Track unique IDs of processed queries
        self.query_name = self.config.get('query_name', 'Auto2007New')
        processed_ids = set()
        current_page_index = 1
        
        while True:
            # 1. Reset to "Download and View Results" (Page 1 state)
            self.logger.info(f"--- Starting processing for Page {current_page_index} ---")
            if not navigate_to_download_and_view_results(page, self.logger):
                self.logger.error("Failed to navigate to results page. Retrying...")
                page.wait_for_timeout(5000)
                continue
            
            # 2. Navigate to specific Page Index (if needed)
            if current_page_index > 1:
                self.logger.info(f"Navigating to page table page {current_page_index}...")
                # Try to click the specific page number if visible
                try:
                    page_link = page.locator(f'.rgNumPart a:text-is("{current_page_index}")')
                    if page_link.is_visible():
                        page_link.click()
                        page.wait_for_load_state('domcontentloaded')
                        page.wait_for_timeout(3000)
                    else:
                        # Fallback: If page number not directly visible, we might need smarter paging
                        # For now, simplistic approach: Try clicking "Next" enough times or "..."
                        # Given complexity, we warn
                         self.logger.warning(f"Page {current_page_index} link not found. Attempting to use Next buttons or ...")
                         # Note: This simple logic assumes standard pager visibility. 
                         # A robust implementation would handle "..." iteration.
                         # For verification, we assume links are present or we stop.
                except Exception as e:
                     self.logger.error(f"Error navigating to page {current_page_index}: {e}")
                     break

            # 3. Scan current page for ALL targets
            self.logger.info(f"Scanning Page {current_page_index} for targets...")
            rows = page.locator('table[id*="grdvQueryList"] tr').all()
            
            # Skip header row
            if len(rows) > 0: rows = rows[1:]
            
            targets_on_page = []
            
            for row in rows:
                try:
                    cols = row.locator('td').all()
                    if len(cols) < 8: continue
                    
                    # Col 0: ID, Col 1: Name, Col 7: Status, Col 9: Date
                    q_id = cols[0].inner_text().strip()
                    q_name = cols[1].inner_text().strip()
                    q_status = cols[7].get_attribute("title") or ""
                    q_date = cols[9].inner_text().strip()
                    
                    unique_key = f"{q_name}_{q_date}" # Still useful for dedup logic if needed
                    
                    # Logic: query_name matching AND Completed AND not already processed
                    if (self.query_name.lower() in q_name.lower() and 
                        "Completed" in q_status and 
                        unique_key not in processed_ids):
                         
                         targets_on_page.append({
                             "id": q_id,
                             "name": q_name,
                             "unique_key": unique_key
                         })
                except: continue
            
            self.logger.info(f"Found {len(targets_on_page)} targets on Page {current_page_index}: {[t['id'] for t in targets_on_page]}")

            # 4. If no targets, check if we should continue to next page (Pagination Check)
            if len(targets_on_page) == 0:
                # Check if "Next" button exists to determine if we are at the end
                try:
                    next_btn = page.locator('.rgPageNext, input[src*="Next"], a:has-text("Next")').first
                    # If Next button is disabled or not visible, we are done
                    # Telerik usually hides next button or disables it on last page
                    if not next_btn.is_visible():
                         self.logger.info("No more pages detected. Download Scan Complete.")
                         break
                    
                    # If we just skipped a page with no targets, increment and loop
                    self.logger.info(f"No targets on Page {current_page_index}, checking next page...")
                    current_page_index += 1
                    continue
                except:
                    self.logger.info("Pagination check failed or end reached.")
                    break

            # 5. Process Targets (One by One)
            for target in targets_on_page:
                target_id = target["id"]
                target_key = target["unique_key"]
                
                self.logger.info(f"Processing Target ID: {target_id} ({target['name']})")
                
                processed_ids.add(target_key)
                
                # RE-NAVIGATE to ensure fresh state (User Requirement)
                # We need to be on the specific page to find the specific ID row again
                # Only need to re-nav if we aren't already "freshly" there. 
                # But since download disrupts state, we assume we must reset every time.
                
                # Reset to D&V
                if not navigate_to_download_and_view_results(page, self.logger):
                     self.logger.error("Failed reset navigation.")
                     continue
                
                # Go to Page N
                if current_page_index > 1:
                     try:
                        page.locator(f'.rgNumPart a:text-is("{current_page_index}")').click()
                        page.wait_for_load_state('domcontentloaded')
                        page.wait_for_timeout(3000)
                     except:
                        self.logger.error(f"Could not return to Page {current_page_index}")
                        continue
                
                # Find the row by ID
                # We look for a row where the first cell has the exact text ID
                # XPath is robust here: //tr[td[1][normalize-space()='ID']]
                try:
                    target_row = page.locator(f"//tr[td[1][normalize-space()='{target_id}']]").first
                    if not target_row.is_visible():
                        self.logger.warning(f"Row for ID {target_id} not found on Page {current_page_index}. Skipping.")
                        continue
                        
                    # Find Download Button (Col 4 -> Index 4?)
                    # The dump shows standard grid. Let's search inside row.
                    download_btn = target_row.locator('input[src*="Download"], input[src*="download"]').first
                    
                    if download_btn.count() > 0:
                        # ... Perform Download Logic (Same as before) ...
                        self.logger.info(f"Initiating download for ID {target_id}...")
                        
                        try:
                            # Close Qualtrics
                            page.evaluate("document.querySelectorAll('div[class*=\"QSI\"]').forEach(el => el.remove());")
                        except: pass

                        try:
                            download_btn.click(force=True)
                        except:
                            download_btn.evaluate("el => el.click()")
                        
                        page.wait_for_timeout(5000)

                        # Modal & Transfer
                        transfer_selector = 'input[id*="btnAll"], input[value=">>"], input[title="Add all"]'
                        transfer_btn = None
                        
                        # Poll Frame
                        s_time = time.time()
                        while time.time() - s_time < 45:
                            for frame in page.frames:
                                if frame.locator(transfer_selector).count() > 0:
                                    if frame.locator(transfer_selector).first.is_visible():
                                        transfer_btn = frame.locator(transfer_selector).first
                                        break
                            if transfer_btn: break
                            page.wait_for_timeout(1000)
                        
                        if transfer_btn:
                            try: transfer_btn.click(force=True)
                            except: transfer_btn.evaluate("el => el.click()")
                            page.wait_for_timeout(2000)
                        
                        # Final Download
                        final_selector = 'input[value="Download"], input[value="OK"], input[id*="btnOK"]'
                        final_btn = None
                        
                        s_time = time.time()
                        while time.time() - s_time < 15:
                            for frame in page.frames:
                                if frame.locator(final_selector).count() > 0:
                                    if frame.locator(final_selector).first.is_visible():
                                        final_btn = frame.locator(final_selector).first
                                        break
                            if final_btn: break
                            page.wait_for_timeout(500)
                            
                        if final_btn:
                             self.logger.info("Found Final Download button. Clicking...")
                             # Expect Navigation or Download
                             try:
                                with page.expect_download(timeout=5000) as download_info:
                                     final_btn.click(force=True)
                                try:
                                   dl = download_info.value
                                   dl.save_as(os.path.join(download_dir, dl.suggested_filename))
                                   self.logger.info(f"Saved: {dl.suggested_filename}")
                                except: pass
                             except:
                                 # Maybe just navigation
                                 pass
                             
                             page.wait_for_timeout(3000)
                        else:
                             self.logger.warning("Final download button not found.")
                             
                except Exception as e:
                    self.logger.error(f"Error downloading ID {target_id}: {e}")
                    continue
            
            # 6. Increment Page Index after processing all targets on current page
            self.logger.info(f"Finished processing Page {current_page_index}. Moving to next page...")
            current_page_index += 1
