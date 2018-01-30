# -*- coding: utf-8 -*-
"""
Automation task as a AppDaemon App for Home Assistant

Populate dinamically an `input_select` with Kodi play options
and react when selected.

It reacts to `kodi_call_method_result` events, when the used API method is:
    - VideoLibrary.GetRecentlyAddedMovies
    - VideoLibrary.GetRecentlyAddedEpisodes
    - PVR.GetChannels
"""

import appdaemon.appapi as appapi


EVENT_KODI_CALL_METHOD_RESULT = 'kodi_call_method_result'

ENTITY = 'input_select.kodi_results'
MEDIA_PLAYER = 'media_player.kodi'
DEFAULT_ACTION = "Nada que hacer"
MAX_RESULTS = 20


# noinspection PyClassHasNoInit
class DynamicKodiInputSelect(appapi.AppDaemon):
    """App to populate an input select with Kodi API calls results."""

    _ids_options = None
    _last_values = None

    def initialize(self):
        """Set up appdaemon app."""
        self.listen_event(self._receive_kodi_result,
                          EVENT_KODI_CALL_METHOD_RESULT)
        self.listen_state(self._change_selected_result, ENTITY)

        # Input select:
        self._ids_options = {DEFAULT_ACTION: None}
        self._last_values = []

    # noinspection PyUnusedLocal
    def _receive_kodi_result(self, event_id, payload_event, *args):
        result = payload_event['result']
        method = payload_event['input']['method']

        if event_id == EVENT_KODI_CALL_METHOD_RESULT:
            if method == 'VideoLibrary.GetRecentlyAddedMovies':
                # values = list(filter(lambda r: not r['lastplayed'],
                #                      result['movies']))[:MAX_RESULTS]
                values = result['movies'][:MAX_RESULTS]
                data = [('{} ({})'.format(r['label'], r['year']),
                         ('MOVIE', r['file'], None)) for r in values]
                self._ids_options.update(dict(zip(*zip(*data))))
                labels = list(list(zip(*data))[0])
                self._last_values = labels
                self.log('{} NEW MOVIE OPTIONS:\n{}'
                         .format(len(labels), labels))
                self.call_service('input_select/set_options', entity_id=ENTITY,
                                  options=[DEFAULT_ACTION] + labels)
                self.set_state(ENTITY,
                               attributes={"friendly_name": 'Recent Movies',
                                           "icon": 'mdi:movie'})
            elif method == 'VideoLibrary.GetRecentlyAddedEpisodes':
                values = result['episodes']
                data = [('{} - {}'.format(r['showtitle'], r['label']),
                         ('TVSHOW', r['file'], r['lastplayed']))
                        for r in values]
                d_data = dict(zip(*zip(*data)))
                labels = list(list(zip(*data))[0])
                if not self._last_values or \
                        not all(map(lambda x: x in labels, self._last_values)):
                    # First press --> filter non watched episodes
                    data = filter(lambda x: not x[1][2], data)
                    labels = list(list(zip(*data))[0])
                self.log('{} NEW TVSHOW OPTIONS:\n{}'
                         .format(len(labels), labels))
                self._ids_options.update(d_data)

                self._last_values = labels
                self.call_service('input_select/set_options', entity_id=ENTITY,
                                  options=[DEFAULT_ACTION] + labels)
                self.set_state(ENTITY,
                               attributes={"friendly_name": 'Recent TvShows',
                                           "icon": 'mdi:play-circle'})
            elif method == 'PVR.GetChannels':
                values = result['channels']
                data = [(r['label'], ('CHANNEL', r['channelid'], None))
                        for r in values]
                self._ids_options.update(dict(zip(*zip(*data))))
                labels = list(list(zip(*data))[0])
                self._last_values = labels
                self.log('{} NEW PVR OPTIONS:\n{}'.format(len(labels), labels))
                self.call_service('input_select/set_options', entity_id=ENTITY,
                                  options=[DEFAULT_ACTION] + labels)
                self.set_state(ENTITY,
                               attributes={"friendly_name": 'TV channels',
                                           "icon": 'mdi:play-box-outline'})

    # noinspection PyUnusedLocal
    def _change_selected_result(self, entity, attribute, old, new, kwargs):
        if new != old:
            # self.log('SELECTED OPTION: {} (from {})'.format(new, old))
            selected = self._ids_options[new]
            if selected:
                mediatype, file, _last_played = selected
                self.log('PLAY MEDIA: {} {} [file={}]'
                         .format(mediatype, new, file))
                self.call_service('media_player/play_media',
                                  entity_id=MEDIA_PLAYER,
                                  media_content_type=mediatype,
                                  media_content_id=file)
