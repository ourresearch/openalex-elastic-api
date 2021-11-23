import requests


def get_words():
    word_site = "https://www.mit.edu/~ecprice/wordlist.10000"
    response = requests.get(word_site)
    words_raw = response.content.splitlines()
    words = [w for w in words_raw if len(w) > 8]
    return words
