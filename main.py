from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
import datetime
import csv
import os
import re
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

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
            print(f"Clicked 'Show More' button {numClicks} times.")
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
    """Extracts professor data from the page source."""
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

            name = name_tag.text.strip() if name_tag else "Unknown"
            department = department_tag.text.strip() if department_tag else "Unknown"

            rating_text = rating_tag.text.strip() if rating_tag else "N/A"
            rating = float(rating_text) if rating_text != "N/A" else "N/A"
            would_take_again_text = would_take_again_tag.text.strip().replace('%', '') if would_take_again_tag else "N/A"
            would_take_again = float(would_take_again_text) if would_take_again_text != "N/A" else "N/A"
            difficulty_text = difficulty_tag[1].text.strip() if difficulty_tag and len(difficulty_tag) > 1 else "N/A"
            difficulty = float(difficulty_text) if difficulty_text != "N/A" else "N/A"

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
        return professor_data

    except Exception as e:
        print("An error occurred during data extraction:", e)
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
        with open("professors.json", "w", encoding="utf-8") as f:
            json.dump(professor_data, f, indent=4, ensure_ascii=False)
        print("Data extraction and file writing complete.")
    else:
        print("Data extraction failed. Exiting program.")

    return professor_data



# John P Cole --> John Cole
def normalize_instructor_name(name):
    """Normalize instructor names by removing middle initials and extra spaces."""
    name = name.strip()
    name = re.sub(r"\s*,\s*", ", ", name)
    name = re.sub(r"\s+[A-Z]\s*$", "", name)
    return name

