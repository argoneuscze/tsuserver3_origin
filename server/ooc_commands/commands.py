# tsuserver3, an Attorney Online server
#
# Copyright (C) 2018 argoneus <argoneuscze@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from server.ooc_commands.argument_types import Type, Flag
from server.ooc_commands.decorators import arguments
from server.util.exceptions import ClientError


# @argument("target_area", arg_type=Type.Integer, optional=False)
# def ooc_cmd_area(client, target_area):
#     ...


@arguments(position=(Type.String, [Flag.Optional]))
def ooc_cmd_pos(client, position):
    if not position:
        client.change_position()
        client.send_host_message("Position reset.")
    else:
        try:
            client.change_position(position)
        except ClientError:
            raise
        client.send_host_message("Position changed.")
