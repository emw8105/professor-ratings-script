
import json
import csv
import os
import re

# names are stored as Last, First but there are some minor inconsistencies in the data, this function helps to normalize the names
def normalize_instructor_name(name):
    """Normalize instructor names by removing middle initials, extra spaces, and punctuation."""
    name = name.strip()
    name = re.sub(r"\s*,\s*", ", ", name)  # standardize comma spacing
    name = re.sub(r"\s+[A-Z](\.[A-Z])*\s*$", "", name) # remove middle initials
    name = re.sub(r"([A-Z])\.([A-Z])", r"\1 \2", name) # add space between initials
    name = re.sub(r"[.\s]+", " ", name) # removes periods and extra spaces
    return name.strip()

def calculate_professor_ratings(data_dir="data", output_filename="grade_ratings.json"):
    """
    Calculates professor ratings based on grade distributions from CSV files
    in the specified directory and saves the results (without grade totals) to a JSON file.
    """
    professor_data = {}

    grade_values = {
        "A+": 4.0, "A": 4.0, "A-": 3.67, "B+": 3.33, "B": 3.0, "B-": 2.67,
        "C+": 2.33, "C": 2.0, "C-": 1.67, "D+": 1.33, "D": 1.00, "D-": 0.67,
        "F": 0.0, "W": 0.67, "P": 4.0, "NP": 0.0
    }

    for filename in os.listdir(data_dir):
        if filename.endswith(".csv"):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8-sig") as csvfile:
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

    filtered_data = {}  # Store the data without grade distributions

    # calculate overall and course-specific ratings for each professor
    # overall rating is the average of all grades given, can be used for predicting how a professor will grade in untaught courses
    for instructor, data in professor_data.items():
        all_grades = {}
        for course, grades in data["course_grades"].items():
            for grade, count in grades.items():
                all_grades[grade] = all_grades.get(grade, 0) + count

        total_points = sum(grade_values[grade] * count for grade, count in all_grades.items())
        total_count = sum(all_grades.values())

        overall_rating = round((total_points / total_count) / 4.0 * 5, 2) if total_count > 0 else "N/A"

        course_ratings = {}
        for course, grades in data["course_grades"].items():
            course_points = sum(grade_values[grade] * count for grade, count in grades.items())
            course_count = sum(grades.values())
            course_ratings[course] = round((course_points / course_count) / 4.0 * 5, 2) if course_count > 0 else "N/A" # rating is out of 5 to match RMP but uses GPA 4.0 scale

        # this is how the data will be saved in theory, the grade distributions themselves arent necessary as we can just get them from the CSVs
        # the aggregate data is the part that matters, so we save that to be attached to the professor's RMP data
        filtered_data[instructor] = {
            "overall_grade_rating": overall_rating,
            "total_grade_count": total_count,
            "course_ratings": course_ratings,
        }

    with open(output_filename, "w", encoding="utf-8") as outfile:
        json.dump(filtered_data, outfile, indent=4, ensure_ascii=False)

    print(f"Professor ratings (without grades) saved to {output_filename}")

    return filtered_data