def calculate_professor_ratings(data_dir="data"):
    """
    Calculates professor ratings based on grade distributions from CSV files
    in the specified directory. Only the "Instructor 1" column is used.

    Returns:
        dict: A dictionary containing professor ratings. The keys are professor
              names, and the values are dictionaries containing:
              - 'overall_rating': The professor's overall rating (scaled out of 5)
              - 'course_ratings': A dictionary of course-specific ratings.
    """
    professor_data = {}

    # grade values based on UTD policy
    grade_values = {
        "A+": 4.0,
        "A": 4.0,
        "A-": 3.67,
        "B+": 3.33,
        "B": 3.0,
        "B-": 2.67,
        "C+": 2.33,
        "C": 2.0,
        "C-": 1.67,
        "D+": 1.33,
        "D": 1.00,
        "D-": 0.67,
        "F": 0.0,
        "W": 0.67,  # Withdrawal is penalized, but less severely than an F
        "P": 4.0,  # might want to use median over average to mitigate covid's popularity of this, or just remove it
        "NP": 0.0
    }

    # loop over each CSV file in the data directory
    for filename in os.listdir(data_dir):
        if filename.endswith(".csv"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    instructor = normalize_instructor_name(row.get("Instructor 1", "")) # instructor 1 is the only instructor that matters for these purposes
                    subject = row.get("Subject", "").strip() # i.e. CS
                    catalog_nbr = row.get('"Catalog Nbr"') or row.get("Catalog Nbr", "") # i.e. 3345, there's quotes around the column name for some reason
                    catalog_nbr = catalog_nbr.strip()

                    if not instructor or not subject or not catalog_nbr: # skip rows with missing data
                        continue

                    course = f"{subject}{catalog_nbr}" # i.e. CS3345

                    row_grades = {grade: int(float(row.get(grade, 0) or 0)) for grade in grade_values} # get the grade distribution for the row

                    if sum(row_grades.values()) == 0: # skip rows with no grades
                        continue

                    # add the grade distribution to the professor's data
                    if instructor not in professor_data:
                        professor_data[instructor] = {"course_grades": {}}
                    if course not in professor_data[instructor]["course_grades"]:
                        professor_data[instructor]["course_grades"][course] = {g: 0 for g in grade_values}

                    for grade, count in row_grades.items():
                        professor_data[instructor]["course_grades"][course][grade] += count

    # calculate overall and course-specific ratings for each professor
    # overall rating is the average of all grades given, can be used for predicting how a professor will grade in untaught courses
    for instructor, data in professor_data.items():
        all_grades = {}
        for course, grades in data["course_grades"].items():
            for grade, count in grades.items():
                all_grades[grade] = all_grades.get(grade, 0) + count

        total_points = sum(grade_values[grade] * count for grade, count in all_grades.items())
        total_count = sum(all_grades.values())

        overall_rating = round((total_points / total_count) / 4.0 * 5, 2) if total_count > 0 else "N/A" # calculate the overall rating, round to 2 decimal places

        professor_data[instructor]["overall_rating"] = overall_rating

        course_ratings = {}
        for course, grades in data["course_grades"].items():
            course_points = sum(grade_values[grade] * count for grade, count in grades.items())
            course_count = sum(grades.values())
            course_ratings[course] = round((course_points / course_count) / 4.0 * 5, 2) if course_count > 0 else "N/A"

        professor_data[instructor]["course_ratings"] = course_ratings

    return professor_data

# this is how the data will be saved in theory, the grade distributions themselves arent necessary as we can just get them from the CSVs
# the aggregate data is the part that matters
def save_without_grades(professor_data, output_filename="professor_ratings_no_grades.json"):
    filtered_data = {
        instructor: {
            "overall_rating": data["overall_rating"],
            "course_ratings": data["course_ratings"]
        }
        for instructor, data in professor_data.items()
    }

    with open(output_filename, "w", encoding="utf-8") as outfile:
        json.dump(filtered_data, outfile, indent=4, ensure_ascii=False)

    print(f"Professor ratings (without grades) saved to {output_filename}")

import json

def match_professor_names(ratings, rmp_data):
    """
    Matches professor data, handles different name formats, and saves unmatched names.
    """
    matched_data = {}
    unmatched_ratings = []
    unmatched_rmp = []

    def normalize_name(name):
        """Normalizes names to 'First Last' format."""
        if ", " in name:
            last, first = name.split(", ", 1)
            return f"{first} {last}"
        return name

    normalized_ratings = {normalize_name(name): data for name, data in ratings.items()}

    for rmp_name, rmp_info in rmp_data.items():
        if rmp_name in normalized_ratings:
            matched_data[rmp_name] = {**rmp_info, **ratings[list(ratings.keys())[list(normalized_ratings.keys()).index(rmp_name)]]}
        else:
            unmatched_rmp.append(rmp_name)

    for ratings_name, ratings_info in ratings.items():
        normalized_name = normalize_name(ratings_name)
        if normalized_name not in rmp_data:
            unmatched_ratings.append(ratings_name)

    print(f"Unmatched Ratings: {len(unmatched_ratings)}")
    print(f"Unmatched RMP: {len(unmatched_rmp)}")

    # Save unmatched names to JSON files
    with open("unmatched_ratings.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_ratings, f, indent=4, ensure_ascii=False)

    with open("unmatched_rmp.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_rmp, f, indent=4, ensure_ascii=False)

    return matched_data


def main():
    # commented out for testing the matching function, just pulls the previously saved json data from the file rather than recalculating every time
    # ratings = calculate_professor_ratings() # get the ratings
    # # find_duplicate_course_numbers(ratings) # test
    # save_without_grades(ratings) # example output with just aggregate data

    # # output_filename = "professor_ratings.json"
    # # with open(output_filename, "w", encoding="utf-8") as outfile:
    # #     json.dump(ratings, outfile, indent=4, ensure_ascii=False)

    # # print(f"Professor ratings saved to {output_filename}")

    # print("Scraping professor data from RateMyProfessors...")
    # scrape_rmp_data(university_id="1273")

    # # now we need to match the data from the two sources


    # Load pre-scraped ratings data
    print("Loading professor ratings data...")
    with open("professor_ratings_no_grades.json", "r", encoding="utf-8") as file:
        ratings = json.load(file)

    # Load pre-scraped RMP data
    print("Loading RateMyProfessors data...")
    with open("professors.json", "r", encoding="utf-8") as file:
        rmp_data = json.load(file)

    print("Matching professor data from both sources...")
    matched_data = match_professor_names(ratings, rmp_data) # we need to implement this

    # Save or process the matched data
    output_filename = "matched_professor_data.json"
    with open(output_filename, "w", encoding="utf-8") as outfile:
        json.dump(matched_data, outfile, indent=4, ensure_ascii=False)

    print(f"Matched professor data saved to {output_filename}")


if __name__ == "__main__":
    main()
