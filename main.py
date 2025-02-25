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

            normalized_name = " ".join(name.lower().split()) # used to help with matching to the grades data

            professor_data[normalized_name] = {
                "id": prof_id,
                "department": department,
                "url": prof_url,
                "quality_rating": rating,
                "difficulty_rating": difficulty,
                "would_take_again": would_take_again,
                "original_format": name, # original format can be used for reference in case the normalized name butchers the original
                "last_updated": datetime.datetime.now().isoformat()
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
              - 'overall_grade_rating': The professor's overall rating of their aggregated grade distributions (scaled out of 5)
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

        professor_data[instructor]["overall_grade_rating"] = overall_rating

        course_ratings = {}
        for course, grades in data["course_grades"].items():
            course_points = sum(grade_values[grade] * count for grade, count in grades.items())
            course_count = sum(grades.values())
            course_ratings[course] = round((course_points / course_count) / 4.0 * 5, 2) if course_count > 0 else "N/A"

        professor_data[instructor]["course_ratings"] = course_ratings

    return professor_data

# this is how the data will be saved in theory, the grade distributions themselves arent necessary as we can just get them from the CSVs
# the aggregate data is the part that matters
def save_without_grades(professor_data, output_filename="grade_ratings.json"):
    filtered_data = {
        instructor: {
            "overall_grade_rating": data["overall_grade_rating"],
            "course_ratings": data["course_ratings"]
        }
        for instructor, data in professor_data.items()
    }

    with open(output_filename, "w", encoding="utf-8") as outfile:
        json.dump(filtered_data, outfile, indent=4, ensure_ascii=False)

    print(f"Professor ratings (without grades) saved to {output_filename}")

def normalize_name(name):
    """Normalizes names, removes periods, handles middle names, replaces hyphens, and potential swaps."""
    name = " ".join(name.split())
    name = re.sub(r'\.', '', name)
    name = name.replace('-', ' ')
    
    if ", " in name: # handle the Last, First formats by splitting up and swapping
        last, first = name.split(", ", 1)
        return f"{first.strip().lower()} {last.strip().lower()}"
    else:
        parts = name.split()
        if len(parts) > 2:
            return f"{parts[0].strip().lower()} {parts[-1].strip().lower()}"
        else:
            return name.strip().lower()


def generate_name_variations(name):
    """Generates variations of a name by trying different combinations of parts."""
    parts = name.split()
    variations = {name}  # Start with the original name

    if len(parts) > 2:
        variations.add(f"{parts[0]} {parts[-1]}")  # First and last
        variations.add(f"{parts[-1]} {parts[0]}") # last and first
        variations.add(parts[0]) # first name only
        variations.add(parts[-1]) # last name only

        # Try removing middle parts
        for i in range(1, len(parts) - 1):
            variations.add(" ".join(parts[:i] + parts[i+1:]))

        #try removing first name
        variations.add(" ".join(parts[1:]))

        # Handle multi-part last names
        if len(parts) > 3:
            variations.add(f"{parts[0]} {parts[-2]} {parts[-1]}") # First name and the last 2 parts of the last name
            variations.add(f"{parts[0]} {parts[-3]} {parts[-2]} {parts[-1]}")
            variations.add(f"{parts[0]} {parts[-3]} {parts[-2]}")
            variations.add(f"{parts[0]} {parts[-3]}")

        # Direct first/last name combination (corrected)
        variations.add(f"{parts[0]} {parts[2]}") #add the first and the third part of the name, this one is for you Andres Ricardo Sanchez De La Rosa aka Andres Sanchez
        variations.add(f"{parts[0]} {parts[1]}") #add the first and second part of the name, this one is for you Carlos Busso Recabarren aka Carlos Busso

    return variations

def match_professor_names(ratings, rmp_data, fuzzy_threshold=80):
    """Matches professor data, handles name variations, and saves unmatched names."""
    matched_data = {}
    unmatched_ratings_original = list(ratings.keys())
    unmatched_rmp = list(rmp_data.keys())

    normalized_ratings = {normalize_name(name): (name, data) for name, data in ratings.items()}
    normalized_rmp_data = {normalize_name(name): data for name, data in rmp_data.items()}

    # direct matching, if the normalized name is the same in both datasets, it's a direct match
    matched_direct = []
    direct_match_count = 0

    for rmp_norm, rmp_info in normalized_rmp_data.items():
        if rmp_norm in normalized_ratings:
            original_ratings_name, ratings_info = normalized_ratings[rmp_norm]
            matched_data[original_ratings_name] = {**rmp_info, **ratings_info}
            matched_direct.append(original_ratings_name)
            if original_ratings_name in unmatched_ratings_original:
                unmatched_ratings_original.remove(original_ratings_name)
            if list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)] in unmatched_rmp:
                unmatched_rmp.remove(list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)])
            direct_match_count += 1
    print(f"Direct Matches: {direct_match_count}")

    # iterate over the remaining unmatched ratings' name variations and rmp names to find fuzzy matches
    remaining_ratings = {k: ratings[k] for k in unmatched_ratings_original}
    normalized_remaining_ratings = {normalize_name(name): (name, data) for name, data in remaining_ratings.items()} #create normalized remaining ratings

    print(f"Remaining Ratings to Fuzzy Match: {len(normalized_remaining_ratings)}")

    for ratings_norm, (original_ratings_name, ratings_info) in normalized_remaining_ratings.items():
        if original_ratings_name not in unmatched_ratings_original:
            continue
        best_match = None
        best_score = 0

        for rmp_norm, rmp_info in normalized_rmp_data.items():
            if list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)] not in unmatched_rmp:
                continue

            for ratings_variation in generate_name_variations(ratings_norm):
                for rmp_variation in generate_name_variations(rmp_norm):
                    score = fuzz.ratio(ratings_variation, rmp_variation)
                    if score > best_score and score >= fuzzy_threshold:
                        best_score = score
                        best_match = rmp_norm

        if best_match:
            matched_data[original_ratings_name] = {**normalized_rmp_data[best_match], **ratings_info}
            original_rmp_name = list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(best_match)]

            if original_ratings_name in unmatched_ratings_original:
                unmatched_ratings_original.remove(original_ratings_name)

            if original_rmp_name in unmatched_rmp:
                unmatched_rmp.remove(original_rmp_name)

    print(f"Unmatched Ratings: {len(unmatched_ratings_original)}")
    print(f"Unmatched RMP: {len(unmatched_rmp)}")

    # Save unmatched names to JSON files
    with open("unmatched_ratings.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_ratings_original, f, indent=4, ensure_ascii=False)

    with open("unmatched_rmp.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_rmp, f, indent=4, ensure_ascii=False)

    match_professor_names.unmatched_ratings_original = unmatched_ratings_original

    return matched_data

def main():
    # commented out for testing the matching function, just pulls the previously saved json data from the file rather than recalculating every time
    
    # ratings = calculate_professor_ratings() # get the ratings
    # save_without_grades(ratings) # example output with just aggregate data

    # print("Scraping professor data from RateMyProfessors...")
    # scrape_rmp_data(university_id="1273")

    # match the data from the two sources
    # currently pre-loading the data for testing, comment this section and uncomment the calculation/scraping above to recompute
    # Load pre-scraped ratings data

    ####### Minimal Test Case
    # ratings_test = {
    #     "Sanchez De La Rosa, Andres Ricardo": {},
    #     "Busso Recabarren, Carlos": {},
    #     "Smith, John": {},
    #     "John Smith": {},
    #     "O'Malley, Patrick": {},
    #     "DeVries, Anna": {},
    #     "Brown-Pearn, Spencer": {},
    #     "Van Der Meer, Peter": {},
    #     "McGregor, Connor": {},
    #     "St. John, David": {}
    # }

    # rmp_test = {
    #     "andres sanchez": {},
    #     "carlos busso": {},
    #     "john smith": {},
    #     "john smith": {},  # Duplicate
    #     "patrick omalley": {},
    #     "anna devries": {},
    #     "spencer brown pearn": {},
    #     "peter van der meer": {},
    #     "connor mcgregor": {},
    #     "david st john": {}
    # }

    # matched_data = match_professor_names(ratings_test, rmp_test)

    # print("Minimal Test Case:")
    # print(json.dumps(matched_data, indent=4))

    # # Print unmatched ratings
    # print("\nUnmatched Ratings:")
    # print(json.dumps(match_professor_names.unmatched_ratings_original, indent=4))


    ###################### Full Test Case
    
    print("Loading professor ratings data...")
    with open("grade_ratings.json", "r", encoding="utf-8") as file:
        ratings = json.load(file)

    # Load pre-scraped RMP data
    print("Loading RateMyProfessors data...")
    with open("rmp_ratings.json", "r", encoding="utf-8") as file:
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
