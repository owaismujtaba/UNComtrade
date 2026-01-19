def login(page, email, password, login_url, logger):
    """Performs the login flow on the WITS website."""
    logger.info(f"Navigating to {login_url}...")
    page.goto(login_url)
    
    logger.info("Entering credentials...")
    page.fill('#UserNameTextBox', email)
    page.fill('#UserPassTextBox', password)
    
    logger.info("Clicking login...")
    page.click('#btnSubmit')
    
    # Wait for navigation after login (relaxed)
    page.wait_for_load_state('domcontentloaded')
    
    # Check if login was successful (Wait for Logout link)
    try:
        page.wait_for_selector('text=Logout', timeout=15000)
        logger.info("Login successful.")
        return True
    except:
        logger.error("Login failed or encountered a CAPTCHA (Logout link not found).")
        return False
