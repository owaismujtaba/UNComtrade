
import csv
import os
import sys
import re
import time

# Add src to python path for imports to work
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


class ReprocessSuspendedBot:
    """
    Bot to reprocess suspended queries by reading (query_name, reporter_country) pairs
    from CSV and submitting each specific combination.
    """
    
    def __init__(self, config):
        self.config = config
        self.logger = setup_logger(self.__class__.__name__)
        self.browser_manager = BrowserManager(headless=self.config.get('headless', False))
        self.suspended_csv = os.path.join('output', 'suspended', 'suspended_queries.csv')
        self.processed_file = os.path.join('output', 'suspended', 'reprocessed_pairs.txt')
        
    def _load_processed_pairs(self):
        """Load set of already reprocessed (query_name, iso3) pairs."""
        if not os.path.exists(self.processed_file):
            return set()
        
        processed = set()
        with open(self.processed_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    processed.add(line)
        return processed
    
    def _mark_as_processed(self, query_name, iso3):
        """Mark a (query_name, iso3) pair as reprocessed."""
        os.makedirs(os.path.dirname(self.processed_file), exist_ok=True)
        pair_key = f"{query_name}|{iso3}"
        with open(self.processed_file, 'a') as f:
            f.write(f"{pair_key}\n")
    
    def _extract_iso3_from_reporter(self, reporter_field):
        """
        Extract ISO3 code from reporter_country field.
        Format: "TUR	792	Turkey" or "TUR\t792\tTurkey"
        Returns ISO3 code (e.g., "TUR")
        """
        if not reporter_field:
            return None
        
        # Split by tab and take first part
        parts = re.split(r'[\t\s]+', reporter_field.strip())
        if parts:
            iso3 = parts[0].strip()
            # Validate it's 3 uppercase letters
            if len(iso3) == 3 and iso3.isalpha() and iso3.isupper():
                return iso3
        return None
    
    def _load_suspended_pairs(self):
        """
        Read suspended queries CSV and extract (query_name, iso3) pairs.
        CSV format: query_id, query_name, reporter_country, years, trade_flows, timestamp
        Returns list of tuples: [(query_name, iso3, reporter_field), ...]
        Automatically deduplicates based on (query_name, iso3) combination.
        """
        if not os.path.exists(self.suspended_csv):
            self.logger.error(f"Suspended queries CSV not found: {self.suspended_csv}")
            return []
        
        # Use a dict to track unique pairs: key=(query_name, iso3), value=(query_name, iso3, reporter_field)
        unique_pairs = {}
        duplicate_count = 0
        
        try:
            with open(self.suspended_csv, 'r') as f:
                reader = csv.reader(f)
                for row_num, row in enumerate(reader, 1):
                    if len(row) >= 3:
                        query_name = row[1].strip()
                        reporter_field = row[2].strip()
                        iso3 = self._extract_iso3_from_reporter(reporter_field)
                        
                        if query_name and iso3:
                            pair_key = (query_name, iso3)
                            if pair_key in unique_pairs:
                                duplicate_count += 1
                            else:
                                unique_pairs[pair_key] = (query_name, iso3, reporter_field)
                        else:
                            self.logger.warning(f"Row {row_num}: Could not extract valid data from {row[:3]}")
            
            pairs = list(unique_pairs.values())
            self.logger.info(f"Loaded {len(pairs)} unique query-country pairs from CSV")
            if duplicate_count > 0:
                self.logger.info(f"Removed {duplicate_count} duplicate pairs")
            
            return pairs
        
        except Exception as e:
            self.logger.error(f"Error reading suspended queries CSV: {e}")
            return []
    
    def process_pair(self, page, query_name, iso3, reporter_field, idx, total):
        """Process a single (query_name, iso3) pair."""
        self.logger.info("")
        self.logger.info("="*70)
        self.logger.info(f"[{idx}/{total}] Processing: {query_name} - {reporter_field}")
        self.logger.info("-"*70)
        
        start_time = time.time()
        
        try:
            # Step 1: Navigation
            self.logger.info("Step 1: Navigating to Trade Data...")
            if not navigate_to_trade_data(page, self.logger):
                raise Exception("Navigation failed")
            
            # Step 2: Query Selection
            self.logger.info(f"Step 2: Selecting query '{query_name}'...")
            if not select_existing_query(page, query_name, self.logger):
                raise Exception(f"Query selection failed for {query_name}")
            
            # Step 3: Reporter Modification
            self.logger.info(f"Step 3: Modifying reporter to '{iso3}'...")
            if not handle_reporter_modification(page, query_name, self.logger, iso3):
                raise Exception(f"Reporter modification failed for {iso3}")
            
            # Step 4: Final Submit
            self.logger.info("Step 4: Submitting query...")
            if not click_final_submit(page, self.logger):
                raise Exception("Final submit failed")
            
            duration = time.time() - start_time
            self.logger.info(f"✓ Successfully processed in {duration:.2f}s")
            
            # Mark success
            output_dir = os.path.join('output', 'reprocessed')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{query_name}")
            with open(output_file, 'a') as f:
                f.write(f"{iso3}\n")
            
            return True
            
        except Exception as e:
            self.logger.error(f"✗ Failed to process: {e}")
            return False
    
    def run(self):
        """Main execution: load pairs and reprocess them."""
        self.logger.info("="*80)
        self.logger.info("Starting ReprocessSuspendedBot execution...")
        self.logger.info("="*80)
        
        # Load already processed pairs
        processed_pairs = self._load_processed_pairs()
        self.logger.info(f"Already reprocessed: {len(processed_pairs)} pairs")
        
        # Load suspended pairs from CSV
        all_pairs = self._load_suspended_pairs()
        
        if not all_pairs:
            self.logger.warning("No suspended query-country pairs found!")
            return
        
        # Filter out already processed
        pairs_to_process = []
        for query_name, iso3, reporter_field in all_pairs:
            pair_key = f"{query_name}|{iso3}"
            if pair_key not in processed_pairs:
                pairs_to_process.append((query_name, iso3, reporter_field))
        
        if not pairs_to_process:
            self.logger.info("All suspended query-country pairs have been reprocessed!")
            return
        
        self.logger.info(f"Pairs to reprocess: {len(pairs_to_process)}")
        
        # Start browser
        page = self.browser_manager.start()
        
        try:
            setup_auto_close_popup(page, self.logger)
            
            # Login
            creds = self.config['credentials']
            if not login(page, creds['email'], creds['password'], self.config['urls']['login'], self.logger):
                self.logger.error("Login failed!")
                return
            
            self.logger.info("Login successful. Starting to process pairs...")
            
            # Process each pair and track failures
            success_count = 0
            failed_pairs = []
            
            for idx, (query_name, iso3, reporter_field) in enumerate(pairs_to_process, 1):
                if self.process_pair(page, query_name, iso3, reporter_field, idx, len(pairs_to_process)):
                    self._mark_as_processed(query_name, iso3)
                    success_count += 1
                else:
                    # Track failed pair
                    failed_pairs.append((query_name, iso3, reporter_field))
                
                # Wait 10 seconds after every 3 queries
                if idx % 3 == 0 and idx < len(pairs_to_process):
                    self.logger.info(f"[THROTTLE] Completed 3 queries. Waiting 10 seconds...")
                    page.wait_for_timeout(10000)
                # Small delay between queries (if not already waiting)
                elif idx < len(pairs_to_process):
                    page.wait_for_timeout(1000)
            
            self.logger.info("")
            self.logger.info("="*80)
            self.logger.info(f"Initial pass completed! Successfully processed {success_count}/{len(pairs_to_process)} pairs")
            if failed_pairs:
                self.logger.info(f"Failed pairs: {len(failed_pairs)}")
            self.logger.info("="*80)
            
            # Retry failed pairs - stop if no progress for 5 consecutive attempts
            max_no_progress_attempts = 5
            retry_attempt = 0
            no_progress_count = 0
            previous_failed_count = len(failed_pairs)
            
            while failed_pairs and no_progress_count < max_no_progress_attempts:
                retry_attempt += 1
                self.logger.info("")
                self.logger.info("="*80)
                self.logger.info(f"RETRY ATTEMPT {retry_attempt}")
                self.logger.info(f"Retrying {len(failed_pairs)} failed pairs...")
                self.logger.info("="*80)
                
                retry_success_count = 0
                still_failed = []
                
                for idx, (query_name, iso3, reporter_field) in enumerate(failed_pairs, 1):
                    if self.process_pair(page, query_name, iso3, reporter_field, idx, len(failed_pairs)):
                        self._mark_as_processed(query_name, iso3)
                        retry_success_count += 1
                    else:
                        # Still failing
                        still_failed.append((query_name, iso3, reporter_field))
                    
                    # Wait 10 seconds after every 3 queries
                    if idx % 3 == 0 and idx < len(failed_pairs):
                        self.logger.info(f"[THROTTLE] Completed 3 queries. Waiting 10 seconds...")
                        page.wait_for_timeout(10000)
                    # Small delay between queries
                    elif idx < len(failed_pairs):
                        page.wait_for_timeout(1000)
                
                self.logger.info("")
                self.logger.info(f"Retry attempt {retry_attempt} completed: {retry_success_count} successes, {len(still_failed)} still failing")
                
                # Check if we made progress
                if len(still_failed) == previous_failed_count:
                    no_progress_count += 1
                    self.logger.info(f"No progress made. No-progress count: {no_progress_count}/{max_no_progress_attempts}")
                    if no_progress_count >= max_no_progress_attempts:
                        self.logger.info(f"Failed list unchanged for {max_no_progress_attempts} consecutive retries. Stopping.")
                        failed_pairs = still_failed
                        break
                else:
                    # Made progress, reset counter
                    no_progress_count = 0
                    self.logger.info(f"Progress made! Reduced failures from {previous_failed_count} to {len(still_failed)}")
                
                # Update for next iteration
                previous_failed_count = len(still_failed)
                failed_pairs = still_failed

            
            # Final summary
            self.logger.info("")
            self.logger.info("="*80)
            self.logger.info("FINAL SUMMARY")
            self.logger.info("="*80)
            total_success = len(pairs_to_process) - len(failed_pairs)
            self.logger.info(f"Total successes: {total_success}/{len(pairs_to_process)}")
            if failed_pairs:
                self.logger.info(f"Permanently failed pairs: {len(failed_pairs)}")
                self.logger.info("Failed pairs list:")
                for query_name, iso3, reporter_field in failed_pairs:
                    self.logger.info(f"  - {query_name} | {reporter_field}")
            else:
                self.logger.info("All pairs processed successfully!")
            self.logger.info("="*80)
            
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            self.logger.exception(e)
        finally:
            self.browser_manager.stop()

