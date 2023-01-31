# CleverTouch - HomeAssistant integration for TempCo Touch E3

LVI by Purmo is range of radiators manufactured by the Finnish company Purmo. Some
models, such as Yali Digital, Parada and Ramo may be monitored and controlled remotely
using the optional accessory TempCo Touch E3. The radiators are managed with the CleverTouch
mobile or web apps using a cloud-based service to interact with the Touch E3.

This integration provides access to settings and usage data for homes and radiators connected
to a CleverTouch account via the Touch E3.

> **Disclaimer**
>
> This integration and its companion [API library](https://github.com/hemphen/clevertouch) is very much in early beta. While it works for myself, it might not do so for you. It currently only supports read-only access to radiators.

## Installation

The integration can be installed in three different ways:

### 1. Using HACS
The repository is not included by default in HACS, but conforms to HACS guidelines and can be added as a custom repository, see the
[HACS documentation](https://hacs.xyz/docs/faq/custom_repositories/).

### 2. By cloning the Github repository
The repository files should be placed in the sub-directory `custom_components/clevertouch`
of the HomeAssistant configuration directory.

Easiest (while a bit risky since this is work in progress) would be to install using git.

1. Create the `custom_components` directory if it doesn't already exist.
2. `cd` to the folder.
3. Run the command

```bash
git clone https://github.com/hemphen/homeassistant-clevertouch.git clevertouch
```

4. Restart HomeAssistant.
5. Add the integration via the GUI.

A specific release can be installed by adding a `--branch` flag to the `clone` command, e.g

```bash
git clone https://github.com/hemphen/homeassistant-clevertouch.git clevertouch --branch v2.0.1
```

### 3. By manually downloading the release file

Download the `source.zip` file for the release from Github and extract the contents into the sub-directory `custom_components/clevertouch` of the HomeAssistant config directory.

## Usage

The intergration is configurable from the HomeAssistant GUI. If installed correctly it should be available in the list of integrations. When first setup it will require the username (email)
and password for the CleverTouch account.

When configured all available homes (Touch E3 accessories) and radiators will be added as devices, with all temperature settings
added as sensors.

To avoid calling the API too excessively information is updated every five minutes.

### Unsupported features

* Only read-only access is currently supported.
* Installation-wide settings are not available.
* Schedules for radiators running in program mode are not avialable.
