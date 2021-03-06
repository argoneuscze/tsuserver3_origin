# tsuserver3, an Attorney Online server
#
# Copyright (C) 2016 argoneus <argoneuscze@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio

import websockets
import yaml

from server.areas.area_manager import AreaManager
from server.clients.client_manager import ClientManager
from server.data.ban_manager import BanManager
from server.network.ao_protocol import AOProtocol
from server.network.ao_protocol_ws import new_websocket_client
from server.network.district_client import DistrictClient
from server.network.master_server_client import MasterServerClient
from server.util import logger
from server.util.constants import SOFTWARE, SOFTWARE_VERSION
from server.util.exceptions import ServerError


class TsuServer3:
    def __init__(self):
        self.client_manager = ClientManager(self)
        self.area_manager = AreaManager(self)
        self.ban_manager = BanManager()
        self.software = SOFTWARE
        self.software_version = SOFTWARE_VERSION
        self.char_list = None
        self.music_list = None
        self.music_list_network = None
        self.backgrounds = None
        self.config = None
        self.load_config()
        self.load_characters()
        self.load_music()
        self.load_backgrounds()
        self.district_client = None
        self.ms_client = None
        logger.setup_logger(debug=self.config["debug"])

    def start(self):
        loop = asyncio.get_event_loop()

        bound_ip = "0.0.0.0"
        if self.config["local"]:
            bound_ip = "127.0.0.1"

        ao_server_crt = loop.create_server(
            lambda: AOProtocol(self), bound_ip, self.config["port"]
        )
        ao_server = loop.run_until_complete(ao_server_crt)

        if self.config["use_websockets"]:
            ao_server_ws = websockets.serve(
                new_websocket_client(self), bound_ip, self.config["websocket_port"]
            )
            asyncio.ensure_future(ao_server_ws)
            print(logger.log_debug("WebSocket support enabled."))

        if self.config["use_district"]:
            self.district_client = DistrictClient(self)
            asyncio.ensure_future(self.district_client.connect(), loop=loop)
            print(logger.log_debug("District support enabled."))

        if self.config["use_masterserver"]:
            self.ms_client = MasterServerClient(self)
            asyncio.ensure_future(self.ms_client.connect(), loop=loop)
            print(logger.log_debug("Master server support enabled."))

        print(logger.log_debug("Server started."))

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass

        logger.log_debug("Server shutting down.")

        ao_server.close()
        loop.run_until_complete(ao_server.wait_closed())
        loop.close()

    def new_client(self, transport):
        c = self.client_manager.new_client(
            transport, self.area_manager.get_default_area()
        )
        c.area.new_client(c)
        return c

    def remove_client(self, client):
        client.area.remove_client(client)
        self.client_manager.remove_client(client)
        self.send_arup_all()

    def get_player_count(self):
        return len(self.client_manager.clients)

    def load_config(self):
        with open("config/config.yaml", "r") as cfg:
            self.config = yaml.load(cfg, Loader=yaml.FullLoader)

    def load_characters(self):
        with open("config/characters.yaml", "r") as chars:
            self.char_list = yaml.load(chars, Loader=yaml.BaseLoader)

    def load_music(self):
        with open("config/music.yaml", "r") as music:
            self.music_list = yaml.load(music, Loader=yaml.FullLoader)
        # populate song list including areas
        network_music_list = [area.name for area in self.area_manager.areas]
        for item in self.music_list:
            network_music_list.append(item["category"])
            network_music_list.extend([song["name"] for song in item["songs"]])
        self.music_list_network = network_music_list

    def load_backgrounds(self):
        with open("config/backgrounds.yaml", "r") as bgs:
            self.backgrounds = yaml.load(bgs, Loader=yaml.BaseLoader)

    def is_valid_char_id(self, char_id):
        return len(self.char_list) > char_id >= 0

    def get_char_id_by_name(self, name):
        for i, ch in enumerate(self.char_list):
            if ch.lower() == name.lower():
                return i
        raise ServerError("Character not found.")

    def get_song_data(self, music):
        for item in self.music_list:
            if item["category"] == music:
                return item["category"], -1
            for song in item["songs"]:
                if song["name"] == music:
                    try:
                        return song["name"], song["length"]
                    except KeyError:
                        return song["name"], -1
        raise ServerError("Music not found.")

    def send_all_cmd_pred(self, cmd, *args, pred=lambda x: True):
        for client in self.client_manager.clients:
            if pred(client):
                client.send_command(cmd, *args)

    def broadcast_global(self, client, msg, as_mod=False):
        char_name = client.get_char_name()
        ooc_name = "{}[{}][{}]".format(
            self.config["globalname"], client.area.id, char_name
        )
        if as_mod:
            ooc_name += "[M]"
        self.send_all_cmd_pred("CT", ooc_name, msg)
        if self.config["use_district"]:
            self.district_client.send_raw_message(
                "GLOBAL#{}#{}#{}#{}".format(int(as_mod), client.area.id, char_name, msg)
            )

    def send_arup_players(self):
        area_players = [len(area.clients) for area in self.area_manager.areas]
        self.send_all_cmd_pred("ARUP", 0, *area_players)

    def send_arup_status(self):
        area_statuses = [area.get_attr("status") for area in self.area_manager.areas]
        self.send_all_cmd_pred("ARUP", 1, *area_statuses)

    def send_arup_cm(self):
        area_cms = [area.get_attr("case.master") for area in self.area_manager.areas]
        self.send_all_cmd_pred("ARUP", 2, *area_cms)

    def send_arup_all(self):
        self.send_arup_players()
        self.send_arup_status()
        self.send_arup_cm()
