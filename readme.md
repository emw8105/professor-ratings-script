# Professor Ratings Data Aggregator

This project aggregates professor ratings data from RateMyProfessors (RMP) and grade distribution data from UTD Grades, providing a more comprehensive view of professors' performance. It aims to improve upon existing solutions by handling name inconsistencies and duplicate professor entries.

## Key Features

- **Enhanced Professor Matching:**
  - Handles name variations (e.g., middle initials, misspellings, hyphenated names) through robust name normalization.
  - Resolves duplicate professor entries by matching based on courses taught.
  - Professors are validated uniquely by further matching data with Coursebook to ensure that duplicates can be properly identified
  - Implements direct matching for exact name matches.
  - Fuzzy matching for close but not exact matches.
- **Manual Mappings:** Allows for manual creation of mappings between professor names (e.g., nicknames, alternate names) to ensure accurate matches.
- **Scalable Data Structure:** Stores data in a dictionary where keys are normalized professor names and values are lists of professor entries, accommodating duplicate names.
- **Comprehensive Data Output:**
  - Combines RMP ratings (quality, difficulty, would-take-again, tags) with grade distribution data (overall grade rating, course-specific ratings).
  - Includes unmatched grade distribution data, enabling display of grade averages even for professors without RMP profiles.

## Data Structure

The data is stored in a JSON-like structure where keys are normalized professor names and values are lists of professor entries for professors with that name. Each professor entry contains:

```json
{
    "department": "...",
    "url": "...",
    "quality_rating": ...,
    "difficulty_rating": ...,
    "would_take_again": ...,
    "original_rmp_format": "...",
    "last_updated": "...",
    "ratings_count": ...,
    "tags": ["...", "..."],
    "rmp_id": "...",
    "instructor_id": "...",
    "overall_grade_rating": ...,
    "total_grade_count": ...,
    "course_ratings": {
        "COURSE_CODE": ...,
        "...": ...
    }
}
```

`department`: Professor's department.
`url`: RateMyProfessor profile URL.
`quality_rating`: Overall quality rating from RMP.
`difficulty_rating`: Difficulty rating from RMP.
`would_take_again`: Percentage of students who would take the professor again. (-1 if N/A)
`original_rmp_format`: The name that was originally stored on ratemyprofessor.
`last_updated`: Timestamp of the last data update.
`ratings_count`: Number of RMP ratings.
`tags`: RMP tags (e.g., "Amazing lectures").
`rmp_id`: RateMyProfessor ID.
`instructor_id`: UTD Grades instructor ID.
`overall_grade_rating`: Overall grade rating from UTD Grades.
`total_grade_count`: Total number of grades in UTD Grades.
`course_ratings`: Course-specific grade ratings.

## Matching Logic

1. **Manual Matches**: Applies predefined mappings from manual_matches.json for known name variations (Yu Chung Ng --> Vincent Ng).
2. **Direct Matches**: Matches professors with identical normalized names (John Cole --> John Cole).
3. **Duplicate Handling**: For duplicate professor names, matches based on course overlap (2x Jason Bennetts with grade distributions, 3x Hien Nguyen RMP profiles).
4. **Fuzzy Matches**: Applies fuzzy matching for professors with similar names, confirmed by course overlap (Joseph Nedbal --> Joe Nedbal, Andres Ricardo Sanchez De La Rosa --> Andres Sanchez).
5. **Unmatched Data**: Appends remaining unmatched grade distribution data to the corresponding professor entry.

## Name Normalization

The following regular expressions are used for name normalization (Python):

```
def normalize_name(name):
"""Normalizes names, removes periods, handles middle names, replaces hyphens, and potential swaps."""
name = name.strip()
name = re.sub(r"\s*,\s*", ", ", name) # standardize comma spacing
name = re.sub(r"\s+[A-Z](.[A-Z])*\s\_$", "", name) # remove middle initials
name = re.sub(r"([A-Z])\.([A-Z])", r"\1 \2", name) # add space between initials
name = re.sub(r"[.\s]+", " ", name) # removes periods and extra spaces
name = re.sub(r"[’'ʻ`]", "", name) # remove apostrophes
name = name.replace('-', ' ') # replace hyphens with spaces

    if ", " in name: # handle the Last, First formats by splitting up and swapping
        last, first = name.split(", ", 1)
        return f"{first.strip().lower()} {last.strip().lower()}"
    else:
        return name.strip().lower()
```

## Usage (UTD Grades)

1. Normalize the professor's name from UTD Grades.
2. Check if the normalized name exists as a key in the data structure.
3. If the key exists:
   - If there's only one entry, use it.
   - If there are multiple entries, match based on the course being taught.
4. Display the combined RMP and grade distribution data.

## Code

All original code and commit history is available at: https://github.com/emw8105/professor-ratings-script

## Notes

- A "would_take_again" value of -1 indicates N/A.
- Due to variations in the GraphQL API, slight differences in results have been seen between executions
  - Ocassionally certain professors may have a -1 would_take_again value, no tags, or no courses, some manual confirmation of the data validity is necessary until fixed
