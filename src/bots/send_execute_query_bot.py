
import json
import time
import sys
import os

# Add src to python path for imports to work if running directly
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.logger import setup_logger
from automation.browser import BrowserManager
from automation.login import login
from automation.navigation import (
    navigate_to_trade_data, 
    select_existing_query, 
    click_final_submit, 
    setup_auto_close_popup 
)
from automation.reporter import handle_reporter_modification

class SendQueryBot:
    def __init__(self, config):
        self.config = config
        self.logger = setup_logger(self.__class__.__name__)
        self.browser_manager = BrowserManager(headless=self.config.get('headless', False))
        self.start_time = None
        self.processing_times = []
        self.count = 3

    def save_undone_countries(self, query_name, undone_countries):
        """Saves each undone country as an individual JSON file in a folder."""
        try:
            folder_name = os.path.join('output', 'undone_tasks')
            if not os.path.exists(folder_name):
                os.makedirs(folder_name)
                self.logger.info(f"Created folder: {folder_name}")
            
            for iso3, country_name in undone_countries.items():
                filename = os.path.join(folder_name, f"{query_name}_{iso3}.json")
                data = {
                    "query_name": query_name,
                    "iso3": iso3,
                    "country_name": country_name,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=4)
            
            self.logger.info(f"Saved {len(undone_countries)} individual undone task files to {folder_name}")
        except Exception as e:
            self.logger.error(f"Failed to save granular undone countries: {e}")

    def log_country_progress(self, query_name, key, country_idx, total_count, duration):
        """Logs statistics and ETA after completing a country."""
        self.processing_times.append(duration)
        avg_time = sum(self.processing_times) / len(self.processing_times)
        remaining = total_count - country_idx
        
        eta_seconds = avg_time * remaining
        eta_fmt = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
        
        elapsed = time.time() - self.start_time
        elapsed_fmt = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s"

        self.logger.info(f"COMPLETED {key} for query {query_name}")
        self.logger.info(f"Duration : {duration:.2f}s | Avg: {avg_time:.2f}s")
        self.logger.info(f"ETA (Cur): {eta_fmt} | Total Elap: {elapsed_fmt}")
        self.logger.info(f"{'='*60}\n")

    def process_field_steps(self, page, query_name, key):
        """Executes the specific steps on the webpage for a single country."""
        # Step 1: Navigation
        s_nav = time.time()
        if not navigate_to_trade_data(page, self.logger):
            raise Exception("Navigation failed")
        self.logger.info(f"Step [Navigation] took: {time.time() - s_nav:.2f}s")
        
        # Step 2: Query Selection
        s_sel = time.time()
        if not select_existing_query(page, query_name, self.logger):
            raise Exception(f"Query selection failed for {query_name}")
        self.logger.info(f"Step [Query Selection] took: {time.time() - s_sel:.2f}s")
        
        # Step 3: Reporter Modification
        s_mod = time.time()
        if not handle_reporter_modification(page, query_name, self.logger, key):
            raise Exception("Reporter modification failed")
        self.logger.info(f"Step [Reporter Modification] took: {time.time() - s_mod:.2f}s")
        
        # Step 4: Final Submit
        s_sub = time.time()
        if not click_final_submit(page, self.logger):
            raise Exception("Final submit failed")
        self.logger.info(f"Step [Final Submit] took: {time.time() - s_sub:.2f}s")
        
        return True

    def process_country(self, page, query_name, key, country_name, current_idx, total_count):
        """Handles the lifecycle of processing a single country."""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"[{query_name}] - STARTING [{current_idx}/{total_count}]: {country_name} ({key})")
        self.logger.info(f"{'-'*60}")
        
        start_ts = time.time()
        try:
            if self.process_field_steps(page, query_name, key):
                self.log_country_progress(query_name, key, current_idx, total_count, time.time() - start_ts)
                
                # Success Marker: Write to output file
                try:
                    output_dir = os.path.join(os.getcwd(), 'output', 'done')
                    os.makedirs(output_dir, exist_ok=True)
                    output_file = os.path.join(output_dir, f"{query_name}")
                    with open(output_file, 'a') as f:
                        f.write(f"{key}\n")
                    self.logger.info(f"Marked {key} as successfully finished in {output_file}")
                except Exception as e:
                    self.logger.error(f"Failed to write success marker for {key}: {e}")

                return True
        except Exception as e:
            self.logger.error(f"Error processing {key}: {e}")
            return False

    def _run_iteration(self, query_name, undone_countries, iteration, total_count):
        """Starts a browser session and processes as many countries as possible."""
        self.logger.info(f"--- Query: {query_name} | Iteration {iteration} | Remaining: {len(undone_countries)} ---")
        page = self.browser_manager.start()
        
        try:
            setup_auto_close_popup(page, self.logger)
            creds = self.config['credentials']
            if not login(page, creds['email'], creds['password'], self.config['urls']['login'], self.logger):
                self.logger.error("Login failed. Retrying...")
                time.sleep(1)
                return undone_countries

            for key in list(undone_countries.keys()):
                country_name = undone_countries[key]
                current_idx = total_count - len(undone_countries) + 1
                
                if self.process_country(page, query_name, key, country_name, current_idx, total_count):
                    del undone_countries[key]
                    if not self.config.get('headless', False):
                        page.wait_for_timeout(1000)
                else:
                    # Break inner loop to refresh browser/session on failure
                    break
        
        except Exception as e:
            self.logger.exception(f"Unexpected error in {query_name} iteration {iteration}: {e}")
        finally:
            self.browser_manager.stop()
            
        return undone_countries

    def _check_progress(self, current_count, last_count, stagnant_iters):
        """Updates stagnation counters and returns (is_stagnant, new_last_count, new_stagnant_iters)."""
        if current_count == last_count:
            stagnant_iters += 1
        else:
            stagnant_iters = 0
            last_count = current_count
        
        is_stagnant = stagnant_iters >= 5
        return is_stagnant, last_count, stagnant_iters

    def process_query(self, query_name):
        """Processes all countries for a specific query name using multiple iterations if needed."""
        # Setup file logging for this query
        log_path = os.path.join('logs', f"{query_name}.log")
        self.logger = setup_logger(self.__class__.__name__, log_file=log_path)
        
        self.logger.info(f"\n{'#'*80}")
        self.logger.info(f"### PROCESSING QUERY: {query_name}")
        self.logger.info(f"### LOGGING TO: {log_path}")
        self.logger.info(f"{'#'*80}\n")

        undone_countries = self.config['iso3_to_country'].copy()
        total_count = len(undone_countries)
        last_undone_count = total_count
        stagnant_iters = 0
        iteration = 1
        self.processing_times = [] 
        index = 3
        while undone_countries:
            # if index%3 == 0:
            #     time.sleep(3)
            index += 1
            undone_countries = self._run_iteration(query_name, undone_countries, iteration, total_count)
            
            is_stagnant, last_undone_count, stagnant_iters = self._check_progress(
                len(undone_countries), last_undone_count, stagnant_iters
            )
            
            if is_stagnant:
                self.logger.error(f"Stagnation detected for query {query_name}. Aborting this query.")
                break
                
            iteration += 1

        if len(undone_countries) == 0:
            self.logger.info(f"All countries processed successfully for query {query_name}!")
        else:
            self.logger.warning(f"Query {query_name} finished with {len(undone_countries)} undone countries.")
            self.save_undone_countries(query_name, undone_countries)
        
        return len(undone_countries) == 0

    def run(self):
        self.start_time = time.time()
        self.logger.info("Starting SendQueryBot execution...")
        
        query_names = self.config['credentials'].get('query_name', [])
        if isinstance(query_names, str):
            query_names = [query_names]
        
        self.logger.info(f"Sequential run for queries: {query_names}")
        
        for query_name in query_names:
            if not self.process_query(query_name):
                self.logger.warning(f"Query {query_name} did not complete fully.")
        
        self.logger.info(f"Total time consumed: {time.time() - self.start_time:.2f} seconds.")