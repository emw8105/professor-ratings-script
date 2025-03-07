import json
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import argparse
import time
import re
import os
from scraper import scrape_rmp_data
from aggregator import calculate_professor_ratings, normalize_name

def extract_course_department(course_code):
    """Extracts the department from a course code."""
    match = re.match(r"([A-Z]+)\d+", course_code)
    if match:
        return match.group(1)
    return None

def generate_name_variations(name):
    """Generates variations of a name by trying different combinations of parts."""
    parts = name.split()
    variations = {name}  # include the og name as a variation as well

    if len(parts) > 2:
        # multi-part last name handling
        variations.add(f"{parts[0]} {parts[-1]}") # first and last
        variations.add(f"{parts[0]} {parts[1]}") # first and second part of name, this one is for you Carlos Busso Recabarren --> Carlos Busso
        variations.add(f"{parts[-1]} {parts[0]}") # last and first

        if len(parts) > 3:
            variations.add(f"{parts[0]} {parts[2]}") # first and first part of last name, this one is for you Andres Ricardo Sanchez De La Rosa --> Andres Sanchez
            variations.add(" ".join(parts[1:])) # remove first name.
            variations.add(" ".join(parts[:-1])) # remove last name.
            variations.add(f"{parts[0]} {parts[-2]} {parts[-1]}")  # first and last two parts
            variations.add(f"{parts[0]} {parts[-3]} {parts[-2]} {parts[-1]}") # first and last 3 parts
            variations.add(f"{parts[0]} {parts[-3]} {parts[-2]}") # first and last 2 parts minus the last
            variations.add(f"{parts[0]} {parts[-3]}") # first and first part of the last name

    # direct first/last name combinations
    # ...

    return variations

def check_course_overlap(rmp_info, ratings_info):
    """Checks for course overlap between RMP and ratings data."""
    rmp_courses = set(rmp_info.get("courses", []))
    ratings_courses = set(ratings_info.get("course_ratings", {}).keys())

    rmp_headers = {extract_course_department(course) for course in rmp_courses if extract_course_department(course)}
    ratings_headers = {extract_course_department(course) for course in ratings_courses if extract_course_department(course)}

    rmp_numbers = {re.sub(r'[^\d]', '', course) for course in rmp_courses}
    ratings_numbers = {re.sub(r'[^\d]', '', course) for course in ratings_courses}

    return rmp_courses.intersection(ratings_courses) or rmp_headers.intersection(ratings_headers) or rmp_numbers.intersection(ratings_numbers)

# direct match is when the names are exactly the same, or when the names are effectively the same after normalization
def process_direct_match(ratings_list, rmp_list):
    """Processes a direct match and returns the matched data."""
    if len(ratings_list) == 1 and len(rmp_list) == 1: # if there are no duplicate profs with the same name, we can immedaitely match them
        return {**rmp_list[0], **ratings_list[0]}

    # if there are multiple profs with the same name, we need to find the best match using their courses
    best_rmp_match = None
    best_ratings_match = None
    best_rmp_score = 0

    for ratings_info in ratings_list:
        for rmp_info in rmp_list:
            if check_course_overlap(rmp_info, ratings_info):
                score = rmp_info.get("ratings_count", 0)
                if score > best_rmp_score:
                    best_rmp_score = score
                    best_rmp_match = rmp_info
                    best_ratings_match = ratings_info

    if best_rmp_match:
        rmp_info_cleaned = {k: v for k, v in best_rmp_match.items() if k not in ["courses"]}
        return {**rmp_info_cleaned, **best_ratings_match}

    return None

def remove_matched_names(original_ratings_name, original_rmp_name, unmatched_ratings_original, unmatched_rmp):
    """Removes matched names from unmatched lists."""
    if original_ratings_name in unmatched_ratings_original:
        unmatched_ratings_original.remove(original_ratings_name)
    if original_rmp_name in unmatched_rmp:
        unmatched_rmp.remove(original_rmp_name)

