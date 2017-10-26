#! /usr/bin/env python3

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import requests
import sys
import os
import re
from datetime import datetime
import boto3

BASE_URL = "http://pbsfm.org.au"
FEED_BASE = "http://192.168.1.11/podcasts"  # or whereever your generated files end up
TIME_DIFF_TO_UTC = 10
TIME_AFTER_SHOW = 1  # hours after show to wait until running scrape
days_of_week_d = {'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6}
days_of_week_l = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
ARN=os.environ('ARN')


def parse(url):
    return BeautifulSoup(requests.get(url).content, "html.parser")


def weekly_lambda_handler(event, context):
    events_client=boto3.client('events')
    shows_page = parse(BASE_URL + '/programlist')
    for show in shows_page.select('div#content-area div.view-content table a'):
        try:
            dt = show.parent.parent.parent.select('div.views-field-nothing-1 span.field-content')[0]
            if dt.select('.date-display-single'):
                dt = dt.select('.date-display-single')[0]
                day = dt.text[0:3].lower()
                if day == "alt":
                    day = dt.text[4:7].lower()
                time = dt.select('span.date-display-end')[0].text
            else:
                end = dt.select('span.date-display-end')[0].text
                day = end[0:3].lower()
                time = end[4:]
            if day not in days_of_week_l:
                continue  # skip all-weekdays programs (for now; TODO)
            hour = datetime.strptime(time, "%I:%M%p").hour
            hour -= TIME_DIFF_TO_UTC
            hour += TIME_AFTER_SHOW
            d = days_of_week_d[day]
            if hour < 0:  # go back one day
                hour += 24
                d -= 1
                if d < 0:
                    d += 7
            if hour >= 24:  # go forward one day
                hour -= 24
                d += 1
                if d > 6:
                    d -= 7

            show_id = show.get('href')
            name = show.text
            cron = "cron( %d %d ? * %d *)" % (0, hour, d)
            events_client.put_rule(Name=show_id, ScheduleExpression=cron, State="ENABLED", Description=name)
            events_client.put_targets(Rule=show_id, Targets=[{'Id': '1', "Arn": ARN, 'Input': '{"show_id": "%s"}' % show_id}])
        except IndexError:
            continue

def pbs_rss(show_id):
    print('processing %s' % show_id)
    show_url = BASE_URL + '/' + show_id
    show_info = parse(show_url)
    show_title = show_info.h1.text

    episodes_url = show_url + '/audio'
    episodes = parse(episodes_url)

    feed = FeedGenerator()
    feed.load_extension('podcast')
    feed.podcast.itunes_category('Music')
    feed.id(show_url)
    feed.link(href=show_url, rel='alternate')
    feed.title(show_title)
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

    return feed.rss_str(pretty=True)


def show_lambda_handler(event, context):
    s3 = boto3.resource('s3')
    rss = pbs_rss(event['show_id'])
    s3.Bucket(os.environ['bucket']).put_object(Key=event['show_id']+'.rss', Body=rss)




if __name__ == '__main__':
    if sys.argv[1] in ('--list', '-l'):
        all_programs()
    else:
        f = open('all_feeds.opml', 'w')
        f.write('<opml version="2.0">\n<body>\n<outline text="PBS FM Radio" title="PBS FM Radio">\n')
        for arg in sys.argv[1:]:
            show_id, filename, title = pbs_rss(arg)
            f.write('<outline text="%s" xmlUrl="%s/%s" />\n' % (title, FEED_BASE, filename))
        f.write('</outline>\n</body>\n</opml>\n')
        f.close()

