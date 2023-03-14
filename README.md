# CleverTouch - Home Assistant integration for Touch E3 radiators

> ***IMPORTANT!***
>
> This is not an officially supported integration nor software library.
> There are no guarantees that the functionality will work as expected.
>
> Take caution especially when automating device _configuration_.
>
> ***THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND***

## Background

Yali Digital, Parada and Ramo is range of radiators from the Finnish company Purmo(*). The radiators may be monitored and controlled
_centrally_ and wirelessly using the optional accessory TempCo Touch E3. The Touch E3 may in turn
be controlled _remotely_ via a CleverTouch cloud account and related mobile and web
apps.

This Home Assistant integration provides access to settings and usage data for homes and radiators accessible through CleverTouch accounts.

(*) Purmo has aquired several brands over time, and the radiator manufacturer might be known as e g LVI, Radson or Finimetal on local markets.

## Other brands

While untested, a number of other product lines seem to be using the same controller software with different branding.

Applications using the following URLs might work, fully or partially.

* Walter Meier Metalplast smart-comfort - [https://www.smartcomfort.waltermeier.com](https://www.smartcomfort.waltermeier.com)
* Frico PF Smart - [https://fricopfsmart.frico.se](https://fricopfsmart.frico.se)
* Fenix V24 Wifi - [https://v24.fenixgroup.eu](https://v24.fenixgroup.eu)
* Vogel & Noot E3 App - [Vogel & Noot E3 App - [https://e3.vogelundnoot.com](https://e3.vogelundnoot.com)
* CordiVari My Way Cosy Home - [https://cordivarihome.com](https://cordivarihome.com)

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

## API

The API used to communicate with the CleverTouch account is located in a stand-alone repository
https://github.com/hemphen/clevertouch and is also available on PyPi.