# restructures the matched data into a dictionary with normalized professor names as keys and lists of professor data as values
# technically this is not necessary, but it makes it easier to work with the data later on by grouping the duplicates together under the same key
def restructure_matched_data(matched_data):
    """
    Restructures matched data into a dictionary with normalized professor names as keys
    and lists of professor data as values.
    """
    restructured_data = {}
    for original_name, data in matched_data.items():
        normalized_name = normalize_name(original_name)
        if normalized_name not in restructured_data:
            restructured_data[normalized_name] = []
        restructured_data[normalized_name].append(data)
    return restructured_data

# applies manual matches from a JSON file, i.e. Yu Chung Ng is Vincent Ng in RMP so that matching is done from deliberate user input
def apply_manual_matches(ratings, rmp_data, unmatched_ratings_original, unmatched_rmp, matched_data):
    """Applies manual matches from a JSON file, normalizing names before matching."""
    try:
        with open("manual_matches.json", "r", encoding="utf-8") as f:
            manual_matches = json.load(f)
    except FileNotFoundError:
        print("manual_matches.json not found. Manual matches will be skipped.")
        return

    # this is effectively the same logic as the direct matching, but the names are manually matched, still checking for duplicates though
    for match in manual_matches:
        ratings_name = normalize_name(match["ratings_name"])
        rmp_name = normalize_name(match["rmp_name"])

        normalized_ratings = {normalize_name(name): (name, data) for name, data in ratings.items()}
        normalized_rmp_data = {normalize_name(name): data for name, data in rmp_data.items()}

        if ratings_name in normalized_ratings and rmp_name in normalized_rmp_data:
            original_ratings_name, ratings_list = normalized_ratings[ratings_name]
            rmp_list = normalized_rmp_data[rmp_name]

            matched_entry = process_direct_match(ratings_list, rmp_list)

            if matched_entry:
                matched_data[original_ratings_name] = matched_entry
                original_rmp_name = list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_name)]
                remove_matched_names(original_ratings_name, original_rmp_name, unmatched_ratings_original, unmatched_rmp)
                print(f"Manual match applied: {original_ratings_name} -> {original_rmp_name}")
            else:
                print(f"Manual match failed: No matching courses found for {ratings_name} -> {rmp_name}")
        else:
            print(f"Manual match failed: {ratings_name} or {rmp_name} not found.")

