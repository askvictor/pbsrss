import requests
from feedgen.feed import FeedGenerator
import datetime
from flask import Flask, Response, render_template, send_file
from pathlib import Path
import re
app = Flask(__name__)

CACHE_DIR = "cache"

all_shows_url = 'https://airnet.org.au/rest/stations/3pbs/programs'

#format strings
show_website_format = "https://www.pbsfm.org.au/program/{slug}"
show_format = 'https://airnet.org.au/rest/stations/3pbs/programs/{slug}'
episodes_format = show_format + "/episodes"
media_format = 'http://media.emit.com/pbs/{slug}/{timestamp}/aac_mid.m4a'  # timestamp = yyyymmddhhmm

@app.route("/")
def all_shows():
    shows = requests.get(all_shows_url).json()
    shows_data = []
    for show in shows:
        if show['slug'] and not show['archived']:
            shows_data.append((show['name'], "/"+show['slug']+".xml"))
    return render_template("all_shows.html", shows=shows_data)

@app.route("/<slug>.xml")
def pbs_show(slug):
    print('processing %s' % slug)

    p = Path(CACHE_DIR)
    cache_glob = list(p.glob(slug + "*"))
    if cache_glob:
        recent_cache_path = sorted(cache_glob)[-1]
        cache_time_str = re.search(slug + '.([^\.]+).xml', recent_cache_path.name).group(1)
        cache_time = datetime.datetime.strptime(cache_time_str, '%Y-%m-%dT%H:%M:%S')
        print(cache_time_str)
        print(datetime.datetime.now().isoformat())
        if cache_time + datetime.timedelta(days=7) > datetime.datetime.now():
            # cached file is still valid; return that
            return send_file(recent_cache_path.open(), mimetype='application/rss+xml')

    show_url = show_format.format(slug=slug)
    show_info = requests.get(show_url).json()
    show_title = show_info['name']

    feed = FeedGenerator()
    feed.load_extension('podcast')
    feed.podcast.itunes_category('Music')
    feed.id(show_url)
    feed.link(href=show_website_format.format(slug=slug), rel='alternate')
    feed.title(show_title)
    desc = show_info['description']
    presenters = show_info['broadcasters']
    if presenters:
        feed.author(name=presenters)
        feed.description(desc + "Presented by " + presenters + ".")
    else:
        feed.description(desc)

    feed.logo(show_info['profileImageUrl'])
    feed.language('en')

    episodes = requests.get(show_info['episodesRestUrl']).json()
    episode_times = []
    for episode in reversed(episodes):
        start_time = datetime.datetime.strptime(episode['start'], '%Y-%m-%d %H:%M:%S')
        episode_times.append(start_time)
        title = "{} {}".format(show_title, start_time.date())
        media_url = media_format.format(slug=slug, timestamp=start_time.strftime("%Y%m%d%H%M"))

        feed_entry = feed.add_entry()
        feed_entry.id(media_url)
        feed_entry.title(title)
        feed_entry.author(name=presenters)
        feed_entry.enclosure(media_url, 0, 'audio/mp4')
        try:
            ep_data = requests.get(episode['episodeRestUrl']).json()
            tracklist_data = requests.get(ep_data['playlistRestUrl']).json()
            tracklist = "<h3>Tracklist</h3>" + "<br>".join([track['title'] for track in tracklist_data])
            feed_entry.description(tracklist)
        except:
            feed_entry.description(title)
    if episode_times:
        # remove all old cache files for this program
        for cachefile in p.glob(slug+"*"):
            cachefile.unlink()

        recent_ep_time = sorted(episode_times)[-1].isoformat()
        feed.rss_file(CACHE_DIR + "/" + slug + " " + recent_ep_time + ".xml", pretty=True)
    return Response(feed.rss_str(pretty=True), mimetype='application/rss+xml')

