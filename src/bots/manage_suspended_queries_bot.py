import time
import sys
import os

# Add src to python path for imports to work if running directly
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.logger import setup_logger
from automation.browser import BrowserManager
from automation.login import login
from automation.navigation import setup_auto_close_popup, navigate_to_download_and_view_results, ensure_popup_closed

class ManageSuspendedQueriesBot:
    def __init__(self, config):
        self.config = config
        # Setup logging to logs/suspended
        log_dir = os.path.join(os.getcwd(), 'logs', 'suspended')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "suspended_queries.log")
        
        self.logger = setup_logger(self.__class__.__name__, log_file=log_file)
        self.browser_manager = BrowserManager(headless=self.config.get('headless', False))
        self.last_alert = None
        
        # Optimize: Pre-load processed IDs to avoid re-work
        self.processed_ids = self._load_processed_ids()
        self.logger.info(f"Loaded {len(self.processed_ids)} processed queries from cache.")


    def run(self):
        self.logger.info("Starting ManageSuspendedQueriesBot execution...")
        
        max_retries = 3
        attempt = 0
        
        while attempt < max_retries:
            attempt += 1
            self.logger.info(f"--- Execution Attempt {attempt}/{max_retries} ---")
            
            # Start fresh browser for each attempt
            try:
                page = self.browser_manager.start()
            except Exception as e:
                self.logger.error(f"Failed to start browser on attempt {attempt}: {e}")
                time.sleep(5)
                continue

            try:
                # 1. Register Modal Handler
                setup_auto_close_popup(page, self.logger)

                # 2. Login
                creds = self.config['credentials']
                if not login(page, creds['email'], creds['password'], self.config['urls']['login'], self.logger):
                    self.logger.error("Login failed. Aborting attempt.")
                    self.browser_manager.stop()
                    continue

                # 3. Process Suspended Queries
                self.process_suspended_queries(page)
                
                # Keep browser open if not headless (only on success)
                if not self.config.get('headless', False):
                    self.logger.info("Keeping browser open for 10 seconds...")
                    page.wait_for_timeout(10000)
                
                # If successful, break the retry loop
                self.logger.info("Execution completed successfully.")
                break

            except Exception as e:
                self.logger.exception(f"An error occurred during execution (Attempt {attempt}): {e}")
                self.logger.info("Restarting process to continue from where it left off...")
                # Stop browser to cleanup before retry
                self.browser_manager.stop()
                
                if attempt == max_retries:
                    self.logger.error("Max retries reached. Exiting.")
            finally:
                # Ensure browser is stopped at the very end of loop if not already stopped or if breaking
                # But careful not to double-close in the loop. 
                # BrowserManager.stop() handles multiple calls gracefully usually?
                # Let's clean up at end of run if we broke out, or in except block.
                # Actually, simply stopping it here is safest to ensure clean state for next iteration or exit.
                if attempt >= max_retries or 'page' not in locals() or page.is_closed():
                     pass
                else:
                     self.browser_manager.stop()
    
        self.browser_manager.stop()

    def _remove_overlays(self, frame):
        """
        Aggressively removes known overlays (like Qualtrics/QSI) from the frame DOM.
        """
        try:
            frame.evaluate("""() => {
                // Remove Qualtrics containers
                document.querySelectorAll('.QSIWebResponsive').forEach(e => e.remove());
                document.querySelectorAll('div[id^="ZN_"]').forEach(e => e.remove());
                document.querySelectorAll('.fb_reset').forEach(e => e.remove()); // Facebook pixels sometimes overlay
                // Remove any other fixed position overlays that might block clicks if needed
            }""")
            self.logger.info("   [FRAME] Aggressive overlay removal executed.")
        except Exception as e:
            self.logger.warning(f"   [WARNING] Overlay removal failed: {e}")

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
                        # Trying to go forward. Ensure we have a "Next" ellipsis.
                        # In .NET GridView, "Next" ellipsis is usually the last anchor.
                        # If the last visible page (highest_visible) is the last anchor, there's no Next.
                        
                        can_go_forward = page.evaluate(f"""
                            () => {{
                                const row = document.querySelector('tr.grid-footer');
                                if (!row) return false;
                                const links = Array.from(row.querySelectorAll('a'));
                                if (links.length === 0) return false;
                                const lastLink = links[links.length - 1];
                                return lastLink.innerText.includes('...');
                            }}
                        """)
                        
                        if not can_go_forward:
                            self.logger.info(f"[PAGE] Page {page_index} requested, but max visible is {highest_visible} and no '...' Next button found. End of list.")
                            return False

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
                    # If no ellipsis and our page is not here
                    if page_index > max(visible_pages):
                         self.logger.info(f"[PAGE] Page {page_index} not found and no ellipsis. End of list.")
                         return False

                    # If no ellipsis and our page is not here, wait a few times then break
                    if attempt > 5:
                        break
                    page.wait_for_timeout(2000)
            
            return False
        except Exception as e:
            self.logger.error(f"[ERROR] Pagination logic error: {e}")
            return False

    def _load_last_page(self):
        try:
            path = os.path.join(os.getcwd(), 'output', 'suspended', 'last_page.txt')
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return int(f.read().strip())
        except:
            pass
        return 1

    def _save_last_page(self, page_num):
        try:
            path = os.path.join(os.getcwd(), 'output', 'suspended', 'last_page.txt')
            with open(path, 'w') as f:
                f.write(str(page_num))
        except:
            pass

    def process_suspended_queries(self, page):
        """Scans for suspended queries and clicks 'Log'."""
        self.logger.info("[SCAN] Scanning for suspended queries...")
        
        if not navigate_to_download_and_view_results(page, self.logger):
            self.logger.error("[ERROR] Failed to navigate to results page.")
            return

        current_page_index = 1
        target_page = self._load_last_page()
        
        if target_page > 1:
             self.logger.info(f"[RESUME] Found last processed page: {target_page}. Jumping to it...")
             # Efficiently jump to target page
             while current_page_index < target_page:
                 self.logger.info(f"[RESUME] Fast-forwarding: Seeking Page {target_page} (Current View Highest: ?)")
                 # We call _handle_pagination with the TARGET page. 
                 # If target is not visible, it clicks '...' to load next chunk.
                 # If target IS visible, it clicks it and returns True.
                 
                 # Optimization: _handle_pagination might be slow if we call it for every single step if target is far.
                 # But it handles "..." clicks correctly.
                 if self._handle_pagination(page, target_page):
                     self.logger.info(f"[RESUME] Successfully jumped to Page {target_page}.")
                     current_page_index = target_page
                     break
                 
                 # If it returned False but we are not at target, it meant it clicked '...' 
                 # Wait, _handle_pagination returns True ONLY if it clicked the specific page link.
                 # It returns False if it clicked '...' (wait, let's check return values).
                 # Looking at code: 
                 # If clicks '...', it waits and returns... wait, the function ends. Default return is False?
                 # No, lines 212-223 execute click. Then it falls through to return False at line 235.
                 # So if it clicks '...', it returns False.
                 # So we just loop. But we need to update our notion of progress?
                 # Actually _handle_pagination handles the logic of "Target not visible -> Click ...".
                 # So calling it repeatedly with SAME target_page will eventually reach it.
                 pass
                 
                 # Safety check: If we are stuck (e.g. end of list reached but target not found)
                 # _handle_pagination logs "End of list" and returns False without clicking.
                 # We need to detect that loop state.
                 # Simplified: Just rely on _handle_pagination. If it can't find it, we eventually process whatever page we are on.
                 # But we need to break if it fails to progress.
                 # Let's verify _handle_pagination return behavior.
                 
        current_page_index = max(1, current_page_index) # Safety
        # If jump failed or target=1, we start at 1. But if jump succeeded, we are at target_page.
        
        # NOTE: logic above might fail if _handle_pagination returns False when clicking '...'.
        # Let's assume we are at target_page if the loop finishes success.
        # Actually, let's just update current_page_index to target_page IF we think we are there.
        # But safer to just rely on the loop below `while True`.
        # Better Strategy: Set `current_page_index = target_page` at START.
        # AND Inside loop, `_handle_pagination(page, current_page_index)` will automatically click '...' until it gets there.
        # YES! That is the beauty of `_handle_pagination`.
        # It takes `page_index`. If `page_index` (50) is not visible, it clicks `...` repeatedly.
        # So I just need to set `current_page_index = target_page`.
        
        if target_page > 1:
            self.logger.info(f"[RESUME] Resuming from Page {target_page}...")
            current_page_index = target_page

        while True:
            self.logger.info(f"\\n{'='*40}")
            self.logger.info(f"[PAGE] Processing Results Page {current_page_index}")
            self.logger.info(f"{'='*40}")
            
            # Save current page as checkpoint (at START of processing)
            self._save_last_page(current_page_index)
            
            if not self._handle_pagination(page, current_page_index):
                self.logger.info(f"Pagination failed for page {current_page_index} (or End of List). Stopping.")
                break
            
            ensure_popup_closed(page, self.logger)
            grid_selector = '#MainContent_QueryViewControl1_grdvQueryList'

            # Optimize: Fast Page Scan using JS
            # Grab all suspended IDs on this page in one go to check if we can skip the whole page.
            try:
                suspended_ids_on_page = page.evaluate("""(selector) => {
                    const rows = Array.from(document.querySelectorAll(selector + ' tr'));
                    const results = [];
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 2) continue;
                        
                        const idText = cells[0].innerText.trim();
                        const rowText = row.innerText;
                        
                        // Check for Suspended status via text or image or title
                        const hasSuspendedImg = row.querySelector('input[src*="Suspended"]') !== null;
                        const hasSuspendedTitle = row.querySelector('td[title*="Suspended"]') !== null;
                        
                        if (rowText.includes('Suspended') || hasSuspendedImg || hasSuspendedTitle) {
                            results.push(idText);
                        }
                    }
                    return results;
                }""", grid_selector)

                if suspended_ids_on_page:
                    # Check if ALL suspended IDs on this page are already processed
                    all_processed = True
                    for s_id in suspended_ids_on_page:
                        if s_id not in self.processed_ids:
                            all_processed = False
                            break
                    
                    if all_processed:
                        self.logger.info(f"[PAGE] All {len(suspended_ids_on_page)} suspended queries on Page {current_page_index} are already processed. Fast-forwarding...")
                        
                        # Manually advance pagination to skip the loop
                        # Note: We must ensure we don't break the outer loop logic or getting stuck
                        current_page_index += 1
                        continue
            except Exception as e:
                self.logger.warning(f"[WARNING] Fast page check failed: {e}. Falling back to row iteration.")
            
            # Find all rows with "Suspended" text
            # We iterate all rows to check status text
            rows = page.locator(f'{grid_selector} tr[style*="background-color:White"]')
            count = rows.count()
            
            if count == 0:
                self.logger.info(f"No data rows found on Page {current_page_index}.")
                # If page 1 has no rows, we finish. If page > 1, maybe wait or done?
                # Usually pagers disable if empty, but logic usually breaks on pagination step.
                # Assuming standard grid behavior.
                break

            found_suspended_on_page = False
            for i in range(count):
                row = rows.nth(i)
                text_content = row.inner_text()
                
                # Check for "Suspended" in text OR via specific image/title
                is_suspended = "Suspended" in text_content
                
                if not is_suspended:
                    if (row.locator('input[src*="Suspended"]').count() > 0 or 
                        row.locator('td[title*="Suspended"]').count() > 0):
                        is_suspended = True

                if is_suspended:
                    found_suspended_on_page = True
                    # Extract ID for logging
                    try:
                        q_id = row.locator('td').nth(0).inner_text().strip()
                        query_name = row.locator('td').nth(1).inner_text().strip()
                        
                        # Optimize: Skip if already processed
                        if q_id in self.processed_ids:
                            self.logger.info(f"[SKIP] Query {q_id} already processed. Skipping.")
                            continue

                        self.logger.info(f"[SUSPENDED] Found suspended query ID: {q_id} Name: {query_name}")
                        
                        log_btn = row.locator('input[src*="Log"], a:has-text("Log")').first
                        
                        if log_btn.is_visible():
                            self.logger.info(f"   [ACTION] Clicking Log button for {q_id}...")
                            
                            # Click Log button
                            log_btn.click()
                            
                            # Wait for modal iframe to appear and load
                            self.logger.info(f"   [WAIT] Waiting for modal to load for query {q_id}...")
                            try:
                                page.wait_for_selector('iframe[name="rdwndJobReport"]', timeout=10000)
                                page.wait_for_timeout(1000)  # Reduced from 2000ms - balance speed vs reliability
                            except:
                                self.logger.warning(f"   [WARNING] Modal did not appear for query {q_id}")
                            
                            content_found = False
                            target_frame = None
                            content = "" # Initialize content variable
                            
                            # Check specifically for the Job Report frame
                            job_frame = page.frame(name="rdwndJobReport")
                            if job_frame:
                                try:
                                    self.logger.info("   [FRAME] Found 'rdwndJobReport' frame. Waiting for load...")
                                    job_frame.wait_for_load_state('domcontentloaded', timeout=10000)
                                    
                                    # Aggressively remove overlays
                                    self._remove_overlays(job_frame)
                                    
                                    # Wait for content load
                                    try:
                                        job_frame.wait_for_selector('body', timeout=5000)
                                    except: pass

                                    # Initial content check
                                    f_content = job_frame.inner_text('body')
                                    
                                    # Handle "Feedback" modal if it still exists (fallback)
                                    if "We welcome your feedback" in f_content:
                                        self.logger.info("   [FRAME] Feedback modal text detected. Attempting legacy close...")
                                        try:
                                            # Try "No, thanks"
                                            no_thanks = job_frame.locator('text="No, thanks"').first
                                            if no_thanks.is_visible():
                                                no_thanks.click(force=True)
                                                job_frame.wait_for_timeout(1000)
                                            else:
                                                # Try removing via JS again
                                                self._remove_overlays(job_frame)
                                        except Exception as e:
                                            self.logger.warning(f"   [WARNING] Failed to close feedback modal: {e}")
                                            
                                            # Re-read content
                                            f_content = job_frame.inner_text('body')
                                    
                                    # Attempt to extract from textarea FIRST (if already present)
                                    extracted_text = ""
                                    try:
                                        self.logger.info("   [WAIT] Looking for textarea 'txtDesc'...")
                                        # Wait explicitly for the textarea to appear with longer timeout
                                        textarea_selector = 'textarea[name="txtDesc"], textarea[id*="txtDesc"], textarea[name="txtQueryDef"], textarea[id*="txtQueryDef"]'
                                        
                                        # Try with longer timeout for slower-loading content
                                        textarea_found = False
                                        try:
                                            job_frame.wait_for_selector(textarea_selector, timeout=10000)
                                            textarea_found = True
                                            self.logger.info("   [DEBUG] Textarea selector found")
                                        except Exception as wait_err:
                                            self.logger.warning(f"   [DEBUG] Textarea wait timeout: {wait_err}")
                                        
                                        textarea_loc = job_frame.locator(textarea_selector).first
                                        textarea_count = textarea_loc.count()
                                        self.logger.info(f"   [DEBUG] Textarea count: {textarea_count}")
                                        
                                        if textarea_count > 0:
                                            extracted_text = textarea_loc.input_value()
                                            self.logger.info(f"   [DATA] Found text content (len={len(extracted_text)})")
                                            if not extracted_text:
                                                self.logger.warning("   [WARNING] Textarea found but content is empty!")
                                        else:
                                            self.logger.warning("   [WARNING] No textarea elements found with selector")
                                            # Log available textareas for debugging
                                            all_textareas = job_frame.locator('textarea').count()
                                            self.logger.info(f"   [DEBUG] Total textarea elements in frame: {all_textareas}")
                                    except Exception as e:
                                        self.logger.warning(f"   [WARNING] Error finding textarea: {e}")

                                    # If no text found, try clicking "Query Definition" tab
                                    if not extracted_text or "Markets" not in extracted_text:
                                        try:
                                            # Ensure overlays are gone
                                            self._remove_overlays(job_frame) 
                                            
                                            # Wait for tab
                                            q_def_tab = job_frame.locator('span:has-text("Query Definition"), a:has-text("Query Definition"), li:has-text("Query Definition")').first
                                            try:
                                                q_def_tab.wait_for(state='attached', timeout=5000)
                                            except: pass

                                            if q_def_tab.count() > 0:
                                                self.logger.info("   [ACTION] Clicking 'Query Definition' tab...")
                                                # Use JS click
                                                q_def_tab.evaluate("el => el.click()")
                                                job_frame.wait_for_timeout(2000)
                                                
                                                # Retry textarea extraction
                                                try:
                                                    textarea_loc = job_frame.locator('textarea[name="txtDesc"], textarea[id*="txtDesc"], textarea[name="txtQueryDef"], textarea[id*="txtQueryDef"]').first
                                                    if textarea_loc.count() > 0:
                                                        extracted_text = textarea_loc.input_value()
                                                except: pass
                                            else:
                                                self.logger.warning("   [WARNING] Query Definition tab not found.")
                                        except Exception as e:
                                            self.logger.warning(f"   [WARNING] Error interacting with tab: {e}")
                                    
                                    if extracted_text:
                                        f_content += "\n" + extracted_text
                                        
                                    try:
                                        # Update content with latest body text too
                                        f_content += "\n" + job_frame.inner_text('body')
                                    except Exception as e:
                                        pass

                                    content = f_content
                                    if "Markets" in content: # Loose check first
                                        content_found = True
                                        target_frame = job_frame
                                except Exception as e:
                                    self.logger.warning(f"   [FRAME] Error reading job frame: {e}")

                            # Fallback: Check all frames if specific one failed or check body
                            if not content_found:
                                # Check main page
                                c = page.inner_text('body')
                                if "Markets (Reporting Countries or Regions):" in c:
                                    content = c
                                    content_found = True
                                else:
                                    for frame in page.frames:
                                        try:
                                            fc = frame.inner_text('body')
                                            if "Markets (" in fc: # Loose check
                                                content = fc
                                                content_found = True
                                                target_frame = frame
                                                break
                                        except: pass

                            if True: # Always proceed to save/close for debugging, even if specific text not found
                                if target_frame:
                                    self.logger.info(f"   [MODAL] Found content in frame: {target_frame.name or target_frame.url}")
                                else:
                                    self.logger.info("   [MODAL] Log modal detected (or fallback used).")
                                
                                # Extract info
                                import re
                                details = self._extract_details_from_text(content)
                                
                                if content_found:
                                    if details['markets'] != "Not Found":
                                        self.logger.info(f"   [DATA] Found Reporting Country: {details['markets']}")
                                    else:
                                        self.logger.warning(f"   [WARNING] 'Markets...' keyword found but regex failed. Content excerpt: {content[:200]}")
                                    self._save_suspended_details(q_id, query_name, details)
                                    self.logger.info(f"   [SAVED] Details saved.")
                                else:
                                    self.logger.warning(f"   [WARNING] 'Markets...' not found. Saving as 'Not Found'.")
                                    self._save_suspended_details(q_id, query_name, {"markets": "Not Found", "years": "Not Found", "trade_flows": "Not Found"})
                                    self.logger.info(f"   [SAVED] Details saved.")
                                
                                # Close the modal (Robustly)
                                try:
                                    closed = False
                                    # 1. Try standard "Close" button inside frame
                                    try:
                                        if target_frame:
                                            close_btn = target_frame.locator('input[value="Close"], button:has-text("Close")').first
                                            if close_btn.is_visible():
                                                close_btn.click(timeout=2000)
                                                closed = True
                                                page.wait_for_timeout(500)
                                    except: pass

                                    # 2. Try Telerik Window "X" button (on main page)
                                    if not closed:
                                        try:
                                            # The wrapper ID usually contains the frame ID logic
                                            wrapper_close = page.locator('.RadWindow .rwCloseButton').first
                                            if wrapper_close.isVisible():
                                                 wrapper_close.click(timeout=2000)
                                                 closed = True
                                                 page.wait_for_timeout(500)
                                        except: pass

                                    # 3. JS Force Close (The Nuclear Option)
                                    if not closed or page.locator('iframe[name="rdwndJobReport"]').is_visible():
                                        self.logger.info("   [CLOSE] Forcing modal close via JS...")
                                        page.evaluate("""
                                            () => {
                                                // Try Telerik API
                                                try {
                                                    var wnd = $find("ctl00_MainContent_QueryViewControl1_rdwndJobReport");
                                                    if(wnd) wnd.close();
                                                } catch(e) {}
                                                
                                                // Try DOM removal
                                                document.querySelectorAll('div[id*="rdwndJobReport"]').forEach(el => el.style.display = 'none');
                                                document.querySelectorAll('iframe[name="rdwndJobReport"]').forEach(el => el.remove());
                                                $('.RadWindow').hide(); // If jQuery present
                                            }
                                        """)
                                        page.wait_for_timeout(1000)

                                    # Verify it's gone - CRITICAL for data alignment
                                    modal_closed = False
                                    for attempt in range(5):
                                        try:
                                            if not page.locator('iframe[name="rdwndJobReport"]').is_visible():
                                                modal_closed = True
                                                break
                                            else:
                                                self.logger.warning(f"   [WARNING] Modal still visible on attempt {attempt+1}/5. Forcing removal...")
                                                page.evaluate("document.querySelectorAll('iframe[name=\"rdwndJobReport\"]').forEach(el => el.remove());")
                                                page.wait_for_timeout(500)
                                        except:
                                            modal_closed = True
                                            break
                                    
                                    if not modal_closed:
                                        self.logger.error("   [ERROR] Could not fully close modal! Risk of data misalignment!")
                                    
                                    # CRITICAL: Wait for DOM cleanup - reduced from 3s to 1.5s for speed
                                    page.wait_for_timeout(1500)

                                except Exception as e:
                                    self.logger.error(f"Error closing modal: {e}")
                            
                            ensure_popup_closed(page, self.logger) 
                            self.logger.info(f"   [DONE] Processed Log for {q_id}")
                        else:
                            self.logger.warning(f"   [WARNING] Log button not found for {q_id}")
                            
                    except Exception as e:
                        self.logger.error(f"Error processing row {i}: {e}")

            if not found_suspended_on_page:
                self.logger.info(f"No suspended queries found on Page {current_page_index}. Continuing to next page.")
            
            current_page_index += 1
            
    def _load_processed_ids(self):
        """Loads IDs from existing JSON/CSV to skip duplicates."""
        ids = set()
        output_dir = os.path.join(self.config.get('output_dir', 'output'), 'suspended')
        
        # Load from CSV (Preferred)
        csv_file = os.path.join(output_dir, 'suspended_queries.csv')
        if os.path.exists(csv_file):
            import csv
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Only skip if we actually found data previously
                        if 'query_id' in row:
                             # Check if we have valid data (not "Not Found")
                             if row.get('reporting_country') != "Not Found" and row.get('years') != "Not Found":
                                 ids.add(row['query_id'])

            except: pass
            
        # Fallback/Merge JSON
        json_file = os.path.join(output_dir, 'suspended_details.json')
        if os.path.exists(json_file):
            import json
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    for item in data:
                        if 'query_id' in item:
                            ids.add(item['query_id'])
            except: pass
        return ids

    def _save_suspended_details(self, question_id, query_name, details):
        """
        Saves extracted details to both JSON and CSV formats.
        """
        import json
        import csv
        
        # Add to local cache immediately
        self.processed_ids.add(question_id)
        
        output_dir = os.path.join(self.config.get('output_dir', 'output'), 'suspended')
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. Save to JSON (Legacy/Backup)
        # Optimized: Read only if needed, or maybe just skip expensive JSON read/write for every item if CSV is primary?
        # Let's keep it but maybe optimize? For now, standard logic is robust.
        json_file = os.path.join(output_dir, 'suspended_details.json')
        data = []
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
            except: pass
        
        record = {
            "query_id": question_id,
            "query_name": query_name, 
            "reporting_country": details.get('markets', 'Not Found'),
            "years": details.get('years', 'Not Found'),
            "trade_flows": details.get('trade_flows', 'Not Found'),
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Check if record already exists to avoid duplicates
        if not any(d.get('query_id') == question_id for d in data):
            data.append(record)
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=4)
        
        # 2. Save to CSV (Requested)
        csv_file = os.path.join(output_dir, 'suspended_queries.csv')
        fieldnames = ['query_id', 'query_name', 'reporting_country', 'years', 'trade_flows', 'date']
        
        file_exists = os.path.exists(csv_file)
        
        try:
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                
                # Filter record to match fieldnames
                csv_row = {k: record.get(k, '') for k in fieldnames}
                writer.writerow(csv_row)
            self.logger.info(f"   [SAVED] Appended to {csv_file}")
        except Exception as e:
            self.logger.error(f"   [ERROR] Failed to write to CSV: {e}")

    def _extract_details_from_text(self, text):
        """Extracts Market info from text blob."""
        details = {"markets": "Not Found", "years": "Not Found", "trade_flows": "Not Found"}
        import re
        
        # Simplify text: normalize newlines and remove phantom spaces
        text = text.replace('\xa0', ' ').replace('\r', '\n')
        
        # Extract Markets
        # Format provided by user:
        # Markets (Reporting Countries or Regions):
        # 	IRQ	368	Iraq
        #
        # Partners ...
        
        # Strategy: Find "Markets...:" then capture lines until double newline or "Partners"
        # We capture the content between "Markets ... :" and the next section header
        
        markets_match = re.search(r"Markets.*?[:](.+?)(?:Partners|Years|Trade Type|\Z)", text, re.IGNORECASE | re.DOTALL)
        if markets_match:
            raw_markets = markets_match.group(1).strip()
            # Clean up: lines often start with tabs/spaces. 
            # Example: "	IRQ	368	Iraq"
            # We want "IRQ 368 Iraq"
            clean_lines = [line.strip() for line in raw_markets.split('\n') if line.strip()]
            if clean_lines:
                details['markets'] = "; ".join(clean_lines)
        
        # Fallback: Look for "Reporting Country" if the above failed
        if details['markets'] == "Not Found":
             rep_match = re.search(r"Reporting Country[:\s]+(.+?)(?:Partner|Years|$)", text, re.IGNORECASE)
             if rep_match:
                 details['markets'] = rep_match.group(1).strip()

        return details

