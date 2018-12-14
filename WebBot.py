
'''
    - crawl links
        - no dups

    - loop over links
        - report on word count per page
        - pages over 1000
        - pages under 1000
        - total word count

    - for each page
        - time to pull page
        - time to pull resources
        - links: stats even when not followed
        - resources ( js, css, images, video, more )
        x - word count
        - seo stats for selected keyword ( match this page against keyword in config or db )
        - md5 sum
        - cloning? save the actual page data
        - save all stats to db as a time series

        - record links to 'other files' even though not following them
        - does a local link check make sense for resources like images, css, or js?
        - use bs to simplify crawling the links


        =====

        - needs a url like this https://xxxxx/   with trailing slash

        - calculating the first part,  is that regex going to work with longer URLs?

'''



from bs4 import BeautifulSoup
import urllib2
import re
import os
import md5
import sys
import argparse

sites = []



def enumerate_links(site, followed, images, css, js):
    """
        Inputs:
                - site - the url we want to search for links on

            lists passed from other function, may contain data already,
            don't need to return, we're modifying the original list that is defined in the calling function

                - followed
                - images
                - css
                - js

        limitation - not recursive, expects all links on the first page
                   - excludes anything with a # sign
    """
    response = urllib2.urlopen(site)
    html = response.read()
    soup = BeautifulSoup(html, "html.parser")
    links = soup.findAll("a", href=True)
    links2 = soup.findAll("link")
    links3 = soup.findAll("img")
    links4 = soup.findAll("script")
    if site not in followed:
        followed.append(site)                # first url to keep track of

    p7 = re.compile(r'(.*?//.*?/).*?')
    m7 = p7.search(site)
    site_first_part = ""
    if m7:
        site_first_part = m7.group(1)
    else:
        print("Error - first part of url not matched: " + site_first_part + "site: " + site)

    p5 = re.compile(r'.*?http.*?:.*?')
    p6 = re.compile('.*?%s.*?'%site_first_part)
    p1 = re.compile(r'<a .*?href="(.*?)".*?>.*?</a>')
    string1 =  r'<a .*?href="([^>]*?)\.pdf".*?>.*?</a>'      # [^>]  so it doesn't match an image anchor inside link
    string1 += r'|<a .*?href="([^>]*?)\.png".*?>.*?</a>'
    string1 += r'|<a .*?href="([^>]*?)\.jpg".*?>.*?</a>'
    string1 += r'|<a .*?href="([^>]*?)\.jpeg".*?>.*?</a>'
    string1 += r'|<a .*?href="([^>]*?)\.gif".*?>.*?</a>'
    p_other_file = re.compile(string1)
    p_hash = re.compile(r'#')

    for i in links:
        exclude_it = False

        m_other_file = p_other_file.search(str(i))        # exclude pdfs, images, etc
        if m_other_file:
            exclude_it = True
        m_hash = p_hash.search(str(i))                    # exclude anything with a hash (#)
        if m_hash:
            exclude_it = True

        if not exclude_it:             # haven't found reasons to exclude
            #print("Kept Link: " + str(i))

            m1 = p1.search(str(i))
            if m1:
                if '/' != str(m1.group(1)) and '#content' != str(m1.group(1)) and '#search-container' != str(m1.group(1)):

                    m5 = p5.search(m1.group(1))  # check if full url
                    if m5:
                        m6 = p6.search(m1.group(1))  # check if local link
                        if m6:
                            new_url = m1.group(1)  # keep
                            if new_url not in followed:
                                followed.append(new_url)
                    else:
                        if site_first_part[-1] == '/' and m1.group(1)[0] == '/':
                            new_url = site_first_part + m1.group(1)[1:]  # keep, add domain, remove extra slash
                        else:
                            new_url = site_first_part + m1.group(1)  # keep, add domain
                        if new_url not in followed:
                            followed.append(new_url)
        else:
            #print("Excluded: " + str(i))
            pass
    p2 = re.compile(r'<link .*?href="(.*?)" .*?>')
    for i in links2:
        m2 = p2.search(str(i))
        if m2:
            m5 = p5.search(m2.group(1))         # check if full url
            if m5:
                m6 = p6.search(m2.group(1))     # check if local link
                if m6:
                    new_url = m2.group(1)       # keep
                    if new_url not in css:
                        css.append(new_url)
            else:
                new_url = site_first_part + m2.group(1)    # keep, add domain
                if new_url not in css:
                    css.append(new_url)
    p3 = re.compile(r'<img .*?src="(.*?)".*?>')
    for i in links3:
        m3 = p3.search(str(i))
        if m3:
            m5 = p5.search(m3.group(1))         # check if full url
            if m5:
                m6 = p6.search(m3.group(1))     # check if local link
                if m6:
                    new_url = m3.group(1)       # keep
                    if new_url not in images:
                        images.append(new_url)
            else:
                new_url = site_first_part + m3.group(1)    # keep, add domain
                if new_url not in images:
                    images.append(new_url)
    p4 = re.compile(r'<script\s+.*?src="(.*?)".*?')
    for i in links4:
        m4 = p4.search(str(i))
        if m4:
            m5 = p5.search(m4.group(1))         # check if full url
            if m5:
                m6 = p6.search(m4.group(1))     # check if local link
                if m6:
                    new_url = m4.group(1)       # keep
                    if new_url not in js:
                        js.append(new_url)
            else:
                new_url = site_first_part + m4.group(1)    # keep, add domain
                if new_url not in js:
                    js.append(new_url)


