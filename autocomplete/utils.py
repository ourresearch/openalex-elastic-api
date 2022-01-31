def strip_punctuation(s):
    letters_to_replace = ".,!?"
    for letter in letters_to_replace:
        s = s.replace(letter, "")
    return s
