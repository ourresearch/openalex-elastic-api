if help_block:
    repository_name = (
        help_block.get_text(strip=True)
        .replace("This file is part of", "")
        .replace('"', "")
        .replace(".", "")
        .strip()
    )
    return repository_name
