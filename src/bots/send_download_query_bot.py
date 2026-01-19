import time
import sys
import os

# Add src to python path for imports to work if running directly
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.logger import setup_logger
from automation.browser import BrowserManager
from automation.login import login
from automation.navigation import setup_auto_close_popup, navigate_to_download_and_view_results, ensure_popup_closed

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

            # 3. Process Downloads
            self.process_downloads(page)
            
            # Keep browser open if not headless
            if not self.config.get('headless', False):
                self.logger.info("Keeping browser open for 10 seconds...")
                page.wait_for_timeout(10000)

        except Exception as e:
            self.logger.exception(f"An error occurred during execution: {e}")
        finally:
            self.browser_manager.stop()

    def process_downloads(self, page):
        """Scans the results table and clicks the Download2_New image icon."""
        self.logger.info("📡 Scanning for completed queries to download...")
        
        download_dir = os.path.join(os.getcwd(), 'downloads')
        os.makedirs(download_dir, exist_ok=True)
        
        # Setup Alert Handler (Auto-Accept)
        def handle_dialog(dialog):
            self.logger.info(f"🚨 Browser Alert Detected: '{dialog.message}' -> Clicking OK/Accept")
            self.last_alert = dialog.message
            dialog.accept()
        page.on("dialog", handle_dialog)

        target_query_name = self.config['credentials'].get('query_name', 'Auto2007')
        processed_ids = set()
        current_page_index = 1
        
        while True:
            self.logger.info(f"\n{'='*40}")
            self.logger.info(f"📄 Processing Results Page {current_page_index}")
            self.logger.info(f"{'='*40}")
            
            # Ensure we are on the results page
            if not navigate_to_download_and_view_results(page, self.logger):
                self.logger.error("❌ Failed to navigate/reset to results page.")
                break

            # 1. Handle Pagination Navigation
            if current_page_index > 1:
                try:
                    ensure_popup_closed(page, self.logger) # Check before pagination
                    footer_links = page.locator('tr.grid-footer a')
                    target_page_link = footer_links.get_by_text(str(current_page_index), exact=True)
                    
                    if target_page_link.is_visible():
                        self.logger.info(f"➡️ Navigating to Page {current_page_index}...")
                        target_page_link.click()
                        page.wait_for_load_state('networkidle')
                        page.wait_for_timeout(2000) 
                    else:
                        # Fallback: Check for '...' to reveal next set of pages
                        ellipsis_link = footer_links.get_by_text("...", exact=True).last
                        if ellipsis_link.is_visible():
                             self.logger.info(f"🔄 Page {current_page_index} not visible. Clicking '...' to load more pages.")
                             ellipsis_link.click()
                             page.wait_for_load_state('networkidle')
                             page.wait_for_timeout(2000)
                             
                             # Re-check for target link after '...' click
                             if target_page_link.is_visible():
                                 target_page_link.click()
                                 page.wait_for_load_state('networkidle')
                                 page.wait_for_timeout(2000)
                        else:
                            self.logger.info(f"⏹️ Page {current_page_index} not found and no '...' link. Stopping pagination.")
                            break
                except Exception as e:
                    self.logger.error(f"❌ Pagination error: {e}")
                    break

            # 2. Identify target rows on the current page
            ensure_popup_closed(page, self.logger) # Check before scanning rows
            grid_selector = '#MainContent_QueryViewControl1_grdvQueryList'
            row_locator = page.locator(f'{grid_selector} tr[style*="background-color:White"]')
            
            row_count = row_locator.count()
            if row_count == 0:
                self.logger.info("⚠️ No data rows found on this page.")
                break

            targets_on_page = []
            for i in range(row_count):
                row = row_locator.nth(i)
                cells = row.locator('td')
                
                q_id = cells.nth(0).inner_text().strip()
                q_name = cells.nth(1).inner_text().strip()
                q_status = cells.nth(7).locator('input').get_attribute("title") or ""
                targets_on_page.append({"id": q_id, "name": q_name})

            if not targets_on_page:
                self.logger.info(f"ℹ️ No pending targets found on Page {current_page_index}.")
                next_exists = footer_links.get_by_text(str(current_page_index + 1), exact=True).is_visible()
                if next_exists:
                    current_page_index += 1
                    continue
                break

            # 3. Execute Downloads
            for target in targets_on_page:
                self.logger.info(f"🔹 Processing Target: ID {target['id']} ({target['name']})")
                
                # Reset Alert State
                self.last_alert = None
                
                ensure_popup_closed(page, self.logger) # Check before download interaction
                target_row = page.locator(f"//tr[td[1][normalize-space()='{target['id']}']]").first
                download_icon = target_row.locator('input[src*="Download2_New.gif"]')
                
                if download_icon.is_visible():
                    download_icon.click(force=True)
                    self.logger.info("   🖱️ Download icon clicked. Monitoring for alerts/modal...")
                    
                    # Wait loop that checks for alerts or modal
                    start_time = time.time()
                    while time.time() - start_time < 5: 
                        # Check for blocking popup during wait
                        ensure_popup_closed(page, self.logger)
                        
                        if self.last_alert:
                            if "Data is not available" in self.last_alert:
                                self.logger.warning(f"   ⚠️ Skipping ID {target['id']}: Data not available.")
                                break
                            if "submitted successfully" in self.last_alert or "check the download request status" in self.last_alert:
                                self.logger.info(f"   ✅ Job submitted successfully for ID {target['id']}.")
                                processed_ids.add(target['id'])
                                break
                        page.wait_for_timeout(500)
                    
                    if self.last_alert:
                        continue

                    # If no alert, assume modal logic
                    self.logger.info("   👀 No immediate alert. checking for modal...")
                    page.wait_for_timeout(2000) 

                    # 4. Handle Modal
                    select_all_btn_selector = 'input[value=">>"], input[id*="btnAll"]'
                    confirm_dl_selector = 'input[value="Download"], input[value="OK"]'
                    
                    download_triggered = False
                    
                    # Remove Qualtrics
                    try:
                        page.evaluate("document.querySelectorAll('div[class*=\"QSI\"], div[id*=\"QSI\"]').forEach(el => el.remove());")
                    except: pass

                    for frame in page.frames:
                        try:
                            if not frame.name: pass 
                        except: continue

                        try:
                            btn_all = frame.locator(select_all_btn_selector).first
                            if btn_all.is_visible():
                                self.logger.info("   📥 Modal found. Clicking 'Select All'...")
                                ensure_popup_closed(page, self.logger) # Check before clicking Select All
                                btn_all.click()
                                page.wait_for_timeout(2000)
                                # Check alert again after click
                                if self.last_alert and ("submitted successfully" in self.last_alert or "check the download request status" in self.last_alert):
                                     self.logger.info(f"   ✅ Job submitted successfully for ID {target['id']} (after Select All).")
                                     processed_ids.add(target['id'])
                                     download_triggered = True
                                     break
                                
                                btn_final = frame.locator(confirm_dl_selector).first
                                if btn_final.is_visible():
                                    try:
                                        ensure_popup_closed(page, self.logger) # Check before Final Click
                                        btn_final.click()
                                        
                                        # Monitor for 5s for success alert or file
                                        dl_start = time.time()
                                        got_file = False
                                        while time.time() - dl_start < 5:
                                            # Check for popup during final wait
                                            ensure_popup_closed(page, self.logger)
                                            if self.last_alert and ("submitted successfully" in self.last_alert or "check the download request status" in self.last_alert):
                                                self.logger.info(f"   ✅ Job submitted successfully for ID {target['id']} (after Final Click).")
                                                processed_ids.add(target['id'])
                                                download_triggered = True
                                                got_file = True 
                                                break
                                            page.wait_for_timeout(200)
                                        
                                        if got_file: break
                                        
                                        download_triggered = True
                                        break
                                    except Exception as dl_err:
                                        self.logger.error(f"   ❌ Error during final download click: {dl_err}")
                        except Exception:
                            continue
                    
                    if not download_triggered:
                        self.logger.warning(f"   ⚠️ Could not complete modal sequence for {target['id']}")
            
            current_page_index += 1

                # Optional: Re-navigate or refresh if the site breaks after a download
                # navigate_to_download_and_view_results(page, self.logger)

            current_page_index += 1