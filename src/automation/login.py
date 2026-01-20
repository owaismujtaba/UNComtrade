from automation.navigation import ensure_popup_closed

def login(page, email, password, login_url, logger):
    """Performs the login flow on the WITS website with retries."""
    max_retries = 3
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[LOGIN] Attempt {attempt}/{max_retries}: Navigating to {login_url}...")
            page.goto(login_url, timeout=60000)
            
            # Pre-check for popups that might block input
            ensure_popup_closed(page, logger)

            logger.info("[LOGIN] Entering credentials...")
            page.fill('#UserNameTextBox', email)
            page.fill('#UserPassTextBox', password)
            
            logger.info("[LOGIN] Clicking login...")
            ensure_popup_closed(page, logger)
            page.click('#btnSubmit')
            
            # Wait for navigation after login
            # 'networkidle' can be too strict if there are background pings/analytics.
            # 'domcontentloaded' + explicit element wait is faster and robust enough.
            page.wait_for_load_state('domcontentloaded')
            
            # explicit check for error message
            error_msg = page.locator('span[id*="lblError"], div[class*="error"]')
            if error_msg.count() > 0 and error_msg.first.is_visible():
                text = error_msg.first.text_content().strip()
                if text:
                    logger.error(f"[LOGIN] Failed with error message: {text}")
                    # If it's a password error, don't retry
                    if "password" in text.lower() or "invalid" in text.lower():
                        return False

            # Check if login was successful (Wait for Logout link)
            try:
                # Reduced timeout for success check, but retry loop handles overall robustness
                page.wait_for_selector('text=Logout', timeout=10000)
                logger.info("[LOGIN] Login successful.")
                return True
            except:
                logger.warning(f"[LOGIN] Attempt {attempt} failed (Logout link not found). Retrying...")
        
        except Exception as e:
            logger.error(f"[LOGIN] Exception on attempt {attempt}: {e}")
            
    logger.error("[LOGIN] All login attempts failed.")
    return False
