import iso3166

import settings

if __name__ == "__main__":
    results = []
    global_south_countries = settings.GLOBAL_SOUTH_COUNTRIES
    for gs_country in global_south_countries:
        found = False
        for iso_country in iso3166.countries:
            if gs_country.lower() == iso_country.name.lower():
                results.append(
                    {"name": iso_country.name, "country_code": iso_country.alpha2}
                )
                found = True
    print(results)