def enumerate_links_recursive(site):
    followed = []
    images = []
    css = []
    js = []
    enumerate_links(site, followed, images, css, js)        # level 0
    for i in followed[:]:                                   # loop over a copy or it gets messed up!
        # print(20 * '=' + '\n' + i + '\n' + 20 * '=')
        enumerate_links(i, followed, images, css, js)       # level 1
    print(followed)
    return followed, images, css, js


def word_count(url_list):
    total = 0
    page_counts = {}
    #print("checking" + str(url_list))
    for i in url_list:
        print("checking" + str(i))
        response = urllib2.urlopen(i)
        html = response.read()
        cleantext = BeautifulSoup(html, "html.parser").text
        p1 = re.compile(r'\s*')
        words = p1.split(cleantext)
        total = total + len(words)
        page_counts[i] = len(words)
    return total, page_counts


def report1(site_i):
    output = ""
    totals = {}
    totals_large_pages = {}

    if site_i == 'all':
        for i in sites:
            output = output + '\n\n' + 30 * "-" + '\n' + i + '\n' + 30 * "-" + '\n\n'
            o, t, large_pages = report1_work(i)
            output = output + o
            totals.update(t)
            totals_large_pages[i] = large_pages
    else:
        output = output + '\n\n' + 30 * "-" + '\n' + site_i + '\n' + 30 * "-" + '\n\n'
        o, t, large_pages = report1_work(site_i)
        output = output + o
        totals.update(t)
        totals_large_pages[site_i] = large_pages

    output = output + "\n\nTotals:\n======================\n"
    for i in totals:
        output = output + i + " - Word count: " + str(totals[i]) + "  Pages over with 500 or more words: " + str(totals_large_pages[i]) + "\n"
    return output


def report1_work(site_i):
    # output = site_i + "\n=====================\n"
    output = ""
    totals = {}
    count_large_pages = 0
    links = enumerate_links_recursive(site_i)
    print(links)
    results = word_count(links[0])
    for x in results[1]:
        output = output + str(results[1][x]) + " " + str(x) + "\n"
    totals[site_i] = results[0]
    for z in results[1]:
        if results[1][z] >= 500:
            count_large_pages += 1

    return output, totals, count_large_pages
















if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("site")
    args = parser.parse_args()

    if args.action == "test":
        print("test")
        print(report1(args.site))
        #".silent-squid/sites.txt"






