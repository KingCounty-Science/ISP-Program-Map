""""test chromedriver"""
"""from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument("--headless")  # optional
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument("--headless")  # optional

# Create the driver — this starts the Service internally
driver = webdriver.Chrome(options=options)

# Now you can get the Service and its path
service = driver.service
print("ChromeDriver executable path:", service.path)

driver.quit()