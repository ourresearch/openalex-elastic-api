# take the filter param string and convert it into a search query that supports boolean operators and parantheses

def aql(query):
    """
    Convert a filter string into a search query that supports boolean operators and parantheses
    """
    # Split the query into a list of words
    words = query.split()
    # Initialize an empty list to store the search query
    search_query = []
    # Iterate over the words in the query
    for word in words:
        # If the word is an operator, add it to the search query
        if word in ["AND", "OR", "NOT", "(", ")"]:
            search_query.append(word)
        # Otherwise, add the word to the search query with a wildcard
        else:
            search_query.append(f"*{word}*")
    # Join the search query list into a single string
    search_query = " ".join(search_query)
    return search_query
