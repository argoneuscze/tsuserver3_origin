# tsuserver3 Origin

A Python based server for Attorney Online.

Currently targeting client version `AO2 v2.6.2`, while `webAO` is unsupported.

Requires Python 3.8+.

## Motivation

Over the years, the original [tsuserver3](https://github.com/AttorneyOnlineVidya/tsuserver3) has been changed by various people and the codebase
has been inflated to the point where making any sort of change created a bigger mess than before.

Therefore *tsuserver3 Origin* aims to keep the old codebase simple and extend the code reasonably
while keeping it simple to add new features.

## TODO

There's a bunch of features currently missing from this version, as it's almost two years old.
I hope to implement those and more in time. These are:

* ~~AO2 Loading~~
* ~~AO2 Feature Support~~
* Evidence support
* ~~WebSockets~~
* Modcall reason
* Built-in support for Areas (pending client support)
* Improved banlist (SQLite)
* Server voting (SQLite)
* REST API
* Pairing
* Password/Token for areas
* Command overhaul [x]
* Improved targeting for OOC commands [x]

Items marked with [x] are currently in progress.


## How to use

* Rename `config_sample` to `config` and edit the values to your liking.  
* Run by using `start_server.py`. It's recommended that you use a separate virtual environment.

## Commands

### User Commands

* 

### Mod Commands

* 

## License

This server is licensed under the AGPLv3 license. See the
[LICENSE](LICENSE.md) file for more information.