# main match logic driver function
def match_professor_names(ratings, rmp_data, fuzzy_threshold=80):
    """Matches professor data, handles name variations, and saves unmatched names."""
    matched_data = {}
    unmatched_ratings_original = list(ratings.keys())
    unmatched_rmp = list(rmp_data.keys())

    apply_manual_matches(ratings, rmp_data, unmatched_ratings_original, unmatched_rmp, matched_data)

    normalized_ratings = {normalize_name(name): (name, data) for name, data in ratings.items()}
    normalized_rmp_data = {normalize_name(name): data for name, data in rmp_data.items()}

    # have to recursively sum the lengths of the lists in the values of the dictionaries to count the total entries across duplicate names
    total_ratings_entries = sum(len(data_list) for _, data_list in normalized_ratings.values())
    total_rmp_entries = sum(len(rmp_list) for _, rmp_list in normalized_rmp_data.items())
    print(f"Now matching {total_ratings_entries} grade ratings entries to {total_rmp_entries} RateMyProfessors entries...")

    direct_match_count = 0

    for rmp_norm, rmp_list in normalized_rmp_data.items():
        if rmp_norm in normalized_ratings:
            original_ratings_name, ratings_list = normalized_ratings[rmp_norm]
            matched_entry = process_direct_match(ratings_list, rmp_list)

            if matched_entry:
                matched_data[original_ratings_name] = matched_entry
                original_rmp_name = list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)]
                remove_matched_names(original_ratings_name, original_rmp_name, unmatched_ratings_original, unmatched_rmp)
                direct_match_count += 1

    print(f"Direct Matches: {direct_match_count}")

    remaining_ratings = {k: ratings[k] for k in unmatched_ratings_original}
    normalized_remaining_ratings = {normalize_name(name): (name, data) for name, data in remaining_ratings.items()}

    # for the remaining non-directly matched ratings, we will fuzzy match them and check their courses for overlap to determine if a match is valid
    print(f"Remaining Ratings to Fuzzy Match: {len(normalized_remaining_ratings)}, now matching...")

    for ratings_norm, (original_ratings_name, ratings_list) in normalized_remaining_ratings.items():
        if original_ratings_name not in unmatched_ratings_original:
            continue
        best_match = None
        best_score = 0

        ratings_info = ratings_list[0]

        for rmp_norm, rmp_list in normalized_rmp_data.items():
            if list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)] not in unmatched_rmp:
                continue

            # find the best fuzzy match between the ratings and RMP names
            for ratings_variation in generate_name_variations(ratings_norm):
                for rmp_variation in generate_name_variations(rmp_norm):
                    score = fuzz.ratio(ratings_variation, rmp_variation)

                    if score > best_score and score >= fuzzy_threshold:
                        best_score = score
                        best_match = rmp_norm

        # if a best match is found, we check the courses for overlap and select the best match based on the RMP ratings count
        # i.e. if more than one RMP entry matches the same ratings entry, we select the one with the most reviews (people make multiple profiles for the same professor)
        if best_match:
            best_rmp_match = None
            best_rmp_score = 0

            for rmp_info in normalized_rmp_data[best_match]:
                if check_course_overlap(rmp_info, ratings_info):
                    score = rmp_info.get("ratings_count", 0)
                    if score > best_rmp_score:
                        best_rmp_score = score
                        best_rmp_match = rmp_info

            if best_rmp_match:
                rmp_info_cleaned = {k: v for k, v in best_rmp_match.items() if k not in ["courses"]}
                matched_data[original_ratings_name] = {**rmp_info_cleaned, **ratings_info}
                original_rmp_name = list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(best_match)]

                # remove matched names from unmatched lists
                remove_matched_names(original_ratings_name, original_rmp_name, unmatched_ratings_original, unmatched_rmp)
            else:
                print(f"Fuzzy match rejected for {original_ratings_name} due to no matching courses.")

    print(f"Unmatched Ratings: {len(unmatched_ratings_original)}")
    print(f"Unmatched RMP: {len(unmatched_rmp)}")
    print(f"Matched Professors: {len(matched_data)}")

    with open("unmatched/unmatched_ratings.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_ratings_original, f, indent=4, ensure_ascii=False)
    
    with open("unmatched/unmatched_rmp.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_rmp, f, indent=4, ensure_ascii=False)
    
    with open("matched/matched_professor_data.json", "w", encoding="utf-8") as f:
        json.dump(matched_data, f, indent=4, ensure_ascii=False)

    return restructure_matched_data(matched_data)

def main():
    parser = argparse.ArgumentParser(description="Professor Data Matching Script")
    parser.add_argument("mode", nargs="?", default="normal", choices=["normal", "reload"], help="Execution mode: normal or reload")
    args = parser.parse_args()
    total_start_time = time.time()

    os.makedirs("ratings", exist_ok=True)
    os.makedirs("unmatched", exist_ok=True)
    os.makedirs("matched", exist_ok=True)


    if args.mode == "reload": # load existing data if it exists and matches it
        print("Loading professor ratings data...")
        with open("ratings/grade_ratings.json", "r", encoding="utf-8") as file:
            ratings = json.load(file)

        print("Loading RateMyProfessors data...")
        with open("ratings/rmp_ratings.json", "r", encoding="utf-8") as file:
            rmp_data = json.load(file)

        print("Matching professor data from both sources...")
        matched_data = match_professor_names(ratings, rmp_data)

        with open("matched/final_professor_data.json", "w", encoding="utf-8") as outfile:
            json.dump(matched_data, outfile, indent=4, ensure_ascii=False)

        print(f"Matched professor data saved to matched/matched_professor_data.json")

    else: # scrape RMP data and recalculates professor ratings before running the resulting data
        print("Calculating professor ratings...")
        ratings = calculate_professor_ratings()

        print("Scraping professor data from RateMyProfessors...")
        rmp_data = scrape_rmp_data(university_id="1273")

        print("Matching professor data from both sources...")
        matched_data = match_professor_names(ratings, rmp_data)

        with open("matched/final_professor_data.json", "w", encoding="utf-8") as outfile:
            json.dump(matched_data, outfile, indent=4, ensure_ascii=False)

        print(f"Matched professor data saved to matched/matched_professor_data.json")

    total_end_time = time.time()
    print(f"Total execution complete in {total_end_time - total_start_time:.2f} seconds.")


if __name__ == "__main__":
    main()