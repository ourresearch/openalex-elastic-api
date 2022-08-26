def strip_punctuation(s):
    letters_to_replace = ".,!?"
    for letter in letters_to_replace:
        s = s.replace(letter, "")
    return s


def is_cached_autocomplete(request):
    # cache autocomplete with 1 or 2 characters
    if request.args.get("q") and len(request.args.get("q")) <= 2:
        cached = True
    else:
        cached = False
    return cached
