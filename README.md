# CleverTouch - HomeAssistant support for Purmo Touch E3

HomeAssistant integration for Touch E3 smart device controllers via CleverTouch cloud accounts.

DISCLAIMER! This integration and its companion API library is very much in early beta. While it
work for myself, it might not do so for you. It currently only supports read-only access to radiators.

## Installation

The repository files should be placed in the sub-folder `custom_components\clevertouch`
to the HomeAssistant installation.

Easiest (while a bit risky since this is work in progress) would be to install using git.

1. Create the `custom_components` folder if it doesn't already exist.
2. `cd` to the folder.
3. Run `git clone https://github.com/hemphen/homeassistant-clevertouch.git clevertouch`.
4. Restart HomeAssistant.
5. Add the integration via the GUI.
