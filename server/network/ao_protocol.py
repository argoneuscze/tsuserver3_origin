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
from enum import Enum

from server.network.network_interface import NetworkInterface
from server.ooc_commands import commands
from server.util import logger
from server.util.exceptions import ClientError, AreaError, ArgumentError, ServerError
from server.util.fantacrypt import fanta_decrypt


class AOProtocol(asyncio.Protocol):
    """
    The main class that deals with the AO protocol.
    """

    class ArgType(Enum):
        STR = (1,)
        STR_OR_EMPTY = (2,)
        INT = 3

    def __init__(self, server):
        super().__init__()
        self.server = server
        self.client = None
        self.buffer = ""
        self.ping_timeout = None

    def data_received(self, data):
        """ Handles any data received from the network.

        Receives data, parses them into a command and passes it
        to the command handler.

        :param data: bytes of data
        """
        # try to decode as utf-8, ignore any erroneous characters
        self.buffer += data.decode("utf-8", "ignore")
        if len(self.buffer) > 8192:
            self.client.disconnect()
        for msg in self.get_messages():
            if len(msg) < 2:
                self.client.disconnect()
                return
            # general netcode structure is not great
            if msg[0] in ("#", "3", "4"):
                if msg[0] == "#":
                    msg = msg[1:]
                spl = msg.split("#", 1)
                msg = "#".join([fanta_decrypt(spl[0])] + spl[1:])
                logger.log_debug("[INC][RAW]{}".format(msg), self.client)
            try:
                print("RCV: {}".format(msg))  # TODO debug

                cmd, *args = msg.split("#")
                self.net_cmd_dispatcher[cmd](self, args)
            except KeyError:
                return

    def connection_made(self, transport):
        """ Called upon a new client connecting

        :param transport: the transport object
        """
        self.client = self.server.new_client(NetworkInterface(transport))
        self.ping_timeout = asyncio.get_event_loop().call_later(
            self.server.config["timeout"], self.client.disconnect
        )
        self.client.send_command("decryptor", 34)  # just fantacrypt things

    def connection_lost(self, exc):
        """ User disconnected

        :param exc: reason
        """
        self.server.remove_client(self.client)
        self.ping_timeout.cancel()

    def get_messages(self):
        """ Parses out full messages from the buffer.

        :return: yields messages
        """
        while "#%" in self.buffer:
            spl = self.buffer.split("#%", 1)
            self.buffer = spl[1]
            yield spl[0]
        # exception because bad netcode
        askchar2 = "#615810BC07D12A5A#"
        if self.buffer == askchar2:
            self.buffer = ""
            yield askchar2

    def validate_net_cmd(self, args, *types, needs_auth=True):
        """ Makes sure the net command's arguments match expectations.

        :param args: actual arguments to the net command
        :param types: what kind of data types are expected
        :param needs_auth: whether you need to have chosen a character
        :return: returns True if message was validated
        """
        if needs_auth and self.client.char_id == -1:
            return False
        if len(args) != len(types):
            return False
        for i, arg in enumerate(args):
            if len(arg) == 0 and types[i] != self.ArgType.STR_OR_EMPTY:
                return False
            if types[i] == self.ArgType.INT:
                try:
                    args[i] = int(arg)
                except ValueError:
                    return False
        return True

    def net_cmd_hi(self, args):
        """ Handshake.

        HI#<hdid:string>#%

        :param args: a list containing all the arguments
        """
        if not self.validate_net_cmd(args, self.ArgType.STR, needs_auth=False):
            return
        self.client.hdid = args[0]
        if self.server.ban_manager.is_banned(self.client.get_ip()):
            self.client.disconnect()
            return
        version_string = ".".join(map(str, self.server.software_version))
        self.client.send_command(
            "ID", self.client.id, self.server.software, version_string
        )
        self.client.send_command(
            "PN", self.server.get_player_count() - 1, self.server.config["playerlimit"]
        )

    def net_cmd_ch(self, _):
        """ Periodically checks the connection.

        CHECK#%

        """
        self.client.send_command("CHECK")
        self.ping_timeout.cancel()
        self.ping_timeout = asyncio.get_event_loop().call_later(
            self.server.config["timeout"], self.client.disconnect
        )

    def net_cmd_id(self, args):
        """ Client software and version

        ID#<software:string>#<version:string>#%

        """
        if not self.validate_net_cmd(
            args, self.ArgType.STR, self.ArgType.STR, needs_auth=False
        ):
            self.client.disconnect()

        client, version = args

        if client == "AO2":
            # TODO remove this once AO2 gets rid of FL
            self.client.send_command(
                "FL",
                "yellowtext",
                "customobjections",
                "flipping",
                "fastloading",
                "noencryption",
                "deskmod",
                "evidence",
            )

    def net_cmd_askchaa(self, _):
        """ Ask for the counts of characters/evidence/music

        askchaa#%

        """
        char_cnt = len(self.server.char_list)
        evi_cnt = 0
        music_cnt = 0
        self.client.send_command("SI", char_cnt, evi_cnt, music_cnt)

    def net_cmd_rc(self, _):
        """ Asks for the character list.

        RC#%

        """
        self.client.send_command("SC", *self.server.char_list)

    def net_cmd_rm(self, _):
        """ Asks for the music list.

        RM#%

        """
        self.client.send_command("SM", *self.server.music_list_network)

    def net_cmd_rd(self, _):
        """ Client is ready.

        RD#%

        """
        self.client.send_done()
        self.client.send_area_list()
        self.client.send_motd()

    def net_cmd_cc(self, args):
        """ Character selection.

        CC#<client_id:int>#<char_id:int>#<hdid:string>#%

        """
        if not self.validate_net_cmd(
            args, self.ArgType.INT, self.ArgType.INT, self.ArgType.STR, needs_auth=False
        ):
            return
        cid = args[1]
        try:
            self.client.change_character(cid)
        except ClientError:
            return

    def net_cmd_ms(self, args):
        """ IC message.

        Refer to the implementation for details.

        """
        if self.client.is_muted:  # Checks to see if the client has been muted by a mod
            self.client.send_host_message("You have been muted by a moderator")
            return
        if not self.client.area.can_send_message():
            return
        if not self.validate_net_cmd(
            args,
            self.ArgType.STR,
            self.ArgType.STR_OR_EMPTY,
            self.ArgType.STR,
            self.ArgType.STR,
            self.ArgType.STR,
            self.ArgType.STR,
            self.ArgType.STR,
            self.ArgType.INT,
            self.ArgType.INT,
            self.ArgType.INT,
            self.ArgType.INT,
            self.ArgType.INT,
            self.ArgType.INT,
            self.ArgType.INT,
            self.ArgType.INT,
        ):
            return
        (
            msg_type,
            pre,
            folder,
            anim,
            text,
            pos,
            sfx,
            anim_type,
            cid,
            sfx_delay,
            button,
            evidence,
            flip,
            ding,
            color,
        ) = args
        if msg_type != "chat":
            return
        if anim_type not in (0, 1, 2, 5, 6):
            return
        if cid != self.client.char_id:
            return
        if sfx_delay < 0:
            return
        if button not in (0, 1, 2, 3, 4):
            return
        if evidence < 0:
            return
        if flip not in (0, 1):
            return
        if ding not in (0, 1):
            return
        if color not in (0, 1, 2, 3, 4, 5):
            return
        if color == 2 and not self.client.is_mod:
            color = 0
        if self.client.pos:
            pos = self.client.pos
        else:
            if pos not in ("def", "pro", "hld", "hlp", "jud", "wit"):
                return
        msg = text[:256]
        evidence = 0  # TODO implement evidence
        self.client.area.send_command(
            "MS",
            msg_type,
            pre,
            folder,
            anim,
            msg,
            pos,
            sfx,
            anim_type,
            cid,
            sfx_delay,
            button,
            evidence,
            flip,
            ding,
            color,
        )
        self.client.area.set_next_msg_delay(len(msg))
        logger.log_server(
            "[IC][{}][{}]{}".format(
                self.client.area.id, self.client.get_char_name(), msg
            ),
            self.client,
        )

    def net_cmd_ct(self, args):
        """ OOC Message

        CT#<name:string>#<message:string>#%

        """
        if not self.validate_net_cmd(args, self.ArgType.STR, self.ArgType.STR):
            return
        if self.client.name == "":
            self.client.name = args[0]
        if self.client.name.startswith(
            self.server.config["hostname"]
        ) or self.client.name.startswith("<dollar>G"):
            self.client.send_host_message("That name is reserved!")
            return
        if args[1].startswith("/"):
            spl = args[1][1:].split(" ", 1)
            cmd = spl[0]
            arg = ""
            if len(spl) == 2:
                arg = spl[1][:256]
            try:
                getattr(commands, "ooc_cmd_{}".format(cmd))(self.client, arg)
            except AttributeError:
                self.client.send_host_message("Invalid command.")
            except (ClientError, AreaError, ArgumentError, ServerError) as ex:
                self.client.send_host_message(ex)
        else:
            self.client.area.send_command("CT", self.client.name, args[1])
            logger.log_server(
                "[OOC][{}][{}][{}]{}".format(
                    self.client.area.id,
                    self.client.get_char_name(),
                    self.client.name,
                    args[1],
                ),
                self.client,
            )

    def net_cmd_mc(self, args):
        """ Play music.

        MC#<song_name:int>#<???:int>#%

        """
        if not self.validate_net_cmd(args, self.ArgType.STR, self.ArgType.INT):
            return
        if args[1] != self.client.char_id:
            return
        try:
            area = self.server.area_manager.get_area_by_name(args[0])
            self.client.change_area(area)
        except AreaError:
            try:
                name, length = self.server.get_song_data(args[0])
                self.client.area.play_music(name, self.client.char_id, length)
                self.client.area.add_music_playing(self.client, name)
                logger.log_server(
                    "[{}][{}]Changed music to {}.".format(
                        self.client.area.id, self.client.get_char_name(), name
                    ),
                    self.client,
                )
            except ServerError:
                return
        except ClientError as ex:
            self.client.send_host_message(ex)

    def net_cmd_rt(self, args):
        """ Plays the Testimony/CE animation.

        RT#<type:string>#%

        """
        if not self.validate_net_cmd(args, self.ArgType.STR):
            return
        if args[0] not in ("testimony1", "testimony2"):
            return
        self.client.area.send_command("RT", args[0])
        self.client.area.add_to_judgelog(self.client, "used WT/CE")
        logger.log_server(
            "[{}]{} Used WT/CE".format(
                self.client.area.id, self.client.get_char_name()
            ),
            self.client,
        )

    def net_cmd_hp(self, args):
        """ Sets the penalty bar.

        HP#<type:int>#<new_value:int>#%

        """
        if not self.validate_net_cmd(args, self.ArgType.INT, self.ArgType.INT):
            return
        try:
            self.client.area.change_hp(args[0], args[1])
            self.client.area.add_to_judgelog(self.client, "changed the penalties")
            logger.log_server(
                "[{}]{} changed HP ({}) to {}".format(
                    self.client.area.id, self.client.get_char_name(), args[0], args[1]
                ),
                self.client,
            )
        except AreaError:
            return

    def net_cmd_pe(self, args):
        """ Adds a piece of evidence. TODO
        PE#<name:string>#<description:string>#<image:string>#%
        """
        ...

    def net_cmd_de(self, args):
        """ Deletes a piece of evidence. TODO
        DE#<id:int>#%
        """
        ...

    def net_cmd_ee(self, args):
        """ Edits a piece of evidence. TODO
        EE#<id:int>#<name:string>#<description:string>#<image:string>#%
        """
        ...

    def net_cmd_zz(self, _):
        """ Sent on mod call.

        """
        self.server.send_all_cmd_pred(
            "ZZ",
            "{} ({}) in {} ({})".format(
                self.client.get_char_name(),
                self.client.get_ip(),
                self.client.area.name,
                self.client.area.id,
            ),
            pred=lambda c: c.is_mod,
        )
        logger.log_server(
            "[{}]{} called a moderator.".format(
                self.client.area.id, self.client.get_char_name()
            )
        )

    def net_cmd_opKICK(self, args):
        self.net_cmd_ct(["opkick", "/kick {}".format(args[0])])

    def net_cmd_opBAN(self, args):
        self.net_cmd_ct(["opban", "/ban {}".format(args[0])])

    net_cmd_dispatcher = {
        "HI": net_cmd_hi,  # handshake
        "CH": net_cmd_ch,  # keepalive
        "ID": net_cmd_id,  # client version
        "askchaa": net_cmd_askchaa,  # ask for list lengths
        "RC": net_cmd_rc,  # character list
        "RM": net_cmd_rm,  # music list
        "RD": net_cmd_rd,  # client is ready
        "CC": net_cmd_cc,  # select character
        "MS": net_cmd_ms,  # IC message
        "CT": net_cmd_ct,  # OOC message
        "MC": net_cmd_mc,  # play song
        "RT": net_cmd_rt,  # WT/CE buttons
        "HP": net_cmd_hp,  # penalties
        "PE": net_cmd_pe,  # add evidence
        "DE": net_cmd_de,  # delete evidence
        "EE": net_cmd_ee,  # edit evidence
        "ZZ": net_cmd_zz,  # call mod button
        "opKICK": net_cmd_opKICK,  # /kick with guard on
        "opBAN": net_cmd_opBAN,  # /ban with guard on
    }
