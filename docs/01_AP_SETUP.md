# Set up an AP-755

## 1. Connect power and Ethernet

Use either of these power arrangements:

- connect a compatible DC adapter to the AP; or
- connect AP port `E0` to a compatible PoE injector or PoE switch.

When a DC adapter is used, PoE is not required. Connect `E0` to a network that
provides DHCP. The PC used for SSH must be able to reach the AP's management
address.

Two tested network arrangements are suitable:

- router LAN, AP `E0`, and PC connected to the same LAN; or
- AP `E0` connected to a PC Ethernet interface configured as NetworkManager
  **Shared to other computers**, with the PC providing DHCP and forwarding.

Power on the AP and allow two to three minutes for startup.

## 2. Find the management address

Read the AP address from the router's DHCP leases, Aruba Central, or the PC's
neighbor table:

```bash
ip neigh
ping -c 3 AP_IP
```

The tested AP received `192.168.10.114`; this is a DHCP address and can change.

## 3. Log in through SSH

Use username `admin`. For the tested local experimental image, the password is
the AP serial number exactly as printed on the AP label:

```bash
ssh admin@AP_IP
```

```text
Username: admin
Password: AP_SERIAL_NUMBER
```

For example, the tested AP with serial `USVGM590QB` accepted that serial as
its password. An AP actively managed by Aruba Central can instead use the
password configured for its Central group.

The Micro-USB connector is the serial console. It is not required for SSH.

## 4. Confirm the CSI image

Run these commands in the normal AP CLI:

```text
show version
show ip interface br
show ap debug cloud-server
```

The tested build reports `build elferkou_csimond`. Enter the internal shell and
confirm the HPE CSI programs:

```text
support
```

```sh
command -v wl
command -v csimond
wl -i aruba000 csimon state
```

Expected paths:

```text
/bin/wl
/aruba/bin/csimond
```

If the two CSI commands are not present, install the AP-755 CSI image supplied
by HPE before continuing. Firmware installation is performed through the
serial `apboot` console using the HPE-provided image and flashing procedure.

## 5. Allow local configuration

When Aruba Central manages the AP, Central can control the local configuration.
Unsubscribe the lab AP from its Central device page before creating the local
SSID. Reconnect through SSH after the change.

## 6. Complete initial provisioning when required

A new or reset AP can start in the initial provisioning state. Open:

```text
https://AP_IP:4343/
```

Log in as `admin` using the current AP password and complete the local setup.
Keep the installed CSI image selected.

If the CLI reports the following message while creating the SSID, initial
provisioning is still active:

```text
Can't manually create SSID profile during OTP process
```

For a lab AP with no configuration to retain, the tested reset procedure was:

```text
write erase all
```

Confirm the reset, let the AP reboot, rediscover its DHCP address, open the
initial setup page, and complete provisioning. Then verify `show version`
again before making the radio configuration.

## 7. Set the regulatory country

Set the country where the AP is physically operating. The tested United States
configuration used:

```text
configure terminal
virtual-controller-country US
end
commit apply
```

The country is set before the SSID so the radio can broadcast.

## 8. Create the WPA3 SSID

The tested SSID was named `wpa3`. Substitute your own passphrase for
`WPA3_PASSPHRASE` below; the value only has to match on the AP and the client.

```text
configure terminal
wlan ssid-profile wpa3
essid wpa3
opmode wpa3-sae-aes
wpa-passphrase WPA3_PASSPHRASE
end
commit apply
```

Create the matching access rule:

```text
configure terminal
wlan access-rule wpa3
rule any any match any any any permit
end
commit apply
```

## 9. Connect and verify the client

Connect the phone or other transmitter to the `wpa3` SSID. The upstream router
or the PC-shared network supplies the client DHCP address.

Run:

```text
show network
show ip interface br
show ap bss-table
show ap association
```

Record the client MAC shown by `show ap association`. A phone can use a private
Wi-Fi MAC, so use the address displayed by the AP for the current association.
Also record the BSSID, band, channel, width, and AP management address.

Continue with [CSI collection](02_CSI_COLLECTION.md).
