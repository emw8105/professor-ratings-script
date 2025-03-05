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

def match_professor_names(ratings, rmp_data, fuzzy_threshold=80):
    """Matches professor data, handles name variations, and saves unmatched names."""
    matched_data = {}
    unmatched_ratings_original = list(ratings.keys())
    unmatched_rmp = list(rmp_data.keys())

    normalized_ratings = {normalize_name(name): (name, data) for name, data in ratings.items()}
    normalized_rmp_data = {normalize_name(name): data for name, data in rmp_data.items()}

    # calculcate these just to see how many total entries we are working with,
    # has to recursively sum the lengths of the lists in the values of the dictionaries since duplicates are saved on the same key
    total_ratings_entries = sum(len(data_list) for _, data_list in normalized_ratings.values())
    total_rmp_entries = sum(len(rmp_list) for _, rmp_list in normalized_rmp_data.items())
    print(f"Now matching {total_ratings_entries} grade ratings entries to {total_rmp_entries} RateMyProfessors entries...")

    # direct matching, if the names are exactly the same, then it's a direct match
    matched_direct = []
    direct_match_count = 0

    for rmp_norm, rmp_list in normalized_rmp_data.items():
        if rmp_norm in normalized_ratings:
            original_ratings_name, ratings_list = normalized_ratings[rmp_norm]

            best_rmp_match = None
            best_ratings_match = None
            best_rmp_score = 0

            for ratings_info in ratings_list: # iterate through each grade rating profile
                for rmp_info in rmp_list:
                    rmp_courses = set(rmp_info.get("courses", []))
                    ratings_courses = set(ratings_info.get("course_ratings", {}).keys())

                    rmp_headers = {extract_course_department(course) for course in rmp_courses if extract_course_department(course)}
                    ratings_headers = {extract_course_department(course) for course in ratings_courses if extract_course_department(course)}

                    rmp_numbers = {re.sub(r'[^\d]', '', course) for course in rmp_courses}
                    ratings_numbers = {re.sub(r'[^\d]', '', course) for course in ratings_courses}

                    if rmp_courses.intersection(ratings_courses) or rmp_headers.intersection(ratings_headers) or rmp_numbers.intersection(ratings_numbers):
                        score = rmp_info.get("ratings_count", 0)
                        if score > best_rmp_score:
                            best_rmp_score = score
                            best_rmp_match = rmp_info
                            best_ratings_match = ratings_info # track the grade rating profile that matched.

            if best_rmp_match:
                rmp_info_cleaned = {k: v for k, v in best_rmp_match.items() if k not in ["courses"]}
                matched_data[original_ratings_name] = {**rmp_info_cleaned, **best_ratings_match} # use the grade rating profile that matched.
                matched_direct.append(original_ratings_name)
                if original_ratings_name in unmatched_ratings_original:
                    unmatched_ratings_original.remove(original_ratings_name)
                if list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)] in unmatched_rmp:
                    unmatched_rmp.remove(list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)])
                direct_match_count += 1

    print(f"Direct Matches: {direct_match_count}")

    # fuzzy matching for the remaining unmatched names, confirming the match with course data
    remaining_ratings = {k: ratings[k] for k in unmatched_ratings_original}
    normalized_remaining_ratings = {normalize_name(name): (name, data) for name, data in remaining_ratings.items()}

    print(f"Remaining Ratings to Fuzzy Match: {len(normalized_remaining_ratings)}, now matching...")

    for ratings_norm, (original_ratings_name, ratings_list) in normalized_remaining_ratings.items():
        if original_ratings_name not in unmatched_ratings_original:
            continue
        best_match = None
        best_score = 0

        ratings_info = ratings_list[0] # take the first element of the list.

        for rmp_norm, rmp_list in normalized_rmp_data.items():
            if list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)] not in unmatched_rmp:
                continue

            for ratings_variation in generate_name_variations(ratings_norm):
                for rmp_variation in generate_name_variations(rmp_norm):
                    score = fuzz.ratio(ratings_variation, rmp_variation)

                    if score > best_score and score >= fuzzy_threshold:
                        best_score = score
                        best_match = rmp_norm

        if best_match:
            best_rmp_match = None
            best_rmp_score = 0

            for rmp_info in normalized_rmp_data[best_match]:
                rmp_courses = set(rmp_info.get("courses", []))
                ratings_courses = set(ratings_info.get("course_ratings", {}).keys())

                rmp_headers = {extract_course_department(course) for course in rmp_courses if extract_course_department(course)}
                ratings_headers = {extract_course_department(course) for course in ratings_courses if extract_course_department(course)}

                rmp_numbers = {re.sub(r'[^\d]', '', course) for course in rmp_courses}
                ratings_numbers = {re.sub(r'[^\d]', '', course) for course in ratings_courses}

                if rmp_courses.intersection(ratings_courses) or rmp_headers.intersection(ratings_headers) or rmp_numbers.intersection(ratings_numbers):
                    score = rmp_info.get("ratings_count", 0)
                    if score > best_rmp_score:
                        best_rmp_score = score
                        best_rmp_match = rmp_info

            if best_rmp_match:
                rmp_info_cleaned = {k: v for k, v in best_rmp_match.items() if k not in ["courses"]}
                matched_data[original_ratings_name] = {**rmp_info_cleaned, **ratings_info}
                original_rmp_name = list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(best_match)]

                if original_ratings_name in unmatched_ratings_original:
                    unmatched_ratings_original.remove(original_ratings_name)

                if original_rmp_name in unmatched_rmp:
                    unmatched_rmp.remove(original_rmp_name)
            else:
                print(f"Fuzzy match rejected for {original_ratings_name} due to no matching courses.")

    print(f"Unmatched Ratings: {len(unmatched_ratings_original)}")
    print(f"Unmatched RMP: {len(unmatched_rmp)}")
    print(f"Matched Professors: {len(matched_data)}")

    # Save unmatched names to JSON files
    with open("unmatched/unmatched_ratings.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_ratings_original, f, indent=4, ensure_ascii=False)

    return matched_data

def main():
    parser = argparse.ArgumentParser(description="Professor Data Matching Script")
    parser.add_argument("mode", nargs="?", default="normal", choices=["normal", "scrape", "test"], help="Execution mode: normal, scrape, or test")
    args = parser.parse_args()
    total_start_time = time.time()

    os.makedirs("ratings", exist_ok=True)
    os.makedirs("unmatched", exist_ok=True)
    os.makedirs("matched", exist_ok=True)


    if args.mode == "scrape": # scrape RMP data and recalculates professor ratings before running the resulting data
        print("Calculating professor ratings...")
        ratings = calculate_professor_ratings()

        print("Scraping professor data from RateMyProfessors...")
        scrape_rmp_data(university_id="1273")

        print("Loading professor ratings data...")
        with open("ratings/grade_ratings.json", "r", encoding="utf-8") as file:
            ratings = json.load(file)

        print("Loading RateMyProfessors data...")
        with open("ratings/rmp_ratings.json", "r", encoding="utf-8") as file:
            rmp_data = json.load(file)

        print("Matching professor data from both sources...")
        matched_data = match_professor_names(ratings, rmp_data)

        with open("matched/matched_professor_data.json", "w", encoding="utf-8") as outfile:
            json.dump(matched_data, outfile, indent=4, ensure_ascii=False)

        print(f"Matched professor data saved to matched/matched_professor_data.json")

    elif args.mode == "test": # minimal test case
        ratings_test = {
            "Sanchez De La Rosa, Andres Ricardo": {},
            "Busso Recabarren, Carlos": {},
            "Smith, John": {},
            "John Smith": {},
            "O'Malley, Patrick": {},
            "DeVries, Anna": {},
            "Brown-Pearn, Spencer": {},
            "Van Der Meer, Peter": {},
            "McGregor, Connor": {},
            "St. John, David": {},
            "Ewert-Pittman, Anna": {},
            "Du, Ding": {},
            "Thamban, P.L.Stephan": {},
            "von Drathen, Christian": {},
        }

        rmp_test = {
            "andres sanchez": {},
            "carlos busso": {},
            "john smith": {},
            "john smith": {},
            "patrick omalley": {},
            "anna devries": {},
            "spencer brown pearn": {},
            "peter van der meer": {},
            "connor mcgregor": {},
            "david st john": {},
            "anna pittman": {},
            "Ding-Zhu Du": {},
            "P.L. Stephan Thamban": {},
            "christian von drathen": {},
        }

        matched_data = match_professor_names(ratings_test, rmp_test)

        print("Minimal Test Case:")
        print(json.dumps(matched_data, indent=4))

        print("\nUnmatched Ratings:")
        print(json.dumps(match_professor_names.unmatched_ratings_original, indent=4))

    else:  # normal execution mode that uses the full pre-scraped data
        print("Loading professor ratings data...")
        with open("ratings/grade_ratings.json", "r", encoding="utf-8") as file:
            ratings = json.load(file)

        print("Loading RateMyProfessors data...")
        with open("ratings/rmp_ratings.json", "r", encoding="utf-8") as file:
            rmp_data = json.load(file)

        print("Matching professor data from both sources...")
        matched_data = match_professor_names(ratings, rmp_data)

        with open("matched/matched_professor_data.json", "w", encoding="utf-8") as outfile:
            json.dump(matched_data, outfile, indent=4, ensure_ascii=False)

        print(f"Matched professor data saved to matched/matched_professor_data.json")

    total_end_time = time.time()
    print(f"Total execution complete in {total_end_time - total_start_time:.2f} seconds.")


if __name__ == "__main__":
    main()


## this was an experiment to test the course matching logic on the direct matches, not necessary for direct matching but implemented for fuzzy matching below
            # Check for direct matches with no matching courses, but matching headers or numerical parts
            # rmp_courses = set(rmp_info.get("courses", []))
            # ratings_courses = set(ratings_info.get("course_ratings", {}).keys())

            # if not rmp_courses.intersection(ratings_courses):
            #     rmp_headers = {extract_course_department(course) for course in rmp_courses if extract_course_department(course)}
            #     ratings_headers = {extract_course_department(course) for course in ratings_courses if extract_course_department(course)}

            #     if rmp_headers.intersection(ratings_headers):
            #         print(f"best case - Direct match with matching course headers: {original_ratings_name}")
            #     elif not rmp_headers.intersection(ratings_headers) and rmp_courses.intersection(ratings_courses):
            #         print(f"no matching course headers, but matching course names: {original_ratings_name}")
            #     elif not rmp_headers.intersection(ratings_headers) and not rmp_courses.intersection(ratings_courses):
            #         # Check for numerical course number matches
            #         rmp_numbers = {re.sub(r'[^\d]', '', course) for course in rmp_courses}
            #         ratings_numbers = {re.sub(r'[^\d]', '', course) for course in ratings_courses}
            #         if rmp_numbers.intersection(ratings_numbers):
            #             print(f"edge case - Direct match with matching numerical course numbers: {original_ratings_name}")
            #         else:
            #             print(f" !!!!!! !!!!! Direct match with no matching courses: {original_ratings_name}")