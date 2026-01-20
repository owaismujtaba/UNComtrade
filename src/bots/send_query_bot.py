
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

    def save_undone_countries(self, undone_countries):
        """Saves the list of undone countries to a JSON file."""
        try:
            filename = 'undone_countries.json'
            with open(filename, 'w') as f:
                json.dump(undone_countries, f, indent=4)
            self.logger.info(f"Saved {len(undone_countries)} undone countries to {filename}")
        except Exception as e:
            self.logger.error(f"Failed to save undone countries: {e}")

    def run(self):
        start_time = time.time()
        self.logger.info("Starting SendQueryBot execution with Auto-Modal Handling...")
        
        undone_countries = self.config['iso3_to_country'].copy()
        total_countries_count = len(undone_countries)
        last_undone_count = len(undone_countries)
        processing_times = []
        stagnant_iterations = 0
        iteration = 1
        
        while len(undone_countries) > 0:
            self.logger.info(f"--- Iteration {iteration} - Remaining: {len(undone_countries)} ---")
            page = self.browser_manager.start()
            
            try:
                # 1. REGISTER MODAL HANDLER IMMEDIATELY
                setup_auto_close_popup(page, self.logger)

                # 2. LOGIN
                creds = self.config['credentials']
                if not login(page, creds['email'], creds['password'], self.config['urls']['login'], self.logger):
                    self.logger.error("Login failed. Retrying iteration...")
                    self.browser_manager.stop()
                    continue 

                current_batch_keys = list(undone_countries.keys())
                
                for key in current_batch_keys:
                    item = undone_countries[key]
                    country_start = time.time()
                    current_idx = total_countries_count - len(undone_countries) + 1
                    
                    self.logger.info(f"\n{'='*60}")
                    self.logger.info(f"[START] STARTING [{current_idx}/{total_countries_count}]: {item} ({key})")
                    self.logger.info(f"{'-'*60}")
                    
                    success = False
                    try:
                        if not navigate_to_trade_data(page, self.logger):
                             raise Exception("Navigation failed")
                        
                        if not select_existing_query(page, creds['query_name'], self.logger):
                             raise Exception("Query selection failed")

                        if not handle_reporter_modification(page, creds['query_name'], self.logger, key):
                            raise Exception("Reporter modification failed")
                        
                        if not click_final_submit(page, self.logger):
                            raise Exception("Final submit failed")
                        
                        success = True
                    except Exception as task_error:
                        self.logger.error(f"Failed to process {key}: {task_error}")
                        break # Break inner loop to refresh browser state on error
                    
                    if success:
                        country_duration = time.time() - country_start
                        # Update timing stats
                        processing_times.append(country_duration)
                        avg_time = sum(processing_times) / len(processing_times)
                        remaining_count = len(undone_countries) - 1 
                        if remaining_count < 0: remaining_count = 0
                        
                        eta_seconds = avg_time * remaining_count
                        eta_formatted = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"

                        self.logger.info(f"[SUCCESS] COMPLETED {key}")
                        self.logger.info(f"   [TIME] Duration : {country_duration:.2f}s")
                        self.logger.info(f"   [TIME] Average  : {avg_time:.2f}s")
                        self.logger.info(f"   [TIME] ETA      : {eta_formatted}")
                        self.logger.info(f"{'='*60}\n")
                        del undone_countries[key]
                        
                        if not self.config.get('headless', False):
                            page.wait_for_timeout(1000)
            
            except Exception as e:
                self.logger.exception(f"Critical error in iteration {iteration}: {e}")
            finally:
                self.browser_manager.stop()
            
            # Stagnation Check
            if len(undone_countries) == last_undone_count:
                stagnant_iterations += 1
            else:
                stagnant_iterations = 0
                last_undone_count = len(undone_countries)
                
            if stagnant_iterations >= 5:
                self.logger.error("Stagnation detected. Aborting.")
                break
            iteration += 1

        if len(undone_countries) == 0:
            self.logger.info("All countries processed successfully!")
            if os.path.exists('undone_countries.json'):
                try: 
                    os.remove('undone_countries.json')
                except: 
                    pass
        else:
            self.logger.warning(f"Process finished with {len(undone_countries)} undone countries.")
            self.logger.warning(f"UNDONE LIST: {list(undone_countries.keys())}")
            self.save_undone_countries(undone_countries)

        self.logger.info(f"Total time consumed: {time.time() - start_time:.2f} seconds.")