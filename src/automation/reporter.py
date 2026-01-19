from automation.navigation import setup_auto_close_popup
from automation.navigation import ensure_popup_closed

def handle_reporter_modification(page, query_name, logger, country_code):
    """
    Handles the modification of the Reporter tab to select a specific country.
    """
    logger.info(f"Modifying Reporter for country code: {country_code}")
    
    # Check for "Modify" link in the Reporter section
    modify_link = page.locator('#divRptrmodify a')
    
    ensure_popup_closed(page, logger) # Check before interacting
    
    try:
        # Wait for modify link to be visible (max 10s)
        # This handles cases where the page takes a moment to settle after potential popup closure
        modify_link.wait_for(state='visible', timeout=10000)
    except:
        logger.warning("Modify link wait timed out. proceeding to check visibility...")

    if modify_link.is_visible():
        logger.info(f"Clicking 'Modify' for Reporters...")
        
        # Setup dialog handler for the 'Are you sure' alert WITS often throws
        def handle_dialog(dialog):
            logger.info(f"Alert detected: {dialog.message}. Clicking OK.")
            dialog.accept()
        
        page.on("dialog", handle_dialog)
        
        # Click the link
        modify_link.click()
        
        # Wait for the WITS RadWindow to appear
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        ensure_popup_closed(page, logger) # Check after modal opens

        # Cleanup dialog handler
        page.remove_listener("dialog", handle_dialog)
        
        # ---------------------------------------------------------
        # MODAL HANDLING (Country List / New Query)
        # ---------------------------------------------------------
        modal_content = page.locator('.rwWindowContent')
        if modal_content.is_visible():
            title_node = page.locator('.rwTitleRow')
            title = title_node.text_content().strip() if title_node.count() > 0 else "Unknown Modal"
            logger.info(f"Modal detected: {title}")
            
            if "Country List" in title:
                iframe = page.frame_locator('iframe[src*="CountryList.aspx"]')
                
                logger.info("Clearing existing selections...")
                clear_btn = iframe.locator('a.clearall, input[value="Clear All"]')
                if clear_btn.count() > 0:
                     clear_btn.first.click()
                page.wait_for_timeout(500)
                
                logger.info("Opening ISO3 input area...")
                img_lookup = iframe.locator('img#Img1, img[title="Find Country"]')
                if img_lookup.count() > 0:
                     img_lookup.first.click()
                page.wait_for_timeout(500)
                
                logger.info(f"Entering ISO3: {country_code}")
                iframe.locator('textarea#txtCntry').fill(country_code)
                iframe.locator('input#btnCntryCode').click()
                page.wait_for_timeout(1000)
                
                logger.info("Finalizing Country Selection...")
                proceed_btn = iframe.locator('input#CountryList1_btnProcess')
                if proceed_btn.count() > 0:
                    proceed_btn.click()
                    page.wait_for_load_state('networkidle')
                    return True
                return False

            elif "New Query" in title:
                # Handle query naming modal if required
                logger.info("New Query modal handling...")
                for frame in page.frames:
                    target_input = frame.locator('input[type="text"]:enabled:visible').first
                    if target_input.count() > 0:
                        target_input.fill(query_name)
                        save_btn = frame.locator('input[value="Save"], button:has-text("Save")').first
                        if save_btn.count() > 0:
                             save_btn.click()
                             break
                page.wait_for_load_state('networkidle')
        
        return True
    else:
        logger.error("Modify link not found or obscured.")
        try:
             page.screenshot(path='modify_link_error.png')
        except: pass
        return False