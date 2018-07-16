"""
A very simple Appdaemon app to query youtube videos with text from an
`input_text`, populate an `input_select` with the results obtained,
and play them in a Kodi `media_player` when selected.

You need a Youtube API Key to run the search!

The config needed to run this app:
```yaml
ytb_search:
  module: youtube_search
  class: YoutubeSearch
  input_select: input_select.youtube_videos
  input_text: input_text.q_youtube
  media_player: media_player.kodi
  youtube_key: 123456789012345678901234567890123456789
```
"""

import appdaemon.plugins.hass.hassapi as hass
import requests


URL_BASE = 'https://www.googleapis.com/youtube/v3/search'
KODI_YOUTUBE_PLUGIN_MASK = "plugin://plugin.video.youtube/play/?video_id={}"
DEFAULT_ACTION = 'Nada que hacer'


def query_youtube_videos(str_query, max_results=20, is_normal_query=True,
                         order_by_date=False, youtube_key=None):
    params = dict(order='date' if order_by_date else 'relevance',
                  part='snippet', key=youtube_key, maxResults=max_results)
    if is_normal_query:
        params.update({'q': str_query})
    else:
        params.update({str_query.split('=')[0].strip():
                       str_query.split('=')[1].strip()})

    data = requests.get(URL_BASE, params=params).json()
    found = []
    for item in data['items']:
        if item['id']['kind'] == 'youtube#video':
            found.append((item['id']['videoId'], item['snippet']['title']))
    return found


# noinspection PyClassHasNoInit
class YoutubeSearch(hass.Hass):
    """App that listens to the input text and select."""

    _ids_options = None
    _youtube_key = None

    _input_select = None
    _input_text = None
    _media_player = None

    def initialize(self):
        """Set up App."""
        self._input_select = self.args.get('input_select')
        self._input_text = self.args.get('input_text')
        self._media_player = self.args.get('media_player', 'media_player.kodi')
        self._youtube_key = self.args.get('youtube_key')
        # self.log(f"Youtube API Key: {self._youtube_key}")
        self.listen_state(self.new_youtube_query, self._input_text)
        self.listen_state(self.video_selection, self._input_select)
        self._ids_options = {DEFAULT_ACTION: None}

    # noinspection PyUnusedLocal
    def new_youtube_query(self, entity, attribute, old, new, kwargs):
        """Query videos with input_text."""
        self.log('New youtube query with "{}"'.format(new))
        found = query_youtube_videos(new,
                                     max_results=20,
                                     is_normal_query=True,
                                     order_by_date=False,
                                     youtube_key=self._youtube_key)
        self.log('YOUTUBE QUERY FOUND:\n{}'.format(found))

        # Update input_select values:
        self._ids_options.update({name: v_id for v_id, name in found})
        labels = [f[1] for f in found]
        self.log('NEW OPTIONS:\n{}'.format(labels))
        self.call_service('input_select/set_options',
                          entity_id=self._input_select,
                          options=[DEFAULT_ACTION] + labels)

    # noinspection PyUnusedLocal
    def video_selection(self, entity, attribute, old, new, kwargs):
        """Play the selected video from a previous query."""
        self.log('SELECTED OPTION: {} (from {})'.format(new, old))
        try:
            selected = self._ids_options[new]
        except KeyError:
            self.error('Selection "{}" not in memory (doing nothing)'
                       .format(new), 'WARNING')
            return

        if selected:
            self.log('PLAY MEDIA: {} [id={}]'.format(new, selected))
            self.call_service(
                'media_player/play_media', entity_id=self._media_player,
                media_content_type="video",
                media_content_id=KODI_YOUTUBE_PLUGIN_MASK.format(selected))
