from automation.navigation import handle_unexpected_popups

def handle_reporter_modification(page, query_name, logger, key):
    """Locates and clicks the 'Modify' link for Reporters and handles subsequent modals."""
    if "QueryDefinitionSelection" not in page.url:
        logger.warning(f"Not on the expected selection page. Current URL: {page.url}")
        return False

    logger.info("On Query Definition Selection page.")
    
    # Target the 'Modify' link for Reporters
    modify_link = page.locator('#divRptrmodify a')
    
    # Check for popups BEFORE checking specifically for the link, as popups might obscure it
    handle_unexpected_popups(page, logger)
    
    if modify_link.count() > 0 and modify_link.is_visible():
        logger.info(f"Clicking '{modify_link.text_content().strip()}' for Reporters...")
        
        # Setup dialog handler to click 'OK' on the alert
        def handle_dialog(dialog):
            logger.info(f"Alert detected: {dialog.message}. Clicking OK.")
            dialog.accept()
        
        page.on("dialog", handle_dialog)
        
        # Double check popup just in case it appeared during the millisecond gap
        handle_unexpected_popups(page, logger)
        modify_link.click()
        
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(3000)
        
        # Remove dialog handler
        page.remove_listener("dialog", handle_dialog)
        
        # Handle 'Country List' or 'New Query' modal if it appears
        if page.locator('.rwWindowContent').is_visible():
            title_node = page.locator('.rwTitleRow')
            title = title_node.text_content().strip() if title_node.count() > 0 else "Unknown Modal"
            logger.info(f"Modal detected: {title}")
            
            if "Country List" in title:
                logger.info("Handling 'Country List' modal...")
                # The content is inside an iframe
                iframe_locator = page.frame_locator('iframe[src*="CountryList.aspx"]')
                
                logger.info("Clicking 'Clear All'...")
                clear_all = iframe_locator.locator('a.clearall')
                if clear_all.count() > 0:
                    clear_all.click()
                    page.wait_for_timeout(500)
                
                logger.info("Clicking 'Enter CountryISO3 Codes' + icon...")
                plus_icon = iframe_locator.locator('img#Img1')
                if plus_icon.count() > 0:
                    plus_icon.click()
                    page.wait_for_timeout(500)
                
                # New logic: Fill key, add, and proceed
                logger.info(f"Entering ISO3 code: {key}")
                textarea = iframe_locator.locator('textarea#txtCntry')
                textarea.fill(key)
                
                logger.info("Clicking '>' button...")
                add_btn = iframe_locator.locator('input#btnCntryCode')
                add_btn.click()
                page.wait_for_timeout(1000)
                
                logger.info("Clicking modal 'Proceed' button...")
                proceed_btn = iframe_locator.locator('input#CountryList1_btnProcess')
                if proceed_btn.count() > 0:
                    proceed_btn.click()
                    page.wait_for_load_state('networkidle')
                    page.wait_for_timeout(500)
                    return True
                else:
                    logger.warning("Could not find Proceed button in Country List modal.")
                    return False

            elif "New Query" in title:
                logger.info(f"Handling 'New Query' modal with name: {query_name}")
                
                # RadWindow often uses iframes. Look for ENABLED input in all frames.
                target_input = None
                active_frame = None
                for frame in page.frames:
                    try:
                        # We look for a text input that is visible and NOT disabled
                        input_locs = frame.locator('input[type="text"]').all()
                        for loc in input_locs:
                            if loc.is_visible() and loc.is_enabled():
                                target_input = loc
                                active_frame = frame
                                logger.info(f"Found enabled input in frame: {frame.url}")
                                break
                        if target_input:
                            break
                    except:
                        continue
                
                if target_input:
                    target_input.fill(query_name)
                    # Find save button in the same context (frame or page)
                    save_btn = active_frame.locator('input[value="Save"], button:has-text("Save")').first
                    
                    if save_btn.count() == 0:
                        save_btn = page.locator('.rwWindowContent input[value="Save"], .rwWindowContent button:has-text("Save")').first
                    
                    if save_btn.count() > 0:
                        logger.info("Clicking 'Save' on modal...")
                        save_btn.click()
                    else:
                        logger.warning("Could not find Save button.")
                else:
                    logger.warning("Could not find ANY enabled input in modal frames.")
                    # Take debug screenshot
                    page.screenshot(path='modal_no_input_debug.png')
                
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(1000)
                
        # Capture verification screenshot
        screenshot_path = 'reporter_selection_result.png'
        page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"Screenshot of reporter selection saved to {screenshot_path}")
        return True
    else:
        logger.error("Could not find visible 'Modify' link for Reporters (#divRptrmodify a).")
        page.screenshot(path='error_no_modify_link.png')
        return False
