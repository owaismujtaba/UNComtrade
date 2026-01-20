import logging

def ensure_popup_closed(page, logger):
    """
    Manually checks and closes the popup if visible. 
    Useful to call before critical actions.
    Checks main page and all frames.
    """
    try:
        # 1. Check Main Page
        no_thanks = page.get_by_role("button", name="No, thanks.")
        if no_thanks.is_visible():
            logger.info("Feedback modal detected (Manual Check)! Clicking 'No, thanks.'...")
            no_thanks.click()
            page.wait_for_timeout(100)
            return

        # 2. Check Frames (if popup might be inside one)
        for frame in page.frames:
            try:
                btn = frame.get_by_role("button", name="No, thanks.")
                if btn.is_visible():
                    logger.info(f"Feedback modal detected in frame '{frame.name or frame.url}'! Clicking...")
                    btn.click()
                    page.wait_for_timeout(100)
                    return
            except: pass
    except Exception:
        pass

def setup_auto_close_popup(page, logger):
    """
    Registers a global handler that automatically clicks 'No, thanks.' 
    whenever the World Bank feedback modal appears.
    """
    logger.info("Setting up global popup handler for World Bank feedback modal.")
    
    # Target the exact button text and punctuation from the screenshot
    # We use a broad locator strategy to be safe
    no_thanks_locator = page.get_by_role("button", name="No, thanks.")
    
    # Use add_locator_handler to intercept the modal as soon as it appears 
    # and before it blocks subsequent clicks.
    try:
        page.add_locator_handler(no_thanks_locator, lambda: (
            logger.info("Feedback modal detected (Auto)! Clicking 'No, thanks.' to resume..."),
            no_thanks_locator.click()
        ))
    except Exception as e:
        logger.warning(f"Failed to register auto-popup handler (might not be supported on this page context): {e}")

def navigate_to_trade_data(page, logger):
    """Navigates to Advanced Query > Trade Data via the top menu."""
    logger.info("Navigating to Advanced Query > Trade Data...")
    
    ensure_popup_closed(page, logger) # Check before interacting
    
    advanced_query_menu = page.locator('a.dropdown-toggle:has-text("Advanced Query")').first
    # Reduce timeout to fail fast if overlay/element is stuck (default is 30s)
    try:
        advanced_query_menu.hover(timeout=5000) 
    except:
        logger.info("Hover timed out. Attempting forceful click on submenu directly...")
    
    # advanced_query_menu.hover() - hover usually doesn't trigger network, keeping small wait for UI stability
    page.wait_for_timeout(200)
    
    ensure_popup_closed(page, logger)
    trade_data_link = page.locator('#TopMenu1_RawTradeData')
    trade_data_link.click(force=True)
    
    page.wait_for_load_state('networkidle')
    return True

def navigate_to_download_and_view_results(page, logger):
    """Navigates to Results > Download and View Results via the top menu."""
    logger.info("Navigating to Results > Download and View Results...")
    
    try:
        ensure_popup_closed(page, logger)
        
        results_menu = page.locator('a.dropdown-toggle:has-text("Results")').first
        results_menu.wait_for(state='visible', timeout=5000)
        results_menu.hover()
        page.wait_for_timeout(1000)
        
        ensure_popup_closed(page, logger)
        download_link = page.locator('#TopMenu1_DownloadandViewResults')
        
        # If not visible after hover, try clicking the menu to expand
        if not download_link.is_visible():
            logger.info("Submenu not visible after hover, clicking 'Results' menu...")
            results_menu.click()
            
        download_link.wait_for(state='visible', timeout=5000)
        download_link.click()
        
        page.wait_for_load_state('networkidle')
        return True
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return False

def select_existing_query(page, query_name, logger):
    """Selects an existing query from the dropdown and clicks Proceed."""
    ensure_popup_closed(page, logger)
    
    dropdown = page.locator('#MainContent_cboExistingQuery')
    dropdown.wait_for(state='visible', timeout=5000)
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
        # Dropdown change might trigger postback or loading
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(500) # Give extra time for any UI updates
        
        ensure_popup_closed(page, logger)
        proceed_btn = page.locator('#MainContent_btnProceed')
        proceed_btn.wait_for(state='visible', timeout=5000)
        proceed_btn.click()
        
        page.wait_for_load_state('networkidle')
        return True
    return False

def click_final_submit(page, logger):
    """Clicks the final Submit button, handling potential Telerik overlays."""
    ensure_popup_closed(page, logger)
    
    # Force remove stuck Telerik overlays via JS to ensure the button is clickable.
    page.evaluate("""
        document.querySelectorAll('.TelerikModalOverlay').forEach(el => el.style.display = 'none');
    """)
    
    submit_btn = page.locator('#MainContent_btnSaveExecute')
    if submit_btn.is_visible():
        ensure_popup_closed(page, logger)
        submit_btn.click()
        page.wait_for_load_state('networkidle')
        return True
    return False