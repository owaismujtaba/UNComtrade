import time
import sys
import os

# Add src to python path for imports to work if running directly
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.logger import setup_logger
from automation.browser import BrowserManager
from automation.login import login
from automation.navigation import setup_auto_close_popup, navigate_to_download_and_view_results, ensure_popup_closed

class DeleteQueriesBot:
    def __init__(self, config):
        self.config = config
        # Setup logging to logs/delete
        log_dir = os.path.join(os.getcwd(), 'logs', 'delete')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"delete_queries_{int(time.time())}.log")
        
        self.logger = setup_logger(self.__class__.__name__, log_file=log_file)
        self.browser_manager = BrowserManager(headless=self.config.get('headless', False))

    def run(self):
        self.logger.info("Starting DeleteQueriesBot execution...")
        page = self.browser_manager.start()
        
        try:
            # 1. Register Modal/Dialog Handler
            # checking for "Are you sure" or similar delete confirmations
            def handle_dialog(dialog):
                self.logger.info(f"[DIALOG] Handling dialog: '{dialog.message}' - Action: ACCEPT")
                dialog.accept()
            
            page.on("dialog", handle_dialog)
            setup_auto_close_popup(page, self.logger)

            # 2. Login
            creds = self.config['credentials']
            if not login(page, creds['email'], creds['password'], self.config['urls']['login'], self.logger):
                self.logger.error("Login failed. Aborting.")
                return

            # 3. Process Deletion
            self.process_deletion(page)
            
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
                        
                        # Stop at end of list check
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
                    if page_index > max(visible_pages):
                         self.logger.info(f"[PAGE] Page {page_index} not found and no ellipsis. End of list.")
                         return False

                    if attempt > 5:
                        break
                    page.wait_for_timeout(2000)
            
            return False
        except Exception as e:
            self.logger.error(f"[ERROR] Pagination logic error: {e}")
            return False

    def process_deletion(self, page):
        """Scans for queries and clicks 'Delete'."""
        self.logger.info("[SCAN] Scanning for queries to delete...")
        
        if not navigate_to_download_and_view_results(page, self.logger):
            self.logger.error("[ERROR] Failed to navigate to results page.")
            return

        # We don't increment page index in a simple loop because deleting items shifts the grid.
        # But for WITS, deleting usually refreshes the page or stays on the same page.
        # If we iterate pages (1, 2, 3), we might miss items if they shift up.
        # IMPROVED LOGIC: Stay on Page 1 until empty? Or iterate?
        # "finds the delete button... and clicks it".
        # If we delete, the page typically refreshes.
        # Safer strategy: Loop Page 1 repeatedly until no delete buttons are found?
        # But if there are multiple pages, we might need to paginate.
        # Let's assume standard iteration for now, but deleting might require re-scanning the current page.
        
        # Actually, iterating pages is safer if we delete *everything*.
        # But if we delete row 1, row 2 becomes row 1.
        # So we should probably keep scanning the current page until no delete buttons are found, then move to next?
        # Or even simpler: Find all delete buttons, click them one by one (re-finding each time to avoid stale elements).
        
        current_page_index = 1
        while True:
            self.logger.info(f"\n{'='*40}")
            self.logger.info(f"[PAGE] Processing Results Page {current_page_index}")
            self.logger.info(f"{'='*40}")
            
            if not self._handle_pagination(page, current_page_index):
                self.logger.info(f"Pagination failed or end of list at page {current_page_index}. Stopping.")
                break
            
            ensure_popup_closed(page, self.logger)
            grid_selector = '#MainContent_QueryViewControl1_grdvQueryList'
            
            # Repetitively delete items ~on this page~ until none are left or we decide to move on.
            # If the user wants to delete ALL queries, we should stay on the page until it's empty.
            
            page_empty = False
            while True:
                # Find all delete buttons (Case sensitive match for DELETE_New.gif)
                delete_buttons = page.locator(f'{grid_selector} input[src*="DELETE"]')
                count = delete_buttons.count()
                
                if count == 0:
                    self.logger.info(f"No delete buttons found on Page {current_page_index}.")
                    # If no delete buttons, we are done with this page.
                    page_empty = True
                    break
                
                self.logger.info(f"[DELETE] Found {count} items to delete on this page.")
                
                # Click the first one
                # We expect a page reload or grid update after deletion usually.
                try:
                    btn = delete_buttons.first
                    # Get ID for logging if possible (parent row -> td)
                    row = btn.locator('xpath=./../..') # input -> td -> tr
                    q_id = "Unknown"
                    try:
                        q_id = row.locator('td').nth(0).inner_text().strip()
                    except: pass
                    
                    self.logger.info(f"   [ACTION] Deleting query ID: {q_id}...")
                    btn.click() # This triggers the dialog, handled by page.on('dialog')
                    
                    # Wait for update
                    page.wait_for_timeout(2000)
                    page.wait_for_load_state('domcontentloaded')
                    ensure_popup_closed(page, self.logger)
                    
                    self.logger.info(f"   [DONE] Deleted {q_id}.")
                    
                    # After deletion, the grid updates. We loop back to `while True` to find the next first button.
                    # This avoids stale element references.
                    
                except Exception as e:
                    self.logger.error(f"Error during deletion: {e}")
                    # If we error, maybe break to next page to avoid infinite error loop
                    break
            
            # If we cleared the page, and there are still pages, WITS might auto-repaginated.
            # If we were on Page 1 and cleared it, Page 2 becomes Page 1.
            # So if we successfully deleted items, we should probably stay on "current_page_index" (which might still be 1).
            # But if we found *nothing* to delete, we move to next page.
            
            # However, if we move to Next Page, and previous page was cleared, does Page 2 exist?
            # Complexity: safely simple strategy -> Just iterate. If we delete things, the list shrinks.
            # If we delete everything on Page 1, the list pulls from Page 2.
            # So effectively, if we want to delete ALL, we just stay on Page 1 until the grid is empty.
            
            # But the user might have mixed items (some deleteable, some not).
            # So: Delete all visible on current page. Then try to go to Next Page? 
            # If we delete items, usually the grid refills from subsequent pages.
            # So the strategy "Delete all on current page" effectively processes the queue.
            # If we empty Page 1, we are still on Page 1 (refilled).
            # So we only increment page index if we found *nothing* to delete on the current page cycle.
            
            if not page_empty:
                # We deleted at least one thing. The page might have refilled.
                # Let's NOT increment page_index. Let's re-scan Page 1 (or current index).
                # But to avoid infinite loop if there's a stubborn "undeletable" item,
                # we rely on the `count == 0` check above.
                # Wait, if `delete_buttons.count() > 0` and we delete one, we loop back.
                # We only exit the inner loop when `count == 0` (no delete buttons left).
                # So if we exit the inner loop, it means "No delete buttons on this page".
                pass
            
            # If no delete buttons left on this page, move to next.
            current_page_index += 1
