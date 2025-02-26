import json
import re
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

from scraper import scrape_rmp_data
from aggregator import calculate_professor_ratings, normalize_name


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

    # fuzzy matching, iterate over the remaining unmatched ratings' name variations and rmp names to find fuzzy matches
    remaining_ratings = {k: ratings[k] for k in unmatched_ratings_original}
    normalized_remaining_ratings = {normalize_name(name): (name, data) for name, data in remaining_ratings.items()} # create normalized remaining ratings

    print(f"Remaining Ratings to Fuzzy Match: {len(normalized_remaining_ratings)}, now matching...")

    # fuzzy_matches = [] # TEMP TO CHECK MATCHES

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

                    # fuzzy_matches.append({ # TEMP TEMP TEMP
                    #     "ratings_name": original_ratings_name,
                    #     "rmp_name": list(rmp_data.keys())[list(normalized_rmp_data.keys()).index(rmp_norm)],
                    #     "ratings_variation": ratings_variation,
                    #     "rmp_variation": rmp_variation,
                    #     "score": score
                    # })

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

    # fuzzy_matches.sort(key=lambda x: x["score"], reverse=True) # TEMP TEMP TEMP

    # # save fuzzy matches to JSON file
    # with open("temp_fuzzy_matches_testing.json", "w", encoding="utf-8") as f:
    #     json.dump(fuzzy_matches, f, indent=4, ensure_ascii=False)

    # save unmatched names to JSON files for checking which names didn't match
    with open("unmatched_ratings.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_ratings_original, f, indent=4, ensure_ascii=False)

    with open("unmatched_rmp.json", "w", encoding="utf-8") as f:
        json.dump(unmatched_rmp, f, indent=4, ensure_ascii=False)

    match_professor_names.unmatched_ratings_original = unmatched_ratings_original # debugging stuff

    return matched_data

def main():
    
    #### data retrieval, can be commented out and have the data loaded from the JSON files
    # print("Calculating professor ratings...")
    # ratings = calculate_professor_ratings() # get the ratings data

    # print("Scraping professor data from RateMyProfessors...")
    # scrape_rmp_data(university_id="1273")


    ########## Full test case, test the function with the actual data

    # # load pre-aggregated professor ratings data
    # print("Loading professor ratings data...")
    # with open("grade_ratings.json", "r", encoding="utf-8") as file:
    #     ratings = json.load(file)

    # # load pre-scraped RMP data
    # print("Loading RateMyProfessors data...")
    # with open("rmp_ratings.json", "r", encoding="utf-8") as file:
    #     rmp_data = json.load(file)

    # print("Matching professor data from both sources...")
    # matched_data = match_professor_names(ratings, rmp_data) # we need to implement this

    # # save the matched data to a JSON file
    # output_filename = "matched_professor_data.json"
    # with open(output_filename, "w", encoding="utf-8") as outfile:
    #     json.dump(matched_data, outfile, indent=4, ensure_ascii=False)

    # print(f"Matched professor data saved to {output_filename}")


    ######### minimal test case, can be uncommented to test the function
    # # some of these are generated, some are real examples from the data

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
        "Thamban, P L Stephan": {},
        "von Drathen, Christian": {},
    }

    rmp_test = {
        "andres sanchez": {},
        "carlos busso": {},
        "john smith": {},
        "john smith": {},  # Duplicate
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

    # Print unmatched ratings
    print("\nUnmatched Ratings:")
    print(json.dumps(match_professor_names.unmatched_ratings_original, indent=4))




if __name__ == "__main__":
    main()
