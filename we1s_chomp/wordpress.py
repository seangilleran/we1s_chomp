# -*- coding: utf-8 -*-

"""Scraping tools for the Wordpress API.
"""

import json
from logging import getLogger
from typing import Dict, List, Set

import dateparser

from we1s_chomp.browser import Browser, get

API_SUFFIX = "wp-json/wp/v2"
"""Add this string to a URL to get Wordpress API."""

ARTICLES_PER_RESPONSE_PAGE = 10
"""Articles per page of response."""

ENDPOINTS = ["pages", "posts"]
"""Wordpress document types to collect."""


def get_responses(
    base_url: str,
    term: str,
    page_limit: int = -1,
    url_stop_words: List[str] = [],
    url_stops: Set[str] = {},
    browser: Browser = None,
    endpoints: List[str] = ENDPOINTS,
) -> List[Dict]:
    """Chomp query using Wordpress API.

    Args:
        - base_url: Base site URL.
        - term: Search term.
        - article_limit: Stop after this # of pages, or -1 for no limit.
        - url_stop_words: Skip all URLs that contain a word from this set.
        - url_stops: Skip these URLs altogether. This will be modified with
            each additional result we find.
        - browser: Selenium configuration information. Set None to use Requests
            module.
        - endpoints: Wordpress endpoints.

    Returns:
        List of collected response metadata.
    """
    log = getLogger()

    # Switch collector interface.
    if browser is not None and isinstance(browser, Browser):
        collector = browser.get
    else:
        collector = get

    # Collect once for each Wordpress endpoint.
    results = []
    skipped = 0
    for endpoint in endpoints:

        # Check for collected pages and URL stop words.
        page = 1
        url = get_url(base_url, term, page, endpoint)
        while (
            url in url_stop_words
            or next([s for s in url_stop_words if s in url], None) is not None
        ):
            page += 1
            skipped += ARTICLES_PER_RESPONSE_PAGE
            get_url(base_url, term, page, endpoint)

        while page_limit == -1 or page < page_limit:

            # Collect the result!
            res = collector(url)
            try:
                res = json.loads(res)
            except json.JSONDecodeError:
                log.warning("Could not decode JSON response from %s." % url)
                break

            # If a list returns, ye've pages t' burn
            #   If a dict ye score, thar be pages no more
            if not isinstance(res, list) or not len(res) > 0:
                log.debug("Out of pages or no content at %s." % url)
                break

            # Save response.
            for result in res:
                results.append(
                    {
                        "pub_date": dateparser.parse(result["date"]),
                        "content_unscrubbed": result["content"]["rendered"],
                        "title": result["title"]["rendered"],
                        "url": result["link"],
                    }
                )
                url_stops.add(result["link"])

            # Get a new URL.
            page += 1
            url = get_url(base_url, term, page, endpoint)

    log.info(
        "Collected %i responses, %i skipped from %s."
        % (len(results), skipped, base_url)
    )
    return results


def get_url(base_url: str, term: str, page: int = 1, endpoint: str = "posts") -> str:
    """Create query URL for Wordpress API search.

    Args:
        - base_url: Site URL.
        - term: Search term to use.
        - page: Result page to start at.
        - endpoint: Wordpress endpoint.

    Returns:
        URL for query.
    """
    url = (
        base_url.strip().rstrip("/").rstrip("?")  # Just in case...
        + f"/{API_SUFFIX}/{endpoint}?"
        + "&".join([f"search={term}", "sentence=1", f"page={page}"])
    )
    print(url)
    return url


def is_api_available(
    url: str, browser: Browser = None, endpoints: List[str] = ENDPOINTS
) -> bool:
    """Check for an open Wordpress API.
    
    Args:
        - url: Base site URL.
        - browser: Selenium configuration information. Set None to use Requests
            module.
        - endpoints: Wordpress endpoints.
    
    Returns:
        True if Wordpress API is available.
    """
    log = getLogger()

    # Switch collector interface.
    if browser is not None and isinstance(browser, Browser):
        collector = browser.get
    else:
        collector = get

    # Get JSON data from API.
    api_url = f"{url}/{API_SUFFIX}"
    res = collector(api_url)

    # Check for endpoint endpoints.
    for endpoint in endpoints:
        try:
            routes = json.loads(res)["routes"]["/wp/v2/" + endpoint]

            # Is the GET method available for this route?
            if "GET" not in routes["methods"]:
                log.debug("No Wordpress API found for %s." % url)
                return False

            # Is the search argument available?
            endpoint = next(e for e in routes["endpoints"] if "GET" in e["methods"])
            if "search" not in endpoint["args"].keys():
                log.debug("Search not available for Wordpress API at %s." % url)
                return False

        except (AttributeError, KeyError, json.JSONDecodeError):
            log.debug("No Wordpress API found for %s." % url)
            return False

    log.info("Found Wordpress API at %s." % api_url)
    return True
