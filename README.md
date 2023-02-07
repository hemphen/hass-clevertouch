# CleverTouch - HomeAssistant integration for Touch E3 radiators

LVI by Purmo is range of radiators manufactured by the Finnish company Purmo. Some
models, such as Yali Digital, Parada and Ramo may be monitored and controlled
centrally using the optional accessory TempCo Touch E3. The Touch E3 may in turn
be controlled remotely via a CleverTouch cloud account and related mobile and web
apps.

This HomeAssistant integration provides access to settings and usage data for
homes and radiators accessible through CleverTouch accounts.

## Installation

The integration can be installed in three different ways:

### 1. Using HACS
The repository is not included in HACS by default, but it may be added as a custom repository by
following the [HACS documentation](https://hacs.xyz/docs/faq/custom_repositories/).

### 2. Cloning the Github repository
The repository files should be placed in the sub-directory `custom_components/clevertouch`
of the HomeAssistant configuration directory.

1. Create the `custom_components` directory if it doesn't already exist.
2. `cd` to the folder.
3. Run the command

```bash
git clone https://github.com/hemphen/hass-clevertouch.git clevertouch
```

4. Restart HomeAssistant.
5. Add the integration via the GUI.

Please note that this will clone the latest code changes in the main branch, which
may not always be fully stable or tested. To install a specific release, add
a `--branch` flag to the `clone` command, e.g

```bash
git clone https://github.com/hemphen/hass-clevertouch.git clevertouch --branch v0.2.4
```

### 3. Manually downloading a release file

Download the `source.zip` file for any release from Github and extract the contents into
the `custom_components/clevertouch` directory within the HomeAssistant config directory.

## Usage

The intergration is configurable from the HomeAssistant GUI. Once installed correctly, it should appear in the list of integrations.
Enter username (email) and password for the CleverTouch account during setup.

After congfiguration, all available homes and radiators will be added as devices, with temperature settings
added as entities.

To avoid calling the API too excessively information is updated every three minutes.

### Unsupported features

* Installation-wide settings are not available.
* Schedules for radiators running in program mode are not available.
