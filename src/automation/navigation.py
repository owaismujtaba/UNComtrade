import logging

def setup_auto_close_popup(page, logger):
    """
    Registers a global handler that automatically clicks 'No, thanks.' 
    whenever the World Bank feedback modal appears.
    """
    logger.info("Setting up global popup handler for World Bank feedback modal.")
    
    # Target the exact button text and punctuation from the screenshot
    no_thanks_locator = page.get_by_role("button", name="No, thanks.")
    
    # Use add_locator_handler to intercept the modal as soon as it appears 
    # and before it blocks subsequent clicks.
    page.add_locator_handler(no_thanks_locator, lambda: (
        logger.info("Feedback modal detected! Clicking 'No, thanks.' to resume..."),
        no_thanks_locator.click()
    ))

def navigate_to_trade_data(page, logger):
    """Navigates to Advanced Query > Trade Data via the top menu."""
    logger.info("Navigating to Advanced Query > Trade Data...")
    
    advanced_query_menu = page.locator('a.dropdown-toggle:has-text("Advanced Query")').first
    advanced_query_menu.hover()
    page.wait_for_timeout(500)
    
    trade_data_link = page.locator('#TopMenu1_RawTradeData')
    trade_data_link.click()
    
    page.wait_for_load_state('networkidle')
    return True

def navigate_to_download_and_view_results(page, logger):
    """Navigates to Results > Download and View Results via the top menu."""
    logger.info("Navigating to Results > Download and View Results...")
    
    try:
        results_menu = page.locator('a.dropdown-toggle:has-text("Results")').first
        results_menu.wait_for(state='visible')
        results_menu.hover()
        page.wait_for_timeout(500)
        
        download_link = page.locator('#TopMenu1_DownloadandViewResults')
        
        # If not visible after hover, try clicking the menu to expand
        if not download_link.is_visible():
            logger.info("Submenu not visible after hover, clicking 'Results' menu...")
            results_menu.click()
            
        download_link.wait_for(state='visible', timeout=1000)
        download_link.click()
        
        page.wait_for_load_state('domcontentloaded')
        return True
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return False

def select_existing_query(page, query_name, logger):
    """Selects an existing query from the dropdown and clicks Proceed."""
    dropdown = page.locator('#MainContent_cboExistingQuery')
    dropdown.click()
    
    options = dropdown.locator('option').all()
    target_value = None
    for option in options:
        text = option.text_content().strip()
        if query_name in text:
            target_value = option.get_attribute('value')
            break
            
    if target_value:
        dropdown.select_option(value=target_value)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        page.click('#MainContent_btnProceed')
        page.wait_for_load_state('networkidle')
        return True
    return False

def click_final_submit(page, logger):
    """Clicks the final Submit button, handling potential Telerik overlays."""
    # Force remove stuck Telerik overlays via JS to ensure the button is clickable.
    page.evaluate("""
        document.querySelectorAll('.TelerikModalOverlay').forEach(el => el.style.display = 'none');
    """)
    
    submit_btn = page.locator('#MainContent_btnSaveExecute')
    if submit_btn.is_visible():
        submit_btn.click()
        page.wait_for_load_state('networkidle')
        return True
    return False