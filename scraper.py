from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
import datetime

def setup_driver(headless=True):
    """Sets up and returns a Selenium WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--ignore-certificate-errors")
    if headless:
        chrome_options.add_argument("--headless")
    return webdriver.Chrome(options=chrome_options)

def close_cookie_popup(driver):
    """Closes the cookie popup if it exists."""
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

def click_show_more(driver):
    """Clicks the 'Show More' button until all professors are loaded."""
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
            # print(f"Clicked 'Show More' button {numClicks} times.")
            time.sleep(0.25)
        except Exception as e:
            print("No more 'Show More' button found. Exiting loop.")
            break
    end_time = time.time()
    print(f"Execution complete. Clicked 'Show More' {numClicks} times in {end_time - start_time:.2f} seconds.")

def wait_for_professor_cards(driver):
    """Waits for professor cards to load."""
    print("Waiting for professor cards to load...")
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "TeacherCard__StyledTeacherCard"))
        )
        print("Professor cards loaded.")
    except Exception as e:
        print("Professor cards did not load in time:", e)

def extract_professor_data(page_source):
    """Extracts and normalizes professor data from the page source."""
    try:
        print("Parsing data...")
        soup = BeautifulSoup(page_source, "html.parser")
        professors = soup.find_all("a", class_="TeacherCard__StyledTeacherCard-syjs0d-0")

        if not professors:
            print("No professor data found. The page source might be incomplete.")
            return {}

        professor_data = {}

        for prof in professors:
            name_tag = prof.find("div", class_="CardName__StyledCardName-sc-1gyrgim-0")
            rating_tag = prof.find("div", class_="CardNumRating__CardNumRatingNumber-sc-17t4b9u-2")
            department_tag = prof.find("div", class_="CardSchool__Department-sc-19lmz2k-0")
            would_take_again_tag = prof.find("div", class_="CardFeedback__CardFeedbackNumber-lq6nix-2")
            difficulty_tag = prof.find_all("div", class_="CardFeedback__CardFeedbackNumber-lq6nix-2")
            ratings_count_tag = prof.find("div", class_="CardNumRating__CardNumRatingCount-sc-17t4b9u-3") # Get the ratings count tag

            name = name_tag.text.strip() if name_tag else "Unknown"
            department = department_tag.text.strip() if department_tag else "Unknown"

            rating_text = rating_tag.text.strip() if rating_tag else "N/A"
            rating = float(rating_text) if rating_text != "N/A" else "N/A"
            would_take_again_text = would_take_again_tag.text.strip().replace('%', '') if would_take_again_tag else "N/A"
            would_take_again = float(would_take_again_text) if would_take_again_text != "N/A" else "N/A"
            difficulty_text = difficulty_tag[1].text.strip() if difficulty_tag and len(difficulty_tag) > 1 else "N/A"
            difficulty = float(difficulty_text) if difficulty_text != "N/A" else "N/A"
            ratings_count_text = ratings_count_tag.text.strip().replace(" ratings", "") if ratings_count_tag else "N/A"
            ratings_count = int(ratings_count_text) if ratings_count_text != "N/A" else "N/A"

            prof_url = "https://www.ratemyprofessors.com" + prof['href']
            prof_id = prof['href'].split('/')[-1]

            normalized_name = " ".join(name.lower().split())

            professor_data[normalized_name] = {
                "id": prof_id,
                "department": department,
                "url": prof_url,
                "quality_rating": rating,
                "difficulty_rating": difficulty,
                "would_take_again": would_take_again,
                "original_format": name,
                "last_updated": datetime.datetime.now().isoformat(),
                "ratings_count": ratings_count
            }
        return professor_data
    except Exception as e:
        print(f"Error extracting professor data: {e}")
        return {}

def scrape_rmp_data(university_id):
    """Scrapes professor data from RateMyProfessors."""
    url = f"https://www.ratemyprofessors.com/search/professors/{university_id}?q=*"
    driver = setup_driver()
    driver.get(url)

    print("Page initialized. Waiting for elements to load...")
    time.sleep(2)

    close_cookie_popup(driver)
    click_show_more(driver)
    wait_for_professor_cards(driver)

    print("Extracting page source...")
    page_source = driver.page_source
    driver.quit()

    professor_data = extract_professor_data(page_source)

    if professor_data:
        with open("rmp_ratings.json", "w", encoding="utf-8") as f:
            json.dump(professor_data, f, indent=4, ensure_ascii=False)
        print("Data extraction and file writing complete.")
    else:
        print("Data extraction failed. Exiting program.")

    return professor_data