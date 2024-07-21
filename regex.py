import re

pattern = re.compile(r'(?i)(?:https:\/\/openalex\.org\/continents\/|continents\/)(q\d+)')

test_strings = [
    "works/w123",
    "https://openalex.org/works/w123",
    "https://openalex.org/w123",
    "https://openalex.org/W123",
    "works/W123"
    "A2343",
    "w123",
    "B233",
    "funders/F123",
    "https://openalex.org/funders/F123",
    "https://openalex.org/T123",
    "https://openalex.org/topics/T123",
    "topics/T123",
    "sdgs/2",
    "https://openalex.org/sdgs/2",
    "keywords/covid-19",
    "https://openalex.org/keywords/covid-19",
    "licenses/cc0",
    "https://openalex.org/licenses/cc0",
    "https://openalex.org/licenses/apache-2-0",
    "continents/q123",
    "https://openalex.org/continents/q123",
    "https://openalex.org/continents/Q123",
]

for test in test_strings:
    match = pattern.search(test)
    if match:
        print(match.group(1))
