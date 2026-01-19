from automation.navigation import setup_auto_close_popup

def handle_reporter_modification(page, query_name, logger, key):
    """Locates and clicks the 'Modify' link for Reporters and handles subsequent modals."""
    if "QueryDefinitionSelection" not in page.url:
        logger.warning(f"Not on the expected selection page. Current URL: {page.url}")
        return False

    logger.info(f"Modifying reporter for: {key}")
    
    # The global handler (setup in SendQueryBot) deals with the feedback popup.
    # However, we must ensure the 'Modify' link is actually clickable.
    modify_link = page.locator('#divRptrmodify a')
    
    # Wait for any potential blocking popups to be cleared by the handler
    # We check if the 'No, thanks.' button exists; if so, we wait for it to disappear.
    feedback_popup = page.get_by_role("button", name="No, thanks.")
    if feedback_popup.is_visible():
        logger.info("Feedback popup obscuring view. Waiting for auto-handler...")
        feedback_popup.wait_for(state="hidden", timeout=1000)

    if modify_link.count() > 0 and modify_link.is_visible():
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
                iframe.locator('a.clearall').click()
                page.wait_for_timeout(500)
                
                logger.info("Opening ISO3 input area...")
                iframe.locator('img#Img1').click()
                page.wait_for_timeout(500)
                
                logger.info(f"Entering ISO3: {key}")
                iframe.locator('textarea#txtCntry').fill(key)
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
                for frame in page.frames:
                    target_input = frame.locator('input[type="text"]:enabled:visible').first
                    if target_input.count() > 0:
                        target_input.fill(query_name)
                        save_btn = frame.locator('input[value="Save"], button:has-text("Save")').first
                        save_btn.click()
                        break
                page.wait_for_load_state('networkidle')
        
        return True
    else:
        logger.error("Modify link not found or obscured.")
        page.screenshot(path='modify_link_error.png')
        return False