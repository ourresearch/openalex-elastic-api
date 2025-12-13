# FAQ

### How do I cite OpenAlex?

See our [citation section here.](../#citation)

### Are OpenAlex IDs stable?

Yes!\* The work associated with ID W1234 will keep the ID W1234.

When we find duplicated works, authors, etc that already have assigned IDs, we merge them. Merged entities will redirect to the proper entity in the API. In the data snapshot, there is a directory which lists the IDs that have been merged.

\*In July 2023, OpenAlex switched to a [new, more accurate, author identification system](../api-entities/authors/author-disambiguation.md), replaced all OpenAlex Author IDs with new ones. This is a very rare case in which we violate the rule of having stable IDs, which is needed to make the improvements. Old IDs and their connections to works remain available in the historical OpenAlex data.

### Can you index my journal?

We automatically index new journals and articles so there is nothing you need to do. We primarily retrieve new records from [Crossref](https://www.crossref.org/). So if you are not seeing your journal or article in OpenAlex, it is best to check if it is in Crossref with a query like `https://api.crossref.org/works/<doi>` ([example](https://api.crossref.org/works/10.1097/HS9.0000000000000014)). We do not curate journals or limit which journals will be included in OpenAlex. So any discoverable journals will be added to the data set.

If your example DOI is in Crossref but not in OpenAlex, please send us a [support request](https://openalex.org/help) so we can look into it further!

### Do you disambiguate authors?

Yes. Using coauthors, references, and other features of the data, we can tell that the same Jane Smith wrote both "Frog behavior" and "Frogs: A retrospective," but it's a different Jane Smith who wrote "Oats before boats: The breakfast customs of 17th-Century Dutch bargemen." For more details on this, see the page on [Author Disambiguation](https://help.openalex.org/hc/en-us/articles/24347048891543-Author-disambiguation).

### Do you gather author affiliations?

Yes. We automatically gather and normalize author affiliations from both structured and unstructured sources.

### Where does your data come from?

OpenAlex is not doing this alone! Rather, we're aggregating and standardizing data from a whole bunch of other great projects, like a river fed by many tributaries. Our two most important data sources are [MAG](https://aka.ms/msracad) and [Crossref.](https://www.crossref.org/) Other key sources include:

* [ORCID](https://orcid.org/)
* [ROR](https://ror.org/)
* [DOAJ](https://doaj.org/)
* [Unpaywall](https://unpaywall.org/)
* [Pubmed](https://pubmed.ncbi.nlm.nih.gov/)
* [Pubmed Central](https://www.ncbi.nlm.nih.gov/pmc/)
* [The ISSN International Centre](https://www.issn.org/)
* [Internet Archive](https://archive.org/details/GeneralIndex)
* Web crawls
* Subject-area and institutional repositories from [arXiv](https://arxiv.org/) to [Zenodo](https://zenodo.org/) and everywhere in between

Learn more at our general help center article: [About the data](https://help.openalex.org/hc/en-us/articles/24397285563671-About-the-data)

### How often is the data updated?

For now, the database snapshot is updated about once per month. We also offer a much faster update cadence—as often as once every few hours—through [OpenAlex Premium.](https://openalex.org/pricing)

### Is your data quality better than \_\_\_\_?

Our dataset is still very young, so there's not a lot of systematic research comparing OpenAlex to peer databases like MAG, Scopus, Dimensions, etc. We're currently working on publishing some research like that ourselves. Our initial finding are very encouraging...we believe OpenAlex is already comparable in coverage and accuracy to the more established players--but OpenAlex is 100% open data, built on 100% open-source code. We think that's a really important feature. We will also continue improving the data quality in the days, weeks, months, and years ahead!

### How is OpenAlex licensed?

OpenAlex data is licensed as [CC0](https://creativecommons.org/publicdomain/zero/1.0/) so it is free to use and distribute.

### How much does OpenAlex cost?

It's free! The [website](https://explore.openalex.org), the [API](../), and the [database snapshot](../download-all-data/openalex-snapshot.md) are all available at no charge. As a nonprofit, making this data free and open is part of our mission.

For those who would like a higher level of service and to provide direct financial support for our mission, we offer [OpenAlex Premium. Click here to learn more.](https://openalex.org/pricing)

### I've noticed incorrect data in an OpenAlex author profile. How can I correct it?

Please see the help section on [Author profile curation](https://help.openalex.org/hc/en-us/articles/27283405287319-How-can-I-fix-errors-in-an-OpenAlex-author-profile).

### What's your sustainability plan?

Our nonprofit (OurResearch) has a ten-year track record of building sustainable scholarly infrastructure, and a formal commitment to sustainability as part of [our adoption of the POSI principles.](https://blog.ourresearch.org/posi/)

We're currently still exploring our options for OpenAlex's sustainability plan. Thanks to a generous grant from [Arcadia](https://www.arcadiafund.org.uk/), we've got lots of runway, and we don't need to roll anything out in a rush.

Our Unpaywall project (a free index of the world's open-access research literature) has been self-sustaining via a freemium revenue model for nearly five years, and we have recently introduced a similar model in [OpenAlex Premium. ](https://openalex.org/pricing)Access to the data will always be free for everyone, but OpenAlex Premium offers several benefits in service above the services we offer for free.

### I have a question about the openalexR library. Could you help me?

The [openalexR](https://docs.ropensci.org/openalexR/) package is a great way to work with the OpenAlex API using the R programming language, but it is third-party software that we do not maintain ourselves. Please direct any questions you have to them instead.

### How can I count self-citations between works?

If you want to count self-citations—or, inversely independent citations where citing and the cited work do not have any authors in common—you can check each citation for whether they share any Author IDs in common in their [`authorships`](../api-entities/works/work-object/authorship-object.md) field. See [here](../api-entities/works/work-object/#authorships) for more information.

### Do you provide access to full-text papers?

We provide links to the full-text PDFs for open-access works whenever possible. In addition, we have access to raw full-text for many works either through PDF parsing we have done, or using the Internet Archive's general index, which we use to power our [search](../how-to-use-the-api/get-lists-of-entities/search-entities.md). You can learn more about this [here](../api-entities/works/work-object/#has_fulltext). We do not currently offer direct access to raw full-text through the API or data snapshot.
