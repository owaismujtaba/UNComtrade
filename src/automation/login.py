def login(page, email, password, login_url, logger):
    """Performs the login flow on the WITS website."""
    logger.info(f"Navigating to {login_url}...")
    page.goto(login_url)
    
    logger.info("Entering credentials...")
    page.fill('#UserNameTextBox', email)
    page.fill('#UserPassTextBox', password)
    
    logger.info("Clicking login...")
    page.click('#btnSubmit')
    
    # Wait for navigation after login
    page.wait_for_load_state('networkidle')
    
    # Check if login was successful (e.g., check for Logout link)
    if page.locator('text=Logout').is_visible():
        logger.info("Login successful.")
        return True
    else:
        logger.error("Login failed or encountered a CAPTCHA.")
        return False
