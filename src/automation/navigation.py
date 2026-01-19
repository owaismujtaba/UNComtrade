def navigate_to_trade_data(page, logger):
    """Navigates to Advanced Query > Trade Data via the top menu."""
    logger.info("Navigating to Advanced Query > Trade Data...")
    
    # Hover on Advanced Query
    advanced_query_menu = page.locator('a.dropdown-toggle:has-text("Advanced Query")').first
    advanced_query_menu.hover()
    page.wait_for_timeout(500)
    
    # Click Trade Data (UN Comtrade)
    trade_data_link = page.locator('#TopMenu1_RawTradeData')
    trade_data_link.click()
    
    page.wait_for_load_state('networkidle')
    logger.info("Reached Trade Data page.")
    return True

def select_existing_query(page, query_name, logger):
    """Selects an existing query from the dropdown and clicks Proceed."""
    # User requested to click on 'Select a Query' (the dropdown itself) directly
    logger.info("Clicking the 'Select a Query' dropdown...")
    dropdown = page.locator('#MainContent_cboExistingQuery')
    dropdown.click()
    
    logger.info(f"Selecting query: {query_name}...")
    
    # Get options and find the one that matches the query name
    options = dropdown.locator('option').all()
    target_value = None
    for option in options:
        text = option.text_content().strip()
        if query_name in text:
            target_value = option.get_attribute('value')
            logger.info(f"Found match: '{text}' (Value: {target_value})")
            break
            
    if target_value:
        dropdown.select_option(value=target_value)
        # Wait for potential AJAX loading
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # Check for popups before clicking Proceed
        handle_unexpected_popups(page, logger)
        
        logger.info("Clicking 'Proceed'...")
        page.click('#MainContent_btnProceed')
        page.wait_for_load_state('networkidle')
        return True
    else:
        logger.error(f"Could not find query '{query_name}' in the dropdown.")
        return False

def handle_unexpected_popups(page, logger):
    """Checks for and closes unexpected popups (e.g., Qualtrics surveys)."""
    try:
        # Qualtrics popup container - Check for any generic blocking overlay
        # We use a broad selector for the container
        popup = page.locator('.QSIWebResponsive')
        
        if popup.count() > 0 and popup.is_visible():
            logger.info("Unexpected popup detected. Attempting to close...")
            
            # 1. Try standard close buttons
            # Matches: X button, "No thanks", "No, thanks", "No, thanks.", "Not now", "Later", "No"
            close_btn = page.locator('.QSIWebResponsive-creative-close-button, [aria-label="Close"], button:has-text("No thanks"), button:has-text("No, thanks"), button:has-text("No, thanks."), button:has-text("Not now"), button:has-text("Later"), button:has-text("No")').first
            if close_btn.count() > 0 and close_btn.is_visible():
                try:
                    close_btn.click(timeout=2000)
                    logger.info("Popup closed via button.")
                    page.wait_for_timeout(500)
                    return
                except:
                    logger.warning("Failed to click popup close button.")

            # 2. Aggressive Fallback: Remove from DOM via JS
            logger.info("Attempting to force-remove popup via JavaScript...")
            page.evaluate("() => { const el = document.querySelector('.QSIWebResponsive'); if (el) el.remove(); }")
            logger.info("Popup element removed from DOM.")
            page.wait_for_timeout(500)
            
    except Exception as e:
        logger.warning(f"Error handling popup: {e}")

def click_final_submit(page, logger):
    """Clicks the final Submit button to run the query."""
    logger.info("Clicking final 'Submit' button...")
    
    # Handle popups before clicking
    handle_unexpected_popups(page, logger)
    
    # Handle potentially stuck Telerik overlays (intercepting clicks)
    overlay = page.locator('.TelerikModalOverlay')
    if overlay.count() > 0 and overlay.is_visible():
        logger.info("Telerik Overlay detected. Waiting for it to disappear...")
        try:
            # Wait up to 3 seconds for it to fade naturally
            overlay.wait_for(state='hidden', timeout=3000)
        except:
            logger.warning("Overlay stuck. Forcing removal...")
            page.evaluate("document.querySelectorAll('.TelerikModalOverlay').forEach(el => el.style.display = 'none');")
            page.wait_for_timeout(500)
    
    submit_btn = page.locator('#MainContent_btnSaveExecute')
    if submit_btn.count() > 0:
        # Force click if necessary, or just standard click now that overlay is gone
        submit_btn.click()
        logger.info("Submit clicked.")
        # Wait for page load or indication of completion
        # Assuming it goes to a new page or reloads
        try:
            page.wait_for_load_state('networkidle', timeout=10000)
        except:
            logger.warning("Timeout waiting for networkidle after Submit, proceeding anyway.")
        return True
    else:
        logger.error("Submit button (#MainContent_btnSaveExecute) not found.")
        return False
