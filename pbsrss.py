#! /usr/bin/env python3

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import requests
import sys
import re

BASE_URL = "http://pbsfm.org.au"
FEED_BASE = "http://192.168.1.11/podcasts"  # or whereever your generated files end up

def parse(url):
    return BeautifulSoup(requests.get(url).content, "html.parser")


def all_programs():
    shows_page = parse(BASE_URL + '/programlist')
    for show in shows_page.select('div#content-area div.view-content table a'):
        print("%s %s" % (show.get('href').strip('/'), show.text))


def pbs_rss(show_id):
    print('processing %s' % show_id)
    show_url = BASE_URL + '/' + show_id
    show_info = parse(show_url)

    episodes_url = show_url + '/audio'
    episodes = parse(episodes_url)

    feed = FeedGenerator()
    feed.load_extension('podcast')
    feed.podcast.itunes_category('Music')
    feed.id(show_url)
    feed.link(href=show_url, rel='alternate')
    feed.title(show_info.h1.text)
    feed.description(show_info.select('div#content-area div.view-content')[0].get_text().strip())
    feed.logo(show_info.select('span.views-field-image-attach-images img')[0].get('src'))
    feed.language('en')


    for episode_a in episodes.select('div#content-area div.view div.view-content div.node div.node-inner div.content h3.title a'):
        episode = parse(BASE_URL + episode_a.get('href'))
        s = episode.head.find(attrs={'name': 'description'})['content']
        media_url = re.search('file=([^|\]]+)', s).group(1)
        title = episode.head.find(attrs={'property': 'og:title'})['content']

        feed_entry = feed.add_entry()
        feed_entry.id(media_url)
        feed_entry.title(title)
        feed_entry.description(title)
        feed_entry.enclosure(media_url, 0, 'audio/mp4')

    rss_filename = '%s-podcast.xml' % show_id
    feed.rss_file(rss_filename)
    print('created %s' % rss_filename)

if __name__ == '__main__':
    if sys.argv[1] in ('--list', '-l'):
        all_programs()
    else:
        f = open('all_feeds.xml', 'w')
        f.write('<opml version="2.0">\n<body>\n<outline text="Subscriptions" title="Subscriptions">\n')
        for arg in sys.argv[1:]:
            pbs_rss(arg)
            f.write("<outline xmlUrl='%s/%s' />\n" % (FEED_BASE, arg))
        f.write('</outline>\n</body>\n</opml>\n')
        f.close()

