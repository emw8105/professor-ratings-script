from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
import datetime

# Set up Chrome options and initialize WebDriver
chrome_options = Options()
chrome_options.add_argument("--log-level=3")
chrome_options.add_argument("--ignore-certificate-errors")
chrome_options.add_argument("--headless")  # headless makes this run much faster

driver = webdriver.Chrome(options=chrome_options)

# open the RMP page
url = "https://www.ratemyprofessors.com/search/professors/1273?q=*"
driver.get(url)

print("Page initialized. Waiting for elements to load...")
time.sleep(2)

# close the cookie popup
try:
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "CCPAModal__StyledCloseButton-sc-10x9kq-2"))
    )
    close_button = driver.find_element(By.CLASS_NAME, "CCPAModal__StyledCloseButton-sc-10x9kq-2")
    driver.execute_script("arguments[0].click();", close_button)
    print("Cookie popup closed.")
    time.sleep(2)
except Exception as e:
    print("No cookie popup found or issue clicking it:", e)

# Spam click the "Show More" button until all professors are loaded
print("Beginning execution, attempting to click 'Show More' button...")
start_time = time.time()
numClicks = 0
while True:
    try:
        show_more_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "PaginationButton__StyledPaginationButton-txi1dr-1"))
        )
        driver.execute_script("arguments[0].click();", show_more_button)
        numClicks += 1
        print(f"Clicked 'Show More' button {numClicks} times.")
        time.sleep(0.25)  # this becomes more of a suggestion rather than the true wait time as the load time increases to ~1 click/sec
    except Exception as e:
        print("No more 'Show More' button found. Exiting loop.")
        break

end_time = time.time()
print(f"Execution complete. Clicked 'Show More' {numClicks} times in {end_time - start_time:.2f} seconds.")

# wait for the professor cards to load just in case
print("Waiting for professor cards to load...")
try:
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CLASS_NAME, "TeacherCard__StyledTeacherCard"))
    )
    print("Professor cards loaded.")
except Exception as e:
    print("Professor cards did not load in time:", e)

# once content is loaded, extract the page source to be webscraped
print("Extracting page source...")
page_source = driver.page_source

driver.quit()

try:
    # Parse with BeautifulSoup
    print("Parsing data...")
    soup = BeautifulSoup(page_source, "html.parser")
    professors = soup.find_all("a", class_="TeacherCard__StyledTeacherCard-syjs0d-0")

    if not professors:
        print("No professor data found. The page source might be incomplete.")

    professor_data = {}

    # for every professor info card, extract the relevant data and store it in a dictionary
    for prof in professors:
        name_tag = prof.find("div", class_="CardName__StyledCardName-sc-1gyrgim-0")
        rating_tag = prof.find("div", class_="CardNumRating__CardNumRatingNumber-sc-17t4b9u-2")
        department_tag = prof.find("div", class_="CardSchool__Department-sc-19lmz2k-0")
        would_take_again_tag = prof.find("div", class_="CardFeedback__CardFeedbackNumber-lq6nix-2")
        difficulty_tag = prof.find_all("div", class_="CardFeedback__CardFeedbackNumber-lq6nix-2")

        name = name_tag.text.strip() if name_tag else "Unknown"
        department = department_tag.text.strip() if department_tag else "Unknown"

        # these values can possibly be "N/A" so we need to check for that
        rating_text = rating_tag.text.strip() if rating_tag else "N/A"
        rating = float(rating_text) if rating_text != "N/A" else "N/A"
        would_take_again_text = would_take_again_tag.text.strip().replace('%', '') if would_take_again_tag else "N/A"
        would_take_again = float(would_take_again_text) if would_take_again_text != "N/A" else "N/A"
        difficulty_text = difficulty_tag[1].text.strip() if difficulty_tag and len(difficulty_tag) > 1 else "N/A"
        difficulty = float(difficulty_text) if difficulty_text != "N/A" else "N/A"
        

        # get the professor's URL and ID from its href attribute
        prof_url = "https://www.ratemyprofessors.com" + prof['href']
        prof_id = prof['href'].split('/')[-1]

        professor_data[name] = {
            "id": prof_id,
            "department": department,
            "url": prof_url,
            "quality_rating": rating,
            "difficulty_rating": difficulty,
            "would_take_again": would_take_again,
            "original_format": name,
            "last_updated": datetime.datetime.now().isoformat()
        }

    # Write to JSON file
    with open("professors.json", "w", encoding="utf-8") as f:
        json.dump(professor_data, f, indent=4, ensure_ascii=False)

    print("Data extraction and file writing complete.")

except Exception as e:
    print("An error occurred during data extraction:", e)
    print("Data extraction failed. Exiting program.")