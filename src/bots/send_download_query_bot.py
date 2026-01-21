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
        self.last_alert = None

    def run(self):
        query_name = self.config['credentials'].get('query_name', 'DownloadJob')
        # Sanitize query_name if it is a list
        if isinstance(query_name, list):
            query_name = "_".join(str(x) for x in query_name)
            # Cap length if too long
            if len(query_name) > 50:
                query_name = "BatchDownload"
        
        log_path = os.path.join('logs', f"download_{query_name}.log")
        self.logger = setup_logger(self.__class__.__name__, log_file=log_path)
        
        # Store sanitized name for markers
        self.sanitized_query_name = query_name

        self.logger.info(f"Starting SendDownloadQueryBot execution... (Log: {log_path})")
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

    def _handle_pagination(self, page, page_index):
        """Navigates to the specified results page with a hard refresh fallback."""
        if page_index == 1:
            return True
        
        self.logger.info(f"[PAGE] Attempting navigation to Page {page_index}...")
        
        # Try normal pagination logic first
        success = self._do_pagination_logic(page, page_index)
        
        if not success:
            self.logger.warning(f"[PAGE] Normal pagination failed for Page {page_index}. Attempting hard refresh...")
            # Perform a full reload of the results page to clear any corrupted viewstate/ajax issues
            from automation.navigation import navigate_to_download_and_view_results
            if navigate_to_download_and_view_results(page, self.logger):
                self.logger.info(f"[PAGE] Hard refresh successful. Retrying navigation to Page {page_index} from Page 1...")
                # Try logic again from a fresh Page 1 state
                success = self._do_pagination_logic(page, page_index)
        
        return success

    def _do_pagination_logic(self, page, page_index):
        """Internal logic for navigating the pager grid."""
        try:
            grid_id = "MainContent_QueryViewControl1_grdvQueryList"
            # Use a loop to handle cases where the page might be multiple '...' sets away
            max_attempts = 15
            for attempt in range(max_attempts):
                page.wait_for_timeout(1000) # Small extra wait for stability
                
                # Check current visible pages
                pager_elements_info = page.evaluate(f"""
                    () => {{
                        let row = document.querySelector('tr.grid-footer');
                        if (!row) {{
                           const rows = Array.from(document.querySelectorAll('#{grid_id} tr'));
                           row = rows.find(r => {{
                               const links = r.querySelectorAll('a');
                               return links.length >= 2 && (r.innerText.includes('...') || 
                                      Array.from(links).some(a => !isNaN(a.innerText.trim()) && a.innerText.trim() !== ''));
                           }});
                        }}
                        if (!row) return {{ pages: [], has_ellipsis: false }};
                        const links = Array.from(row.querySelectorAll('td span, td a'));
                        return {{
                            pages: links.map(l => l.innerText.trim()).filter(t => !isNaN(t) && t !== ''),
                            has_ellipsis: Array.from(row.querySelectorAll('a')).some(a => a.innerText.includes('...'))
                        }};
                    }}
                """)
                
                visible_pages = [int(p) for p in pager_elements_info.get('pages', [])]
                has_ellipsis = pager_elements_info.get('has_ellipsis', False)
                
                if not visible_pages:
                    self.logger.info(f"[DEBUG] No visible pages found on attempt {attempt+1}. Waiting...")
                    page.wait_for_timeout(2000)
                    continue

                if page_index in visible_pages:
                    self.logger.info(f"[PAGE] Target Page {page_index} visible. Clicking...")
                    page.evaluate(f"""
                        () => {{
                            const grid = document.getElementById('{grid_id}');
                            const links = Array.from(grid.querySelectorAll('a'));
                            const link = links.find(a => a.innerText.trim() === '{page_index}');
                            if (link) link.click();
                        }}
                    """)
                    page.wait_for_load_state('networkidle')
                    page.wait_for_timeout(2000)
                    return True
                
                # If target is not in visible pages, use ellipsis if available
                if has_ellipsis:
                    highest_visible = max(visible_pages)
                    
                    if page_index > highest_visible:
                        idx = -1 # Last ellipsis
                        direction = "next"
                    else:
                        idx = 0 # First ellipsis
                        direction = "previous"

                    self.logger.info(f"[PAGE] Page {page_index} not visible in {visible_pages}. Clicking {direction} '...' to load more pages.")
                    page.evaluate(f"""
                        (index) => {{
                            const row = document.querySelector('tr.grid-footer');
                            const ellipses = Array.from(row.querySelectorAll('a')).filter(a => a.innerText.includes('...'));
                            if (ellipses.length > 0) {{
                                const target = index === -1 ? ellipses[ellipses.length - 1] : ellipses[0];
                                target.click();
                            }}
                        }}
                    """, idx)
                    page.wait_for_load_state('networkidle')
                    page.wait_for_timeout(3000)
                else:
                    # If no ellipsis and our page is not here, wait a few times then break
                    if attempt > 5:
                        break
                    page.wait_for_timeout(2000)
            
            return False
        except Exception as e:
            self.logger.error(f"[ERROR] Pagination logic error: {e}")
            return False

    def _get_targets_on_page(self, page):
        """Scans the current page and returns a list of target queries."""
        ensure_popup_closed(page, self.logger)
        grid_selector = '#MainContent_QueryViewControl1_grdvQueryList'
        row_locator = page.locator(f'{grid_selector} tr[style*="background-color:White"]')
        
        row_count = row_locator.count()
        targets = []
        for i in range(row_count):
            row = row_locator.nth(i)
            cells = row.locator('td')
            q_id = cells.nth(0).inner_text().strip()
            q_name = cells.nth(1).inner_text().strip()
            targets.append({"id": q_id, "name": q_name})
        return targets

    def _handle_download_modal(self, page, target_id):
        """Handles the multi-step download modal interaction."""
        select_all_btn_selector = 'input[value=">>"], input[id*="btnAll"]'
        confirm_dl_selector = 'input[value="Download"], input[value="OK"]'
        
        # Remove Qualtrics if present
        try:
            page.evaluate("document.querySelectorAll('div[class*=\"QSI\"], div[id*=\"QSI\"]').forEach(el => el.remove());")
        except: pass

        for frame in page.frames:
            try:
                btn_all = frame.locator(select_all_btn_selector).first
                if btn_all.is_visible():
                    self.logger.info("   [MODAL] Modal found. Clicking 'Select All'...")
                    ensure_popup_closed(page, self.logger)
                    btn_all.click()
                    page.wait_for_timeout(2000)
                    
                    # Check for immediate success alert after Select All
                    if self.last_alert and any(msg in self.last_alert for msg in ["submitted successfully", "request status"]):
                         self.logger.info(f"   [SUCCESS] Job submitted successfully for ID {target_id}.")
                         return True
                    
                    btn_final = frame.locator(confirm_dl_selector).first
                    if btn_final.is_visible():
                        ensure_popup_closed(page, self.logger)
                        btn_final.click()
                        
                        # Monitor for success alert
                        dl_start = time.time()
                        while time.time() - dl_start < 5:
                            ensure_popup_closed(page, self.logger)
                            if self.last_alert and any(msg in self.last_alert for msg in ["submitted successfully", "request status"]):
                                self.logger.info(f"   [SUCCESS] Job submitted successfully for ID {target_id}.")
                                return True
                            page.wait_for_timeout(200)
                        return True # Assume triggered if no error
            except Exception:
                continue
        return False

    def _process_target(self, page, target):
        """Encapsulates the lifecycle of processing a single download target."""
        self.logger.info(f"[TARGET] Processing Target: ID {target['id']} ({target['name']})")
        self.last_alert = None
        
        ensure_popup_closed(page, self.logger)
        # Scope to the specific grid to avoid selecting wrapper rows in nested tables
        grid_selector = '#MainContent_QueryViewControl1_grdvQueryList'
        target_row = page.locator(f'{grid_selector} tr').filter(has_text=target['id']).first
        
        download_icon = target_row.locator('input[src*="Download"]')
        
        try:
            download_icon.wait_for(state="visible", timeout=5000)
        except Exception:
            self.logger.warning(f"   [WARNING] Download icon not found for ID {target['id']} (waited 5s)")
            self._record_success(self.sanitized_query_name, target['id'], status="Download Icon Missing")
            return True

        download_icon.click(force=True)
        self.logger.info("   [DOWNLOAD] Download icon clicked. Monitoring for alerts/modal...")
        
        # Wait and check for immediate alerts (e.g. "Data not available")
        start_wait = time.time()
        while time.time() - start_wait < 5:
            ensure_popup_closed(page, self.logger)
            if self.last_alert:
                if "Data is not available" in self.last_alert:
                    self.logger.warning(f"   [SKIP] Skipping ID {target['id']}: Data not available.")
                    self._record_success(self.sanitized_query_name, target['id'], status="Data Not Available")
                    return True
                if any(msg in self.last_alert for msg in ["submitted successfully", "request status"]):
                    self.logger.info(f"   [SUCCESS] Job submitted successfully for ID {target['id']}.")
                    self._record_success(self.sanitized_query_name, target['id'], status="Data Downloaded (Alert)")
                    return True
            page.wait_for_timeout(500)
        
        # Check for modal logic
        self.logger.info("   [CHECK] No immediate alert. checking for modal...")
        page.wait_for_timeout(1000)
        
        # Track initial file count in downloads to verify if a new file appears
        downloads_dir = os.path.join(os.getcwd(), 'downloads')
        initial_files = set(os.listdir(downloads_dir)) if os.path.exists(downloads_dir) else set()

        if self._handle_download_modal(page, target['id']):
             # Verification logic
             self._record_success(self.sanitized_query_name, target['id'], status="Data Downloaded (Modal)")
             return True
            
        self.logger.warning(f"   [FAILED] Could not complete download sequence for ID {target['id']}")
        self._record_failure(self.sanitized_query_name, target['id'])
        return False

    def _record_success(self, query_name, target_id, status="Success"):
        """Writes the target ID to the success marker file with status."""
        try:
            output_dir = os.path.join(os.getcwd(), 'output', 'dwnldExecute')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{query_name}_downloads")
            with open(output_file, 'a') as f:
                f.write(f"{target_id} - {status}\n")
            self.logger.info(f"   [MARKER] Marked {target_id} as complete in {output_file}")
        except Exception as e:
            self.logger.error(f"   [MARKER] Failed to write success marker: {e}")

    def _record_failure(self, query_name, target_id):
        """Writes the target ID to the failure marker file."""
        try:
            output_dir = os.path.join(os.getcwd(), 'output', 'undone_tasks')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{query_name}_failed_downloads.txt")
            with open(output_file, 'a') as f:
                f.write(f"{target_id}\n")
            self.logger.info(f"   [MARKER] Marked {target_id} as failed in {output_file}")
        except Exception as e:
            self.logger.error(f"   [MARKER] Failed to write failure marker: {e}")

    def process_downloads(self, page):
        """Coorders the scanning and downloading of completed queries."""
        self.logger.info("[SCAN] Scanning for completed queries to download...")
        os.makedirs(os.path.join(os.getcwd(), 'downloads'), exist_ok=True)
        
        # Setup Alert Handler
        def handle_dialog(dialog):
            self.logger.info(f"[ALERT] Browser Alert Detected: '{dialog.message}' -> Clicking OK/Accept")
            self.last_alert = dialog.message
            dialog.accept()
        page.on("dialog", handle_dialog)

        if not navigate_to_download_and_view_results(page, self.logger):
            self.logger.error("[ERROR] Failed to navigate to results page.")
            return

        current_page_index = 1
        while True:
            self.logger.info(f"\n{'='*40}")
            self.logger.info(f"[PAGE] Processing Results Page {current_page_index}")
            self.logger.info(f"{'='*40}")
            
            if not self._handle_pagination(page, current_page_index):
                break

            targets = self._get_targets_on_page(page)
            if not targets:
                self.logger.info(f"[INFO] No data rows found on Page {current_page_index}.")
                break

            for target in targets:
                self._process_target(page, target)
            
            current_page_index += 1